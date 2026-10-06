"""Ingestão da base de conhecimento: `knowledge-base/*.md` → `documentos` e `trechos`.

Uso:

    python -m scripts.ingest                 # processa tudo: texto + embeddings
    python -m scripts.ingest --forcar         # reprocessa o texto, mesmo com hash igual
    python -m scripts.ingest --sem-embeddings # só parsing e reconciliação, sem chamar a Voyage

O script roda em três fases, em duas transações separadas. Primeiro lê e
valida *todos* os arquivos, sem tocar no banco; qualquer erro de cabeçalho ou
de estrutura aborta a execução listando todos os problemas de uma vez. Depois
grava texto e reconcilia trechos, numa transação — ou a base inteira entra, ou
nada muda. Só então, numa segunda transação, gera e grava os embeddings dos
trechos que precisam.

As duas últimas fases são transações separadas, e não uma só, de propósito: a
chamada à Voyage é uma chamada de rede que pode demorar ou falhar, e mantê-la
dentro da mesma transação que grava o texto seguraria locks do Postgres pelo
tempo da chamada. Separado, um problema na Voyage não impede o texto —
sempre rápido e local — de ser gravado; rodar o script de novo tenta só o que
falta.

O que fica fora da busca
------------------------

A busca (`app.services.busca`) filtra por duas condições e nada mais:
`documentos.indexar = true` e `trechos.embedding IS NOT NULL`. Cabe a este
script manter as duas colunas dizendo a verdade:

- **Trecho órfão** — seção que saiu do arquivo, mas cujo DELETE a FK de
  auditoria (`mensagem_trechos`) barrou. O registro fica, porque a auditoria
  aponta para ele; o vetor é zerado, porque a auditoria guarda o id e a
  similaridade, não o vetor. A vetorização pula órfãos, então eles não
  ganham vetor de novo.
- **Documento sem arquivo indexável** — o arquivo foi removido de
  `knowledge-base/` ou passou a ter `indexar: false`. O banco recebe
  `indexar = false`; os trechos e vetores ficam intactos. Se o arquivo voltar
  com `indexar: true`, o banco volta a `true` e, se o conteúdo não mudou,
  nenhum vetor precisa ser regerado.

Decisões de parsing
-------------------

- **Cabeçalho YAML**: bloco entre `---` na primeira linha e o `---` seguinte,
  lido com `yaml.safe_load`. Campos a mais (o guia tem `tipo: interno`) são
  ignorados; campos a menos são erro. `indexar` é conferido *antes* dos demais:
  um arquivo com `indexar: false` é pulado sem exigir `topico` e `publico` — o
  próprio guia de escrita não os tem, e não faz sentido reprovar um documento
  por lhe faltar metadado de recuperação quando ele não será recuperado.
- **Trecho = seção `##`**: só título ATX de nível 2 exato abre trecho. `#`
  (título do documento) e o texto antes do primeiro `##` ficam de fora.
- **`###` e abaixo** não abrem trecho: continuam dentro da seção `##` que os
  contém, como subtítulos. Quebrar em `###` produziria trechos menores que o
  mínimo de 80 palavras do guia e sem o contexto do `##` acima.
- **Blocos de código cercados** (```` ``` ```` ou `~~~`): o conteúdo é opaco.
  Um `## ` ou `---` dentro do bloco não abre seção nem é removido. Bloco aberto
  e não fechado é erro — pelo CommonMark ele iria até o fim do arquivo e
  engoliria em silêncio todas as seções seguintes.
- **Tabelas** entram como estão, em markdown. O guia (R7) exige prosa antes de
  toda tabela; a sintaxe `|` preserva o cabeçalho junto das linhas, o que é o
  máximo de contexto que a tabela pode carregar sozinha.
- **Réguas horizontais (`---`)**: os arquivos as usam como separador *entre*
  seções. As que ficam no fim de uma seção são removidas; uma régua no meio da
  seção é conteúdo e fica. Títulos setext (texto sublinhado com `---` ou `===`)
  não são reconhecidos como título: a base usa só ATX.
- **Títulos repetidos no mesmo arquivo** são erro: a reconciliação casa trecho
  do banco com seção do arquivo pelo título, e dois títulos iguais tornariam a
  correspondência ambígua.
- **Contagem de palavras**: sobre o conteúdo, sem o título. Conta como palavra
  todo token separado por espaço que tenha ao menos uma letra ou dígito — assim
  `|`, `---|---` e marcadores de lista não inflam a contagem de tabelas.
"""

import argparse
import asyncio
import hashlib
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import EMBEDDING_DIM, MODELO_EMBEDDING_DOCUMENTOS
from app.db.session import SessionLocal, engine
from app.embeddings import ErroEmbedding, gerar_embeddings_documentos
from app.models import Documento, PublicoDocumento, TopicoDocumento, Trecho

# Teto de palavras por seção definido no guia de escrita (R6).
LIMITE_PALAVRAS = 250

# Limites de tamanho das colunas em `app.models.conhecimento`. Conferidos na
# validação para que o erro aponte o arquivo, e não chegue como erro do banco.
MAX_IDENTIFICADOR = 64
MAX_TITULO = 200

# Chave do `pg_advisory_xact_lock`: duas ingestões simultâneas reconciliariam
# os mesmos trechos ao mesmo tempo. O valor é arbitrário, só precisa ser fixo.
_CHAVE_LOCK = 0x4C554D454E  # "LUMEN"

# Violação de chave estrangeira no Postgres.
_SQLSTATE_FK = "23503"

_CAMPOS_OBRIGATORIOS = ("id", "titulo", "topico", "publico", "indexar", "atualizado_em")
_IDENTIFICADOR = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TITULO_H2 = re.compile(r"^##(?!#)[ \t]+(?P<titulo>.+?)[ \t]*$")
# Sequência de fechamento opcional do ATX (`## Título ##`). Exige espaço antes,
# como o CommonMark, para não comer o `#` de um título como "C#".
_FECHO_ATX = re.compile(r"[ \t]+#+$")
_CERCA = re.compile(r"^ {0,3}(?P<cerca>`{3,}|~{3,})")
_REGUA = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")


class ErroValidacao(Exception):
    """Problema num arquivo da base. A mensagem já diz qual arquivo e o quê."""


# --- Leitura e parsing -------------------------------------------------------


@dataclass(frozen=True)
class Secao:
    titulo: str
    conteudo: str
    ordem: int


@dataclass(frozen=True)
class Arquivo:
    """Um arquivo `.md` lido e validado, pronto para gravar."""

    nome: str
    hash_conteudo: str
    indexar: bool
    # Os campos abaixo só são preenchidos quando `indexar` é verdadeiro.
    identificador: str = ""
    titulo: str = ""
    topico: TopicoDocumento | None = None
    publico: tuple[PublicoDocumento, ...] = ()
    atualizado_em: date | None = None
    secoes: tuple[Secao, ...] = ()


def ler_arquivo(caminho: Path) -> Arquivo:
    # Normaliza BOM e fim de linha antes do hash: um `git checkout` com
    # autocrlf mudaria os bytes sem mudar o conteúdo, e o documento seria
    # reprocessado à toa.
    texto = caminho.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    hash_conteudo = hashlib.sha256(texto.encode("utf-8")).hexdigest()

    cabecalho, corpo, linha_corpo = _separar_cabecalho(caminho.name, texto)

    if "indexar" not in cabecalho:
        raise ErroValidacao(f"{caminho.name}: campo obrigatório ausente no cabeçalho: indexar")
    indexar = cabecalho["indexar"]
    if not isinstance(indexar, bool):
        raise ErroValidacao(
            f"{caminho.name}: campo 'indexar' deve ser true ou false, veio {indexar!r}"
        )
    if not indexar:
        return Arquivo(nome=caminho.name, hash_conteudo=hash_conteudo, indexar=False)

    ausentes = [c for c in _CAMPOS_OBRIGATORIOS if cabecalho.get(c) in (None, "", [])]
    if ausentes:
        raise ErroValidacao(
            f"{caminho.name}: campo(s) obrigatório(s) ausente(s) ou vazio(s) no cabeçalho: "
            + ", ".join(ausentes)
        )

    # Cada validação roda mesmo que a anterior tenha falhado: quem corrige o
    # arquivo vê todos os problemas dele de uma vez, não um por execução.
    erros: list[str] = []
    nome = caminho.name
    identificador = _coletar(erros, lambda: _validar_identificador(nome, cabecalho["id"]))
    titulo = _coletar(
        erros, lambda: _validar_texto(nome, "titulo", cabecalho["titulo"], MAX_TITULO)
    )
    topico = _coletar(erros, lambda: _validar_topico(nome, cabecalho["topico"]))
    publico = _coletar(erros, lambda: _validar_publico(nome, cabecalho["publico"]))
    atualizado_em = _coletar(erros, lambda: _validar_data(nome, cabecalho["atualizado_em"]))
    secoes = _coletar(erros, lambda: extrair_secoes(nome, corpo, linha_corpo))
    if secoes == []:
        erros.append(f"{nome}: nenhuma seção '##' encontrada")
    if erros:
        raise ErroValidacao("\n".join(erros))

    assert identificador and titulo and topico and publico and atualizado_em and secoes
    return Arquivo(
        nome=nome,
        hash_conteudo=hash_conteudo,
        indexar=True,
        identificador=identificador,
        titulo=titulo,
        topico=topico,
        publico=publico,
        atualizado_em=atualizado_em,
        secoes=tuple(secoes),
    )


def _coletar[T](erros: list[str], validacao: Callable[[], T]) -> T | None:
    try:
        return validacao()
    except ErroValidacao as erro:
        erros.append(str(erro))
        return None


def _separar_cabecalho(nome: str, texto: str) -> tuple[dict[str, Any], str, int]:
    """Devolve o cabeçalho, o corpo e o número da linha do arquivo onde o corpo começa."""
    linhas = texto.split("\n")
    if not linhas or linhas[0].strip() != "---":
        raise ErroValidacao(f"{nome}: cabeçalho YAML ausente (o arquivo deve começar com '---')")
    try:
        fim = next(i for i, linha in enumerate(linhas[1:], start=1) if linha.strip() == "---")
    except StopIteration:
        raise ErroValidacao(f"{nome}: cabeçalho YAML aberto com '---' e nunca fechado") from None

    try:
        dados = yaml.safe_load("\n".join(linhas[1:fim]))
    except yaml.YAMLError as erro:
        raise ErroValidacao(f"{nome}: cabeçalho YAML inválido: {erro}") from None
    if not isinstance(dados, dict):
        raise ErroValidacao(f"{nome}: cabeçalho YAML deve ser um mapeamento de campos")
    return dados, "\n".join(linhas[fim + 1 :]), fim + 2


def extrair_secoes(nome: str, corpo: str, primeira_linha: int = 1) -> list[Secao]:
    """Quebra o corpo do markdown em seções `##`. Ver as decisões no topo do módulo."""
    secoes: list[Secao] = []
    titulo_atual: str | None = None
    linhas_atuais: list[str] = []
    cerca_aberta: str | None = None
    linha_cerca = 0

    def fechar_secao() -> None:
        if titulo_atual is not None:
            secoes.append(Secao(titulo_atual, _limpar_conteudo(linhas_atuais), len(secoes)))

    for numero, linha in enumerate(corpo.split("\n"), start=primeira_linha):
        if cerca_aberta is not None:
            # Fecha com o mesmo caractere, em quantidade igual ou maior.
            fecho = linha.strip()
            if fecho.startswith(cerca_aberta) and set(fecho) == {cerca_aberta[0]}:
                cerca_aberta = None
            if titulo_atual is not None:
                linhas_atuais.append(linha)
            continue

        if m := _CERCA.match(linha):
            cerca_aberta, linha_cerca = m.group("cerca"), numero
            if titulo_atual is not None:
                linhas_atuais.append(linha)
            continue

        if m := _TITULO_H2.match(linha):
            fechar_secao()
            titulo_atual = _FECHO_ATX.sub("", m.group("titulo"))
            linhas_atuais = []
            continue

        if titulo_atual is not None:
            linhas_atuais.append(linha)

    if cerca_aberta is not None:
        raise ErroValidacao(
            f"{nome}: bloco de código aberto com '{cerca_aberta}' na linha {linha_cerca} "
            "nunca foi fechado"
        )
    fechar_secao()

    vistos: set[str] = set()
    for secao in secoes:
        if len(secao.titulo) > MAX_TITULO:
            raise ErroValidacao(
                f"{nome}: título de seção com mais de {MAX_TITULO} caracteres: {secao.titulo!r}"
            )
        if secao.titulo in vistos:
            raise ErroValidacao(f"{nome}: título de seção repetido: {secao.titulo!r}")
        vistos.add(secao.titulo)
    return secoes


def _limpar_conteudo(linhas: list[str]) -> str:
    """Tira linhas vazias das pontas e as réguas `---` do fim da seção."""
    fim = len(linhas)
    while fim and (not linhas[fim - 1].strip() or _REGUA.match(linhas[fim - 1])):
        fim -= 1
    inicio = 0
    while inicio < fim and not linhas[inicio].strip():
        inicio += 1
    return "\n".join(linha.rstrip() for linha in linhas[inicio:fim])


def contar_palavras(conteudo: str) -> int:
    return sum(1 for token in conteudo.split() if any(c.isalnum() for c in token))


# --- Validação dos campos do cabeçalho -----------------------------------------


def _validar_texto(nome: str, campo: str, valor: Any, maximo: int) -> str:
    if not isinstance(valor, str):
        raise ErroValidacao(f"{nome}: campo '{campo}' deve ser texto, veio {valor!r}")
    texto = valor.strip()
    if len(texto) > maximo:
        raise ErroValidacao(f"{nome}: campo '{campo}' passa de {maximo} caracteres")
    return texto


def _validar_identificador(nome: str, valor: Any) -> str:
    identificador = _validar_texto(nome, "id", valor, MAX_IDENTIFICADOR)
    if not _IDENTIFICADOR.match(identificador):
        raise ErroValidacao(
            f"{nome}: campo 'id' deve ser minúsculo com hífens (ex.: valores-e-pagamento), "
            f"veio {identificador!r}"
        )
    return identificador


def _validar_topico(nome: str, valor: Any) -> TopicoDocumento:
    try:
        return TopicoDocumento(valor)
    except ValueError:
        validos = ", ".join(t.value for t in TopicoDocumento)
        raise ErroValidacao(
            f"{nome}: campo 'topico' inválido: {valor!r} (válidos: {validos})"
        ) from None


def _validar_publico(nome: str, valor: Any) -> tuple[PublicoDocumento, ...]:
    if not isinstance(valor, list):
        raise ErroValidacao(f"{nome}: campo 'publico' deve ser lista, veio {valor!r}")
    try:
        return tuple(PublicoDocumento(p) for p in valor)
    except ValueError:
        validos = ", ".join(p.value for p in PublicoDocumento)
        raise ErroValidacao(
            f"{nome}: campo 'publico' tem valor inválido em {valor!r} (válidos: {validos})"
        ) from None


def _validar_data(nome: str, valor: Any) -> date:
    # O YAML já converte `2026-08-11` sem aspas em `date`. `datetime` é
    # subclasse de `date`, então é recusado primeiro: data com hora seria
    # precisão que o campo não tem.
    if isinstance(valor, datetime):
        raise ErroValidacao(f"{nome}: campo 'atualizado_em' deve ser só data, sem hora")
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            pass
    raise ErroValidacao(f"{nome}: campo 'atualizado_em' deve estar no formato AAAA-MM-DD")


def ler_base(diretorio: Path) -> list[Arquivo]:
    """Lê e valida todos os arquivos. Reúne todos os erros antes de falhar."""
    if not diretorio.is_dir():
        raise ErroValidacao(f"diretório da base não encontrado: {diretorio}")

    arquivos: list[Arquivo] = []
    erros: list[str] = []
    for caminho in sorted(diretorio.glob("*.md")):
        try:
            arquivos.append(ler_arquivo(caminho))
        except ErroValidacao as erro:
            erros.append(str(erro))

    por_identificador: dict[str, str] = {}
    for arquivo in arquivos:
        if not arquivo.indexar:
            continue
        if outro := por_identificador.get(arquivo.identificador):
            erros.append(f"{arquivo.nome}: id {arquivo.identificador!r} já usado por {outro}")
        por_identificador[arquivo.identificador] = arquivo.nome

    if erros:
        raise ErroValidacao("\n".join(erros))
    return arquivos


# --- Gravação ------------------------------------------------------------------


@dataclass
class Relatorio:
    processados: list[str] = field(default_factory=list)
    inalterados: list[str] = field(default_factory=list)
    pulados: list[tuple[str, str]] = field(default_factory=list)
    inseridos: int = 0
    atualizados: int = 0
    reposicionados: int = 0
    removidos: int = 0
    # (arquivo, título da seção) de trechos no banco cuja seção não existe mais
    # no arquivo — sobraram de um DELETE barrado pela FK de auditoria, nesta
    # execução ou numa anterior. Levantados a cada execução, e não só quando o
    # documento é reprocessado: senão o órfão sumiria do relatório na execução
    # seguinte, com hash inalterado, continuando no banco.
    orfaos: list[tuple[str, str]] = field(default_factory=list)
    # Quantos órfãos ainda tinham vetor e o perderam nesta execução.
    orfaos_zerados: int = 0
    # Transições de `documentos.indexar` nesta execução: (arquivo, motivo) dos
    # que foram a `false`, e arquivos dos que voltaram a `true`.
    desativados: list[tuple[str, str]] = field(default_factory=list)
    reativados: list[str] = field(default_factory=list)
    # Estado, não transição: todos os documentos com `indexar = false` no banco
    # ao final. Listado sempre, pelo mesmo motivo dos órfãos.
    inativos: list[str] = field(default_factory=list)


async def gravar(session: AsyncSession, arquivos: Sequence[Arquivo], forcar: bool) -> Relatorio:
    relatorio = Relatorio()
    await session.execute(text("SELECT pg_advisory_xact_lock(:chave)"), {"chave": _CHAVE_LOCK})

    for arquivo in arquivos:
        if not arquivo.indexar:
            relatorio.pulados.append((arquivo.nome, "indexar: false no cabeçalho"))
            continue

        documento = await session.scalar(
            select(Documento).where(Documento.identificador == arquivo.identificador)
        )
        if documento is None:
            # O `id` do cabeçalho é a chave de correspondência. Se o nome do
            # arquivo já existe no banco com outro `id`, alguém mudou o `id` —
            # o guia proíbe, e decidir se é o mesmo documento não cabe ao script.
            ocupante = await session.scalar(
                select(Documento.identificador).where(Documento.arquivo == arquivo.nome)
            )
            if ocupante is not None:
                raise ErroValidacao(
                    f"{arquivo.nome}: o banco já tem este arquivo com id {ocupante!r}, mas o "
                    f"cabeçalho agora diz {arquivo.identificador!r}. O id não deve mudar depois "
                    "de criado; corrija o cabeçalho ou remova o documento antigo manualmente."
                )
            documento = Documento(identificador=arquivo.identificador)
            session.add(documento)
        else:
            if not documento.indexar:
                # O arquivo voltou (ou voltou a ter `indexar: true`). Feito
                # antes do teste de hash: um arquivo removido e restaurado
                # idêntico tem o mesmo hash, e sem isto ficaria inativo para
                # sempre por "não ter mudado".
                documento.indexar = True
                relatorio.reativados.append(arquivo.nome)
            if (
                not forcar
                and documento.hash_conteudo == arquivo.hash_conteudo
                and documento.arquivo == arquivo.nome
            ):
                relatorio.inalterados.append(arquivo.nome)
                continue

        _aplicar_metadados(documento, arquivo)
        await session.flush()
        await _reconciliar_trechos(session, documento, arquivo, relatorio)
        relatorio.processados.append(arquivo.nome)

    await _tratar_orfaos(session, arquivos, relatorio)
    await _desativar_documentos_sem_arquivo(session, arquivos, relatorio)
    return relatorio


def _aplicar_metadados(documento: Documento, arquivo: Arquivo) -> None:
    assert arquivo.topico is not None and arquivo.atualizado_em is not None
    documento.arquivo = arquivo.nome
    documento.titulo = arquivo.titulo
    documento.topico = arquivo.topico
    documento.publico = list(arquivo.publico)
    documento.indexar = arquivo.indexar
    documento.atualizado_em = arquivo.atualizado_em
    documento.hash_conteudo = arquivo.hash_conteudo


async def _reconciliar_trechos(
    session: AsyncSession, documento: Documento, arquivo: Arquivo, relatorio: Relatorio
) -> None:
    """Casa trechos do banco com seções do arquivo por título, sem apagar em massa.

    `mensagem_trechos.trecho_id` é ON DELETE RESTRICT: um trecho já citado numa
    resposta não pode sumir. Por isso cada trecho mantém seu `id` enquanto a
    seção existir, e só as seções removidas do arquivo são apagadas — uma a
    uma, cada DELETE em seu próprio SAVEPOINT, para que um bloqueio da FK não
    aborte a transação inteira.
    """
    existentes = list(
        await session.scalars(select(Trecho).where(Trecho.documento_id == documento.id))
    )
    por_titulo = {t.titulo: t for t in existentes}
    if len(por_titulo) != len(existentes):
        raise ErroValidacao(
            f"{arquivo.nome}: o banco tem dois trechos com o mesmo título neste documento; "
            "a correspondência por título ficaria ambígua. Corrija manualmente."
        )

    # Posição final de cada trecho que continua existindo.
    destino: dict[int, int] = {}
    novos: list[Secao] = []
    for secao in arquivo.secoes:
        trecho = por_titulo.pop(secao.titulo, None)
        if trecho is None:
            novos.append(secao)
            continue
        if trecho.conteudo != secao.conteudo:
            trecho.conteudo = secao.conteudo
            # Texto novo, vetor velho: zerar sinaliza que o embedding precisa
            # ser regerado e tira o trecho da busca vetorial até lá.
            trecho.embedding = None
            trecho.embedding_modelo = None
            relatorio.atualizados += 1
        elif trecho.ordem != secao.ordem:
            relatorio.reposicionados += 1
        destino[trecho.id] = secao.ordem

    # Seções que sumiram do arquivo.
    orfaos_no_documento = 0
    for trecho in sorted(por_titulo.values(), key=lambda t: t.ordem):
        try:
            async with session.begin_nested():
                await session.execute(delete(Trecho).where(Trecho.id == trecho.id))
        except IntegrityError as erro:
            if _sqlstate(erro) != _SQLSTATE_FK:
                raise
            # Fica no banco, depois das seções atuais, para não ocupar a
            # `ordem` de uma seção viva (UNIQUE documento_id, ordem). O vetor
            # dele é zerado em `_tratar_orfaos`, que cobre também os órfãos
            # de execuções anteriores.
            destino[trecho.id] = len(arquivo.secoes) + orfaos_no_documento
            orfaos_no_documento += 1
        else:
            session.expunge(trecho)
            existentes.remove(trecho)
            relatorio.removidos += 1

    # Reordenar sem violar UNIQUE(documento_id, ordem), que o Postgres confere
    # linha a linha. Primeiro quem muda de posição vai para uma faixa livre,
    # acima de qualquer ordem atual ou final; depois, para a posição final.
    # Em cada passo nenhum destino está ocupado, qualquer que seja a ordem em
    # que os UPDATEs forem emitidos.
    mudam = [t for t in existentes if t.ordem != destino[t.id]]
    if mudam:
        faixa_livre = max([t.ordem for t in existentes] + list(destino.values())) + 1
        for deslocamento, trecho in enumerate(mudam):
            trecho.ordem = faixa_livre + deslocamento
        await session.flush()
        for trecho in mudam:
            trecho.ordem = destino[trecho.id]
        await session.flush()

    for secao in novos:
        session.add(
            Trecho(
                documento_id=documento.id,
                titulo=secao.titulo,
                conteudo=secao.conteudo,
                ordem=secao.ordem,
                embedding=None,
            )
        )
        relatorio.inseridos += 1
    await session.flush()


def _sqlstate(erro: IntegrityError) -> str | None:
    # O adaptador asyncpg do SQLAlchemy expõe o código em `sqlstate` (ou
    # `pgcode`, conforme a versão).
    orig = erro.orig
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


async def _tratar_orfaos(
    session: AsyncSession, arquivos: Iterable[Arquivo], relatorio: Relatorio
) -> None:
    """Lista os trechos órfãos e tira da busca os que ainda têm vetor.

    Roda sobre todos os documentos indexáveis, e não só sobre os reprocessados
    nesta execução: um órfão criado antes desta regra existir, num documento
    de hash inalterado, também precisa perder o vetor.
    """
    secoes_por_arquivo = {a.nome: {s.titulo for s in a.secoes} for a in arquivos if a.indexar}
    linhas = await session.execute(
        select(Trecho, Documento.arquivo)
        .join(Trecho.documento)
        .where(Documento.arquivo.in_(secoes_por_arquivo))
        .order_by(Documento.arquivo, Trecho.ordem)
    )
    for trecho, nome in linhas:
        if trecho.titulo in secoes_por_arquivo[nome]:
            continue
        relatorio.orfaos.append((nome, trecho.titulo))
        if trecho.embedding is not None or trecho.embedding_modelo is not None:
            trecho.embedding = None
            trecho.embedding_modelo = None
            relatorio.orfaos_zerados += 1
    await session.flush()


async def _desativar_documentos_sem_arquivo(
    session: AsyncSession, arquivos: Iterable[Arquivo], relatorio: Relatorio
) -> None:
    """Grava `indexar = false` nos documentos cujo arquivo sumiu ou deixou de ser indexável.

    Não apaga: apagar o documento cascatearia para os trechos e esbarraria na
    FK de auditoria. Os trechos e seus vetores ficam como estão — quem os tira
    da busca é o filtro por `documentos.indexar`. A volta é em `gravar`.
    """
    indexaveis = {a.nome for a in arquivos if a.indexar}
    nao_indexaveis = {a.nome for a in arquivos if not a.indexar}
    for documento in await session.scalars(select(Documento).order_by(Documento.arquivo)):
        if documento.arquivo in indexaveis:
            continue
        if documento.indexar:
            documento.indexar = False
            motivo = (
                "o arquivo agora tem indexar: false"
                if documento.arquivo in nao_indexaveis
                else "o arquivo não existe mais em knowledge-base/"
            )
            relatorio.desativados.append((documento.arquivo, motivo))
        relatorio.inativos.append(documento.arquivo)
    await session.flush()


# --- Embeddings ------------------------------------------------------------------


@dataclass
class RelatorioEmbeddings:
    vetorizados: int = 0
    tokens_usados: int = 0
    # Trechos com embedding ausente ou de modelo antigo que não foram
    # vetorizados nesta execução, e por quê.
    orfaos: int = 0
    de_documentos_inativos: int = 0
    pulados_por_flag: int = 0
    erro: str | None = None


async def selecionar_trechos_para_vetorizar(
    session: AsyncSession, arquivos: Sequence[Arquivo], relatorio: RelatorioEmbeddings
) -> list[tuple[Trecho, str]]:
    """Trechos com embedding ausente ou gerado por outro modelo, com o texto a enviar.

    Órfãos e trechos de documentos inativos ficam de fora — vetor para trecho
    que a busca não devolve é chamada de API jogada fora — e são contados em
    `relatorio`, porque o motivo de não terem vetor importa para quem lê.
    """
    secoes_por_arquivo = {a.nome: {s.titulo for s in a.secoes} for a in arquivos if a.indexar}

    linhas = await session.execute(
        select(Trecho, Documento.arquivo, Documento.titulo, Documento.indexar)
        .join(Trecho.documento)
        .where(
            or_(
                Trecho.embedding.is_(None),
                # `IS DISTINCT FROM`, não `!=`: em SQL, `NULL != 'x'` é NULL
                # (nem verdadeiro nem falso), então um `!=` comum deixaria de
                # fora um trecho com embedding presente mas `embedding_modelo`
                # nulo — que não deveria existir, mas se existisse por algum
                # motivo, o objetivo desta condição é justamente pegá-lo.
                Trecho.embedding_modelo.is_distinct_from(MODELO_EMBEDDING_DOCUMENTOS),
            )
        )
        .order_by(Documento.arquivo, Trecho.ordem)
    )

    candidatos: list[tuple[Trecho, str]] = []
    for trecho, arquivo_nome, titulo_documento, indexar in linhas:
        if not indexar:
            relatorio.de_documentos_inativos += 1
        elif trecho.titulo not in secoes_por_arquivo.get(arquivo_nome, set()):
            # Se ganhasse vetor aqui, voltaria para a busca — exatamente o
            # que `_tratar_orfaos` acabou de desfazer.
            relatorio.orfaos += 1
        else:
            texto = f"{titulo_documento} — {trecho.titulo}\n\n{trecho.conteudo}"
            candidatos.append((trecho, texto))
    return candidatos


async def vetorizar_trechos(
    session: AsyncSession, arquivos: Sequence[Arquivo], sem_embeddings: bool
) -> RelatorioEmbeddings:
    relatorio = RelatorioEmbeddings()
    # Mesma trava da gravação de texto: duas execuções concorrentes não devem
    # selecionar os mesmos trechos e pagar duas vezes pela mesma vetorização.
    await session.execute(text("SELECT pg_advisory_xact_lock(:chave)"), {"chave": _CHAVE_LOCK})

    candidatos = await selecionar_trechos_para_vetorizar(session, arquivos, relatorio)
    if not candidatos:
        return relatorio

    if sem_embeddings:
        relatorio.pulados_por_flag = len(candidatos)
        return relatorio

    try:
        resultado = await gerar_embeddings_documentos([texto for _, texto in candidatos])
    except ErroEmbedding as erro:
        relatorio.erro = str(erro)
        return relatorio

    for (trecho, _texto), vetor in zip(candidatos, resultado.vetores, strict=True):
        trecho.embedding = vetor
        trecho.embedding_modelo = MODELO_EMBEDDING_DOCUMENTOS
    await session.flush()

    relatorio.vetorizados = len(candidatos)
    relatorio.tokens_usados = resultado.tokens_usados
    return relatorio


# --- Relatório -----------------------------------------------------------------


async def imprimir_relatorio(
    session: AsyncSession, relatorio: Relatorio, embeddings: RelatorioEmbeddings
) -> None:
    linhas = (
        await session.execute(
            select(Documento.arquivo, Trecho.titulo, Trecho.conteudo)
            .select_from(Trecho)
            .join(Trecho.documento)
            .order_by(Documento.arquivo, Trecho.ordem)
        )
    ).all()
    sem_embedding = await session.scalar(
        select(func.count()).select_from(Trecho).where(Trecho.embedding.is_(None))
    )
    contagens = [
        (arquivo, titulo, contar_palavras(conteudo)) for arquivo, titulo, conteudo in linhas
    ]

    print("\n=== Ingestão da base de conhecimento ===\n")
    print("Documentos")
    print(f"  processados: {len(relatorio.processados)}")
    for nome in relatorio.processados:
        print(f"    - {nome}")
    print(f"  inalterados: {len(relatorio.inalterados)} (hash igual, não reprocessados)")
    for nome in relatorio.inalterados:
        print(f"    - {nome}")
    print(f"  pulados:     {len(relatorio.pulados)}")
    for nome, motivo in relatorio.pulados:
        print(f"    - {nome}: {motivo}")
    print(f"  desativados: {len(relatorio.desativados)} (indexar passou a false no banco)")
    for nome, motivo in relatorio.desativados:
        print(f"    - {nome}: {motivo}")
    print(f"  reativados:  {len(relatorio.reativados)} (indexar voltou a true no banco)")
    for nome in relatorio.reativados:
        print(f"    - {nome}")
    if relatorio.inativos:
        print(f"  inativos no banco, fora da busca: {len(relatorio.inativos)}")
        for nome in relatorio.inativos:
            print(f"    - {nome}")

    print("\nTrechos")
    print(f"  inseridos:      {relatorio.inseridos}")
    print(f"  atualizados:    {relatorio.atualizados} (conteúdo mudou; embedding zerado)")
    print(f"  reposicionados: {relatorio.reposicionados} (só a ordem mudou; embedding mantido)")
    print(f"  removidos:      {relatorio.removidos}")
    print(f"  total no banco: {len(contagens)} ({sem_embedding} sem embedding)")

    if contagens:
        menor = min(contagens, key=lambda c: c[2])
        maior = max(contagens, key=lambda c: c[2])
        media = sum(c[2] for c in contagens) / len(contagens)
        print("\nPalavras por trecho (conteúdo, sem o título)")
        print(f"  menor: {menor[2]:>4}  {menor[0]} › {menor[1]}")
        print(f"  maior: {maior[2]:>4}  {maior[0]} › {maior[1]}")
        print(f"  média: {media:>6.1f}")

    acima = [c for c in contagens if c[2] > LIMITE_PALAVRAS]
    print(
        f"\nTrechos acima de {LIMITE_PALAVRAS} palavras (teto do guia de escrita, R6): {len(acima)}"
    )
    for arquivo, titulo, palavras in sorted(acima, key=lambda c: -c[2]):
        print(f"  {palavras:>4}  {arquivo} › {titulo}")

    if relatorio.orfaos:
        print(
            f"\n⚠ Trechos órfãos: {len(relatorio.orfaos)} — a seção saiu do arquivo, mas o "
            "trecho já foi usado numa resposta (FK de auditoria) e não pôde ser apagado."
        )
        print(
            "  Seguem no banco para a auditoria, mas fora da busca: o vetor é zerado "
            f"({relatorio.orfaos_zerados} nesta execução)."
        )
        for arquivo, titulo in relatorio.orfaos:
            print(f"    - {arquivo} › {titulo}")
        print("  Resolvida a referência em mensagem_trechos, `--forcar` tenta o DELETE de novo.")

    # `sem_embedding` é o estado do banco (`embedding IS NULL`). Os motivos
    # abaixo explicam essa contagem, mas não são um extrato exato dela: depois
    # de uma troca de modelo, um trecho "não vetorizado" pode ter vetor — o do
    # modelo antigo.
    print("\nEmbeddings")
    print(f"  vetorizados nesta execução: {embeddings.vetorizados}")
    print(f"  tokens consumidos: {embeddings.tokens_usados}")
    print(f"  modelo: {MODELO_EMBEDDING_DOCUMENTOS} (dimensão {EMBEDDING_DIM})")
    print(f"  sem embedding, no banco, ao final desta execução: {sem_embedding}")
    if embeddings.orfaos:
        print(f"    - {embeddings.orfaos} órfão(s), não vetorizado(s) de propósito")
    if embeddings.de_documentos_inativos:
        print(
            f"    - {embeddings.de_documentos_inativos} de documento(s) inativo(s), "
            "não vetorizado(s) de propósito"
        )
    if embeddings.pulados_por_flag:
        print(
            f"    - {embeddings.pulados_por_flag} elegível(is), pulado(s) nesta execução "
            "por causa de --sem-embeddings"
        )
    if embeddings.erro:
        print(f"    - geração de embeddings falhou nesta execução: {embeddings.erro}")
    print()


# --- Entrada -------------------------------------------------------------------


async def executar(diretorio: Path, forcar: bool, sem_embeddings: bool) -> int:
    try:
        arquivos = ler_base(diretorio)
    except ErroValidacao as erro:
        print(
            f"Ingestão abortada; nada foi gravado. Problemas encontrados:\n{erro}", file=sys.stderr
        )
        return 1

    try:
        async with SessionLocal() as session:
            try:
                async with session.begin():
                    relatorio = await gravar(session, arquivos, forcar)
            except ErroValidacao as erro:
                print(f"Ingestão abortada; nada foi gravado.\n{erro}", file=sys.stderr)
                return 1

            # Transação separada da gravação de texto — ver o docstring do
            # módulo. O texto acima já está gravado mesmo que isto falhe.
            async with session.begin():
                embeddings = await vetorizar_trechos(session, arquivos, sem_embeddings)

            await imprimir_relatorio(session, relatorio, embeddings)
            if embeddings.erro:
                return 1
    finally:
        await engine.dispose()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.ingest",
        description="Grava knowledge-base/*.md nas tabelas documentos e trechos, com embeddings.",
    )
    parser.add_argument(
        "--forcar",
        action="store_true",
        help="reprocessa todos os documentos, mesmo os de hash inalterado "
        "(útil depois de mudar a lógica de parsing)",
    )
    parser.add_argument(
        "--sem-embeddings",
        action="store_true",
        help="só parsing e reconciliação de texto; não chama a API da Voyage",
    )
    args = parser.parse_args()
    diretorio = Path(get_settings().knowledge_base_path)
    sys.exit(asyncio.run(executar(diretorio, args.forcar, args.sem_embeddings)))


if __name__ == "__main__":
    main()
