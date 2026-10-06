"""Dados e vetores de mentira para os testes.

Os vetores são desenhados para a similaridade ser previsível de cabeça:
`vetor(graus)` é um vetor unitário a `graus` do primeiro eixo, então a
similaridade de cosseno entre `vetor(0)` e `vetor(g)` é exatamente `cos(g)` —
1 para 0°, ~0,87 para 30°, 0,5 para 60°, 0 para 90°.
"""

import math
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import EMBEDDING_DIM, MODELO_EMBEDDING_DOCUMENTOS
from app.models import Documento, PublicoDocumento, TopicoDocumento, Trecho


def vetor(graus: float) -> list[float]:
    radianos = math.radians(graus)
    componentes = [0.0] * EMBEDDING_DIM
    componentes[0] = math.cos(radianos)
    componentes[1] = math.sin(radianos)
    return componentes


async def criar_documento(
    sessao: AsyncSession, identificador: str, *, indexar: bool = True
) -> Documento:
    documento = Documento(
        identificador=identificador,
        arquivo=f"{identificador}.md",
        titulo=f"Documento {identificador}",
        topico=TopicoDocumento.COMERCIAL,
        publico=[PublicoDocumento.INTERESSADOS],
        indexar=indexar,
        atualizado_em=date(2026, 8, 11),
        hash_conteudo="0" * 64,
    )
    sessao.add(documento)
    await sessao.flush()
    return documento


async def criar_trecho(
    sessao: AsyncSession, documento: Documento, titulo: str, graus: float | None, *, ordem: int = 0
) -> Trecho:
    """Trecho com o vetor a `graus` da pergunta falsa; `None` deixa o embedding nulo."""
    trecho = Trecho(
        documento_id=documento.id,
        titulo=titulo,
        conteudo=f"Conteúdo de {titulo}.",
        ordem=ordem,
        embedding=None if graus is None else vetor(graus),
        embedding_modelo=None if graus is None else MODELO_EMBEDDING_DOCUMENTOS,
    )
    sessao.add(trecho)
    await sessao.flush()
    return trecho
