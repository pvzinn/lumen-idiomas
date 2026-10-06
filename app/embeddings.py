"""Único ponto de contato com a API de embeddings da Voyage AI.

Expõe duas funções assíncronas — uma para vetorizar trechos da base
(indexação) e uma para vetorizar a pergunta do usuário (busca, tarefa 3.3).
Nenhum outro módulo deve importar `voyageai` diretamente: se o SDK ou o
provedor mudar, a mudança fica contida aqui.

`input_type`
------------
A Voyage prefixa o texto enviado com uma instrução diferente conforme o
`input_type`: `"document"` para o que será indexado, `"query"` para o que
será buscado. Os dois prefixos são desenhados para aproximar, no espaço
vetorial, a pergunta do texto que a responde — é assimetria de propósito, não
uma normalização que poderia ser pulada. Usar o mesmo `input_type` dos dois
lados (ou nenhum) funciona, mas recupera pior.

Retentativa
-----------
O `AsyncClient` da Voyage já embute backoff exponencial com jitter (1s a 16s,
via `tenacity`) para os erros transitórios — `RateLimitError` (HTTP 429),
`ServiceUnavailableError` (502/503/504) e `Timeout`. Não reimplementamos esse
laço aqui; só ligamos `max_retries` na construção do client, porque o padrão
do SDK é `0` (nenhuma retentativa).

Erros permanentes — `AuthenticationError` (401, chave inválida) e
`InvalidRequestError` (400, requisição malformada) — não entram nesse retry
do SDK e sobem já na primeira tentativa; nós os traduzimos em mensagem clara
sem tentativa adicional. Uma `RateLimitError` que sobra depois de esgotar as
tentativas do client também vira erro aqui — a Voyage não distingue, pelo
código HTTP, limite de taxa de cota esgotada (os dois são 429), então a
mensagem não tenta adivinhar qual dos dois foi; só diz que as tentativas
acabaram.
"""

from dataclasses import dataclass

from voyageai.client_async import AsyncClient
from voyageai.error import AuthenticationError, InvalidRequestError, VoyageError

from app.core.config import get_settings
from app.core.constants import (
    EMBEDDING_DIM,
    MODELO_EMBEDDING_CONSULTAS,
    MODELO_EMBEDDING_DOCUMENTOS,
)

# Tentativas por lote antes de desistir (inclui a primeira chamada). O valor é
# arbitrário — só precisa ser alto o bastante para absorver uma rajada de rate
# limit sem esperar minutos, e baixo o bastante para não deixar o script preso
# numa cota realmente esgotada.
MAX_TENTATIVAS = 5

# Textos por requisição. A API aceita até 1000; usamos o mesmo padrão do SDK
# oficial (`voyageai.VOYAGE_EMBED_BATCH_SIZE`). A base tem ~83 trechos hoje —
# cabe numa única chamada — mas o valor não fica preso ao tamanho atual dela.
TAMANHO_LOTE = 128


class ErroEmbedding(RuntimeError):
    """Falha ao gerar embeddings pela Voyage AI. A mensagem já é o suficiente
    para decidir se vale tentar de novo ou se é preciso uma intervenção
    (chave, cota, formato do texto)."""


@dataclass(frozen=True)
class ResultadoEmbeddings:
    vetores: list[list[float]]
    tokens_usados: int


def _client() -> AsyncClient:
    chave = get_settings().voyage_api_key
    if not chave:
        raise ErroEmbedding(
            "VOYAGE_API_KEY não configurada. Defina a variável de ambiente antes de "
            "gerar embeddings (ver .env.example)."
        )
    return AsyncClient(api_key=chave.get_secret_value(), max_retries=MAX_TENTATIVAS)


async def gerar_embeddings_documentos(textos: list[str]) -> ResultadoEmbeddings:
    """Embeddings para indexação: `input_type="document"`, `MODELO_EMBEDDING_DOCUMENTOS`."""
    return await _gerar(textos, model=MODELO_EMBEDDING_DOCUMENTOS, input_type="document")


async def gerar_embedding_consulta(texto: str) -> list[float]:
    """Embedding de uma pergunta do usuário: `input_type="query"`, `MODELO_EMBEDDING_CONSULTAS`.

    Chamada por `app.services.busca`, uma vez por pergunta.
    """
    resultado = await _gerar([texto], model=MODELO_EMBEDDING_CONSULTAS, input_type="query")
    return resultado.vetores[0]


async def _gerar(textos: list[str], *, model: str, input_type: str) -> ResultadoEmbeddings:
    if not textos:
        return ResultadoEmbeddings(vetores=[], tokens_usados=0)

    client = _client()
    vetores: list[list[float]] = []
    tokens_usados = 0

    for inicio in range(0, len(textos), TAMANHO_LOTE):
        lote = textos[inicio : inicio + TAMANHO_LOTE]
        try:
            resposta = await client.embed(
                lote,
                model=model,
                input_type=input_type,
                # Explícito e igual ao tipo da coluna no banco — nunca o
                # padrão do modelo (que hoje é 1024, mas é um detalhe da
                # Voyage, não do nosso esquema).
                output_dimension=EMBEDDING_DIM,
            )
        except AuthenticationError as erro:
            raise ErroEmbedding(f"Chave da Voyage AI inválida ou ausente: {erro}") from erro
        except InvalidRequestError as erro:
            raise ErroEmbedding(f"Requisição rejeitada pela Voyage AI: {erro}") from erro
        except VoyageError as erro:
            raise ErroEmbedding(
                f"Falha ao chamar a Voyage AI (modelo {model}) após esgotar as tentativas: {erro}"
            ) from erro

        for vetor in resposta.embeddings:
            if len(vetor) != EMBEDDING_DIM:
                raise ErroEmbedding(
                    f"Voyage AI (modelo {model}) devolveu vetor de dimensão {len(vetor)}, "
                    f"esperado {EMBEDDING_DIM}"
                )
            # `resposta.embeddings` é tipado como float ou int (conforme
            # `output_dtype`); nunca pedimos int, mas o `float(x)` torna o
            # tipo estático o mesmo que o runtime já garante.
            vetores.append([float(x) for x in vetor])
        tokens_usados += resposta.total_tokens

    return ResultadoEmbeddings(vetores=vetores, tokens_usados=tokens_usados)


__all__ = [
    "ErroEmbedding",
    "ResultadoEmbeddings",
    "gerar_embedding_consulta",
    "gerar_embeddings_documentos",
]
