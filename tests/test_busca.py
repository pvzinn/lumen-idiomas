"""`POST /busca` e o serviço `buscar_trechos`.

A pergunta falsa vira sempre `vetor(0)`; cada trecho é criado a um ângulo
conhecido dela (ver `tests.fabricas`), então a ordem e a similaridade esperadas
saem de `cos(ângulo)`.
"""

import logging
import math

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.busca import MENSAGEM_INDISPONIVEL
from app.core.constants import MODELO_EMBEDDING_CONSULTAS
from app.embeddings import ErroEmbedding
from app.services.busca import buscar_trechos
from tests.fabricas import criar_documento, criar_trecho

# --- Com banco -----------------------------------------------------------------


async def test_resultados_vem_do_mais_similar_para_o_menos(
    cliente_com_banco: httpx.AsyncClient, sessao: AsyncSession, voyage_falsa: list[str]
) -> None:
    documento = await criar_documento(sessao, "valores")
    # Inseridos fora de ordem, para a ordem da resposta não ser a de inserção.
    for ordem, graus in enumerate([60, 0, 90, 30]):
        await criar_trecho(sessao, documento, f"a {graus} graus", graus, ordem=ordem)

    resposta = await cliente_com_banco.post("/busca", json={"pergunta": "quanto custa?", "k": 10})

    assert resposta.status_code == 200
    resultados = resposta.json()["resultados"]
    assert [r["titulo_secao"] for r in resultados] == [
        "a 0 graus",
        "a 30 graus",
        "a 60 graus",
        "a 90 graus",
    ]
    assert [r["posicao"] for r in resultados] == [1, 2, 3, 4]
    similaridades = [r["similaridade"] for r in resultados]
    assert similaridades == sorted(similaridades, reverse=True)
    esperadas = [math.cos(math.radians(g)) for g in (0, 30, 60, 90)]
    # Tolerância de float4: é a precisão com que o pgvector guarda o vetor.
    assert similaridades == pytest.approx(esperadas, abs=1e-6)


async def test_resposta_traz_origem_modelo_e_tempos(
    cliente_com_banco: httpx.AsyncClient, sessao: AsyncSession, voyage_falsa: list[str]
) -> None:
    documento = await criar_documento(sessao, "valores")
    trecho = await criar_trecho(sessao, documento, "Mensalidade", 30)

    resposta = await cliente_com_banco.post("/busca", json={"pergunta": "quanto custa?"})

    corpo = resposta.json()
    assert corpo["pergunta"] == "quanto custa?"
    assert corpo["modelo"] == MODELO_EMBEDDING_CONSULTAS
    assert set(corpo["tempo_ms"]) == {"embedding", "banco"}
    assert all(tempo >= 0 for tempo in corpo["tempo_ms"].values())
    assert corpo["resultados"] == [
        {
            "posicao": 1,
            "trecho_id": trecho.id,
            "arquivo": "valores.md",
            "titulo_documento": "Documento valores",
            "titulo_secao": "Mensalidade",
            "similaridade": pytest.approx(math.cos(math.radians(30)), abs=1e-6),
            "conteudo": "Conteúdo de Mensalidade.",
        }
    ]


async def test_k_limita_aos_mais_similares_e_o_padrao_e_cinco(
    cliente_com_banco: httpx.AsyncClient, sessao: AsyncSession, voyage_falsa: list[str]
) -> None:
    documento = await criar_documento(sessao, "valores")
    for ordem, graus in enumerate([70, 10, 50, 30, 80, 20, 60]):
        await criar_trecho(sessao, documento, f"a {graus} graus", graus, ordem=ordem)

    com_k = await cliente_com_banco.post("/busca", json={"pergunta": "x", "k": 2})
    sem_k = await cliente_com_banco.post("/busca", json={"pergunta": "x"})

    assert [r["titulo_secao"] for r in com_k.json()["resultados"]] == ["a 10 graus", "a 20 graus"]
    assert len(sem_k.json()["resultados"]) == 5


async def test_trecho_de_documento_com_indexar_false_nao_aparece(
    cliente_com_banco: httpx.AsyncClient, sessao: AsyncSession, voyage_falsa: list[str]
) -> None:
    ativo = await criar_documento(sessao, "ativo")
    inativo = await criar_documento(sessao, "inativo", indexar=False)
    await criar_trecho(sessao, ativo, "do documento ativo", 60)
    # Seria o primeiro colocado, se o documento estivesse na busca.
    await criar_trecho(sessao, inativo, "do documento inativo", 0)

    resposta = await cliente_com_banco.post("/busca", json={"pergunta": "x", "k": 20})

    assert [r["titulo_secao"] for r in resposta.json()["resultados"]] == ["do documento ativo"]


async def test_trecho_com_embedding_nulo_nao_aparece(
    cliente_com_banco: httpx.AsyncClient, sessao: AsyncSession, voyage_falsa: list[str]
) -> None:
    documento = await criar_documento(sessao, "valores")
    await criar_trecho(sessao, documento, "com vetor", 45, ordem=0)
    await criar_trecho(sessao, documento, "sem vetor", None, ordem=1)

    resposta = await cliente_com_banco.post("/busca", json={"pergunta": "x", "k": 20})

    assert [r["titulo_secao"] for r in resposta.json()["resultados"]] == ["com vetor"]


async def test_base_sem_trecho_vetorizado_devolve_lista_vazia(
    cliente_com_banco: httpx.AsyncClient, sessao: AsyncSession, voyage_falsa: list[str]
) -> None:
    documento = await criar_documento(sessao, "valores")
    await criar_trecho(sessao, documento, "sem vetor", None)

    resposta = await cliente_com_banco.post("/busca", json={"pergunta": "x"})

    assert resposta.status_code == 200
    assert resposta.json()["resultados"] == []


async def test_pergunta_no_limite_e_aceita_e_chega_sem_espacos_nas_pontas(
    cliente_com_banco: httpx.AsyncClient, sessao: AsyncSession, voyage_falsa: list[str]
) -> None:
    pergunta = "a" * 1000

    resposta = await cliente_com_banco.post("/busca", json={"pergunta": f"  {pergunta}\n"})

    assert resposta.status_code == 200
    assert resposta.json()["pergunta"] == pergunta
    assert voyage_falsa == [pergunta]


async def test_servico_pode_ser_chamado_sem_http(
    sessao: AsyncSession, voyage_falsa: list[str]
) -> None:
    """É assim que o script de avaliação da tarefa 3.4 vai usar a busca."""
    documento = await criar_documento(sessao, "valores")
    await criar_trecho(sessao, documento, "longe", 80, ordem=0)
    await criar_trecho(sessao, documento, "perto", 10, ordem=1)

    resultado = await buscar_trechos(sessao, "quanto custa?", k=1)

    assert [t.titulo_secao for t in resultado.trechos] == ["perto"]
    assert resultado.trechos[0].similaridade == pytest.approx(math.cos(math.radians(10)), abs=1e-6)
    assert resultado.modelo == MODELO_EMBEDDING_CONSULTAS


async def test_texto_da_pergunta_nao_vai_para_o_log(
    cliente_com_banco: httpx.AsyncClient,
    sessao: AsyncSession,
    voyage_falsa: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    documento = await criar_documento(sessao, "valores")
    await criar_trecho(sessao, documento, "Mensalidade", 30)
    caplog.set_level(logging.DEBUG)

    await cliente_com_banco.post("/busca", json={"pergunta": "meu cpf é 123.456.789-00", "k": 3})

    assert "busca: pergunta de 24 caracteres, k=3, 1 resultado(s)" in caplog.text
    assert "cpf" not in caplog.text
    assert "123.456" not in caplog.text


# --- Sem banco -----------------------------------------------------------------
# `cliente` puro: a sessão é a proibida, então estes testes também provam que a
# requisição é barrada antes de chegar ao banco.


@pytest.mark.parametrize("k", [0, -1, 21, 1.5, "muitos", None])
async def test_k_fora_do_intervalo_e_recusado(
    cliente: httpx.AsyncClient, voyage_falsa: list[str], k: object
) -> None:
    resposta = await cliente.post("/busca", json={"pergunta": "quanto custa?", "k": k})

    assert resposta.status_code == 422
    assert voyage_falsa == []


@pytest.mark.parametrize(
    "corpo",
    [
        {"pergunta": ""},
        {"pergunta": "   \n\t "},
        {"pergunta": "a" * 1001},
        {"pergunta": None},
        {"pergunta": 123},
        {"k": 3},
        {},
    ],
    ids=["vazia", "so_espacos", "1001_caracteres", "nula", "numero", "ausente", "corpo_vazio"],
)
async def test_pergunta_invalida_e_recusada(
    cliente: httpx.AsyncClient, voyage_falsa: list[str], corpo: dict[str, object]
) -> None:
    resposta = await cliente.post("/busca", json=corpo)

    assert resposta.status_code == 422
    assert voyage_falsa == []


async def test_falha_da_voyage_vira_503_sem_detalhe_interno(
    cliente: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def voyage_fora_do_ar(texto: str) -> list[float]:
        try:
            raise TimeoutError("api.voyageai.com não respondeu")
        except TimeoutError as causa:
            raise ErroEmbedding(f"Falha ao chamar a Voyage AI: {causa} [chave pa-123]") from causa

    monkeypatch.setattr("app.services.busca.gerar_embedding_consulta", voyage_fora_do_ar)
    caplog.set_level(logging.DEBUG)

    resposta = await cliente.post("/busca", json={"pergunta": "pergunta sigilosa"})

    assert resposta.status_code == 503
    assert resposta.json() == {"detail": MENSAGEM_INDISPONIVEL}
    assert "voyageai" not in resposta.text
    assert "pa-123" not in resposta.text
    # O log diz o que falhou, sem a mensagem do provedor e sem a pergunta.
    assert "falha ao gerar o embedding (TimeoutError)" in caplog.text
    assert "pa-123" not in caplog.text
    assert "sigilosa" not in caplog.text
