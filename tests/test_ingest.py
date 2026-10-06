"""Ingestão: o que ela precisa garantir para a busca filtrar certo.

A busca confia em duas colunas — `documentos.indexar` e `trechos.embedding` —
e é a ingestão que as mantém corretas. Estes testes cobrem os dois casos em
que elas mentiriam: trecho órfão e documento cujo arquivo deixou de valer.
"""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings import ResultadoEmbeddings
from app.models import AutorMensagem, Conversa, Documento, Mensagem, MensagemTrecho, Trecho
from app.services.busca import buscar_trechos
from scripts import ingest
from tests.fabricas import vetor

SECOES = {"Mensalidade": "A mensalidade custa R$ 389,00.", "Matrícula": "A taxa é de R$ 150,00."}


def escrever(
    base: Path, identificador: str, secoes: dict[str, str], *, indexar: bool = True
) -> Path:
    corpo = "\n\n".join(f"## {titulo}\n\n{conteudo}" for titulo, conteudo in secoes.items())
    arquivo = base / f"{identificador}.md"
    arquivo.write_text(
        "---\n"
        f"id: {identificador}\n"
        f"titulo: Documento {identificador}\n"
        "topico: comercial\n"
        "publico: [interessados]\n"
        f"indexar: {'true' if indexar else 'false'}\n"
        "atualizado_em: 2026-08-11\n"
        "---\n\n"
        f"# Documento {identificador}\n\n{corpo}\n",
        encoding="utf-8",
    )
    return arquivo


@pytest.fixture
def vetorizacao_falsa(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Troca a vetorização de documentos; devolve os lotes de texto recebidos."""
    lotes: list[list[str]] = []

    async def falsa(textos: list[str]) -> ResultadoEmbeddings:
        lotes.append(textos)
        return ResultadoEmbeddings(
            vetores=[vetor(10 * i) for i in range(len(textos))], tokens_usados=len(textos)
        )

    monkeypatch.setattr(ingest, "gerar_embeddings_documentos", falsa)
    return lotes


async def ingerir(
    sessao: AsyncSession, base: Path
) -> tuple[ingest.Relatorio, ingest.RelatorioEmbeddings]:
    arquivos = ingest.ler_base(base)
    relatorio = await ingest.gravar(sessao, arquivos, forcar=False)
    embeddings = await ingest.vetorizar_trechos(sessao, arquivos, sem_embeddings=False)
    return relatorio, embeddings


async def estado_dos_trechos(sessao: AsyncSession) -> dict[str, tuple[bool, str | None]]:
    """Título da seção -> (tem vetor?, modelo). Lido do banco, não da memória da sessão."""
    linhas = await sessao.execute(
        select(Trecho.titulo, Trecho.embedding.is_not(None), Trecho.embedding_modelo)
    )
    return {titulo: (tem_vetor, modelo) for titulo, tem_vetor, modelo in linhas}


async def citar_em_resposta(sessao: AsyncSession, titulo_secao: str) -> None:
    """Faz o trecho constar na auditoria de uma resposta — o que impede seu DELETE."""
    trecho_id = await sessao.scalar(select(Trecho.id).where(Trecho.titulo == titulo_secao))
    assert trecho_id is not None
    conversa = Conversa(canal="teste")
    sessao.add(conversa)
    await sessao.flush()
    mensagem = Mensagem(conversa_id=conversa.id, autor=AutorMensagem.BOT, conteudo="resposta")
    sessao.add(mensagem)
    await sessao.flush()
    sessao.add(MensagemTrecho(mensagem_id=mensagem.id, trecho_id=trecho_id, similaridade=0.9))
    await sessao.flush()


async def titulos_na_busca(sessao: AsyncSession) -> set[str]:
    resultado = await buscar_trechos(sessao, "qualquer pergunta", k=20)
    return {trecho.titulo_secao for trecho in resultado.trechos}


async def test_primeira_ingestao_vetoriza_com_titulos_no_texto(
    sessao: AsyncSession, tmp_path: Path, vetorizacao_falsa: list[list[str]]
) -> None:
    escrever(tmp_path, "valores", SECOES)

    _, embeddings = await ingerir(sessao, tmp_path)

    assert embeddings.vetorizados == 2
    assert vetorizacao_falsa == [
        [
            "Documento valores — Mensalidade\n\nA mensalidade custa R$ 389,00.",
            "Documento valores — Matrícula\n\nA taxa é de R$ 150,00.",
        ]
    ]
    assert await estado_dos_trechos(sessao) == {
        "Mensalidade": (True, "voyage-4-lite"),
        "Matrícula": (True, "voyage-4-lite"),
    }


async def test_segunda_ingestao_sem_mudanca_nao_chama_a_voyage(
    sessao: AsyncSession, tmp_path: Path, vetorizacao_falsa: list[list[str]]
) -> None:
    escrever(tmp_path, "valores", SECOES)
    await ingerir(sessao, tmp_path)
    vetorizacao_falsa.clear()

    relatorio, embeddings = await ingerir(sessao, tmp_path)

    assert vetorizacao_falsa == []
    assert embeddings.vetorizados == 0
    assert relatorio.inalterados == ["valores.md"]


async def test_trecho_orfao_perde_o_vetor_e_nao_ganha_outro(
    sessao: AsyncSession,
    tmp_path: Path,
    vetorizacao_falsa: list[list[str]],
    voyage_falsa: list[str],
) -> None:
    escrever(tmp_path, "valores", SECOES)
    await ingerir(sessao, tmp_path)
    await citar_em_resposta(sessao, "Matrícula")
    vetorizacao_falsa.clear()

    # A seção "Matrícula" sai do arquivo, mas a auditoria segura o trecho.
    escrever(tmp_path, "valores", {"Mensalidade": SECOES["Mensalidade"]})
    relatorio, embeddings = await ingerir(sessao, tmp_path)

    assert relatorio.orfaos == [("valores.md", "Matrícula")]
    assert relatorio.orfaos_zerados == 1
    assert await estado_dos_trechos(sessao) == {
        "Mensalidade": (True, "voyage-4-lite"),
        "Matrícula": (False, None),
    }
    assert vetorizacao_falsa == []
    assert embeddings.orfaos == 1
    assert await titulos_na_busca(sessao) == {"Mensalidade"}

    # Nas execuções seguintes o órfão continua listado e continua sem vetor.
    relatorio, _ = await ingerir(sessao, tmp_path)
    assert relatorio.orfaos == [("valores.md", "Matrícula")]
    assert relatorio.orfaos_zerados == 0
    assert vetorizacao_falsa == []
    assert (await estado_dos_trechos(sessao))["Matrícula"] == (False, None)


async def test_arquivo_removido_desativa_o_documento_e_a_volta_reativa(
    sessao: AsyncSession,
    tmp_path: Path,
    vetorizacao_falsa: list[list[str]],
    voyage_falsa: list[str],
) -> None:
    escrever(tmp_path, "valores", {"Mensalidade": SECOES["Mensalidade"]})
    politicas = escrever(tmp_path, "politicas", {"Cancelamento": "O cancelamento é por escrito."})
    conteudo_original = politicas.read_text(encoding="utf-8")
    await ingerir(sessao, tmp_path)
    vetorizacao_falsa.clear()

    politicas.unlink()
    relatorio, _ = await ingerir(sessao, tmp_path)

    assert relatorio.desativados == [
        ("politicas.md", "o arquivo não existe mais em knowledge-base/")
    ]
    assert relatorio.inativos == ["politicas.md"]
    assert await _indexar(sessao) == {"valores.md": True, "politicas.md": False}
    # O vetor fica: quem tira o trecho da busca é `indexar`, não a falta dele.
    assert (await estado_dos_trechos(sessao))["Cancelamento"] == (True, "voyage-4-lite")
    assert await titulos_na_busca(sessao) == {"Mensalidade"}

    # Rodar de novo não "desativa" outra vez, mas o documento segue listado.
    relatorio, _ = await ingerir(sessao, tmp_path)
    assert relatorio.desativados == []
    assert relatorio.inativos == ["politicas.md"]

    # O arquivo volta idêntico: mesmo hash, e ainda assim precisa reativar.
    politicas.write_text(conteudo_original, encoding="utf-8")
    relatorio, _ = await ingerir(sessao, tmp_path)

    assert relatorio.reativados == ["politicas.md"]
    assert relatorio.inativos == []
    assert await _indexar(sessao) == {"valores.md": True, "politicas.md": True}
    assert await titulos_na_busca(sessao) == {"Mensalidade", "Cancelamento"}
    assert vetorizacao_falsa == [], "o vetor estava guardado; nada a regerar"


async def test_indexar_false_no_cabecalho_desativa_e_true_reativa(
    sessao: AsyncSession,
    tmp_path: Path,
    vetorizacao_falsa: list[list[str]],
    voyage_falsa: list[str],
) -> None:
    escrever(tmp_path, "valores", SECOES)
    await ingerir(sessao, tmp_path)
    vetorizacao_falsa.clear()

    escrever(tmp_path, "valores", SECOES, indexar=False)
    relatorio, _ = await ingerir(sessao, tmp_path)

    assert relatorio.desativados == [("valores.md", "o arquivo agora tem indexar: false")]
    assert await _indexar(sessao) == {"valores.md": False}
    assert await titulos_na_busca(sessao) == set()

    # Volta a `true` com uma seção alterada: reativa e revetoriza só o que mudou.
    escrever(tmp_path, "valores", {**SECOES, "Matrícula": "A taxa passou a R$ 180,00."})
    relatorio, embeddings = await ingerir(sessao, tmp_path)

    assert relatorio.reativados == ["valores.md"]
    assert await _indexar(sessao) == {"valores.md": True}
    assert vetorizacao_falsa == [["Documento valores — Matrícula\n\nA taxa passou a R$ 180,00."]]
    assert embeddings.vetorizados == 1
    assert await titulos_na_busca(sessao) == {"Mensalidade", "Matrícula"}


async def test_trecho_de_documento_inativo_nao_e_vetorizado(
    sessao: AsyncSession, tmp_path: Path, vetorizacao_falsa: list[list[str]]
) -> None:
    arquivo = escrever(tmp_path, "valores", SECOES)
    arquivos = ingest.ler_base(tmp_path)
    await ingest.gravar(sessao, arquivos, forcar=False)  # texto gravado, ainda sem vetor
    arquivo.unlink()

    _, embeddings = await ingerir(sessao, tmp_path)

    assert vetorizacao_falsa == []
    assert embeddings.de_documentos_inativos == 2
    assert await estado_dos_trechos(sessao) == {
        "Mensalidade": (False, None),
        "Matrícula": (False, None),
    }


async def test_sem_embeddings_nao_chama_a_voyage(
    sessao: AsyncSession, tmp_path: Path, vetorizacao_falsa: list[list[str]]
) -> None:
    escrever(tmp_path, "valores", SECOES)
    arquivos = ingest.ler_base(tmp_path)
    await ingest.gravar(sessao, arquivos, forcar=False)

    embeddings = await ingest.vetorizar_trechos(sessao, arquivos, sem_embeddings=True)

    assert vetorizacao_falsa == []
    assert embeddings.pulados_por_flag == 2
    assert await estado_dos_trechos(sessao) == {
        "Mensalidade": (False, None),
        "Matrícula": (False, None),
    }


async def _indexar(sessao: AsyncSession) -> dict[str, bool]:
    linhas = await sessao.execute(select(Documento.arquivo, Documento.indexar))
    return {arquivo: indexar for arquivo, indexar in linhas}
