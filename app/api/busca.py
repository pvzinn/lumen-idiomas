"""`POST /busca`: busca semântica nos trechos, sem modelo de linguagem.

É `POST`, e não `GET`, para a pergunta ir no corpo: texto em URL acaba em log
de acesso, em histórico de navegador e em cabeçalho `Referer`. Pelo mesmo
motivo, nada aqui grava o texto da pergunta em log — só o tamanho dela, o `k`
e os tempos.

Modelos de requisição e resposta
--------------------------------
`RequisicaoBusca` e `RespostaBusca` são modelos Pydantic. O FastAPI os usa
para três coisas: validar o corpo antes de a função da rota rodar (corpo
inválido vira 422 sem nenhum código nosso), filtrar e serializar a saída
(`response_model`), e gerar o esquema que aparece em `/docs`. As restrições
de `Field` (`min_length`, `ge`, `le`) são a validação e a documentação ao
mesmo tempo.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.embeddings import ErroEmbedding
from app.services.busca import buscar_trechos

logger = logging.getLogger(__name__)

router = APIRouter(tags=["busca"])

MENSAGEM_INDISPONIVEL = (
    "Serviço de busca temporariamente indisponível. Tente novamente em instantes."
)


class RequisicaoBusca(BaseModel):
    # Remove espaços das pontas *antes* de aplicar `min_length`/`max_length`:
    # é o que faz uma pergunta só de espaços ser recusada como vazia.
    model_config = ConfigDict(str_strip_whitespace=True)

    pergunta: str = Field(
        min_length=1,
        max_length=1000,
        description="Pergunta em linguagem natural. Espaços das pontas são removidos.",
        examples=["Quanto custa a mensalidade?"],
    )
    k: int = Field(default=5, ge=1, le=20, description="Quantos trechos devolver.")


class TempoBusca(BaseModel):
    embedding: float = Field(description="Geração do embedding da pergunta (Voyage AI).")
    banco: float = Field(description="Consulta de similaridade no Postgres.")


class TrechoResultado(BaseModel):
    # Permite montar o modelo a partir dos atributos de um objeto — aqui, o
    # dataclass `TrechoEncontrado` do serviço.
    model_config = ConfigDict(from_attributes=True)

    posicao: int = Field(description="1 é o mais similar.")
    trecho_id: int
    arquivo: str = Field(description="Arquivo de origem em knowledge-base/.")
    titulo_documento: str
    titulo_secao: str
    similaridade: float = Field(
        description="Similaridade de cosseno: 1 menos a distância. Quanto maior, mais próximo."
    )
    conteudo: str


class RespostaBusca(BaseModel):
    pergunta: str = Field(description="A pergunta recebida, já sem espaços nas pontas.")
    modelo: str = Field(description="Modelo de embedding usado na pergunta.")
    tempo_ms: TempoBusca = Field(description="Tempo gasto em cada etapa, em milissegundos.")
    resultados: list[TrechoResultado] = Field(
        description="Do mais similar para o menos. Vazia se a base não tem trecho vetorizado."
    )


class Erro(BaseModel):
    detail: str


@router.post(
    "/busca",
    response_model=RespostaBusca,
    summary="Busca os trechos da base mais próximos de uma pergunta",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": Erro,
            "description": "O serviço de embeddings não respondeu.",
        }
    },
)
async def buscar(
    requisicao: RequisicaoBusca,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RespostaBusca:
    try:
        resultado = await buscar_trechos(session, requisicao.pergunta, requisicao.k)
    except ErroEmbedding as erro:
        # Só o tipo da falha vai para o log: a mensagem vem do provedor, e não
        # há garantia de que ela não cite o texto enviado. O cliente recebe
        # uma mensagem fixa, sem nada disso.
        causa = type(erro.__cause__).__name__ if erro.__cause__ else "configuração"
        logger.error(
            "busca indisponível: falha ao gerar o embedding (%s); pergunta de %d caracteres, k=%d",
            causa,
            len(requisicao.pergunta),
            requisicao.k,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=MENSAGEM_INDISPONIVEL
        ) from None

    logger.info(
        "busca: pergunta de %d caracteres, k=%d, %d resultado(s), embedding %.1f ms, banco %.1f ms",
        len(requisicao.pergunta),
        requisicao.k,
        len(resultado.trechos),
        resultado.tempo_embedding_ms,
        resultado.tempo_banco_ms,
    )
    return RespostaBusca(
        pergunta=requisicao.pergunta,
        modelo=resultado.modelo,
        tempo_ms=TempoBusca(
            embedding=round(resultado.tempo_embedding_ms, 1),
            banco=round(resultado.tempo_banco_ms, 1),
        ),
        resultados=[TrechoResultado.model_validate(trecho) for trecho in resultado.trechos],
    )
