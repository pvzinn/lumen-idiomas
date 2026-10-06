"""Busca semântica nos trechos da base de conhecimento.

Sem estado e só de leitura: gera o embedding da pergunta, compara com os
vetores dos trechos e devolve os `k` mais próximos. Não chama modelo de
linguagem e não grava nada — o registro da conversa é da Fase 4.

Comparadores do pgvector
------------------------
O tipo `Vector` do pacote `pgvector.sqlalchemy` acrescenta à coluna métodos
que viram os operadores de distância da extensão:

    Trecho.embedding.cosine_distance(v)     ->  embedding <=> v   (cosseno)
    Trecho.embedding.l2_distance(v)         ->  embedding <-> v   (euclidiana)
    Trecho.embedding.max_inner_product(v)   ->  embedding <#> v   (produto interno negado)

Usamos o cosseno, que compara direção e ignora o tamanho do vetor. O operador
devolve *distância* (0 = mesma direção, 1 = ortogonais, 2 = opostos); a
similaridade que a API expõe é `1 - distância`.

A consulta ordena pela distância crescente, e não pela similaridade
decrescente. O resultado é idêntico, mas um índice vetorial (HNSW, IVFFlat) só
é usado pelo Postgres quando o `ORDER BY` é exatamente o operador de distância
em ordem crescente. Hoje não há índice — a varredura sequencial sobre ~80
trechos é exata e leva milissegundos —, mas escrita assim a consulta não
precisa mudar no dia em que ele existir.
"""

import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MODELO_EMBEDDING_CONSULTAS
from app.embeddings import gerar_embedding_consulta
from app.models import Documento, Trecho


@dataclass(frozen=True)
class TrechoEncontrado:
    posicao: int
    trecho_id: int
    arquivo: str
    titulo_documento: str
    titulo_secao: str
    similaridade: float
    conteudo: str


@dataclass(frozen=True)
class ResultadoBusca:
    modelo: str
    tempo_embedding_ms: float
    tempo_banco_ms: float
    trechos: list[TrechoEncontrado]


async def buscar_trechos(session: AsyncSession, pergunta: str, k: int) -> ResultadoBusca:
    """Os `k` trechos mais próximos da pergunta, do mais similar para o menos.

    Não aplica limiar mínimo de similaridade: devolve os `k` mais próximos
    mesmo que nenhum seja de fato parecido. Decidir a partir de que nota um
    trecho serve de resposta é da Fase 4, com base na avaliação da 3.4.

    Levanta `app.embeddings.ErroEmbedding` se a Voyage falhar. Base sem nenhum
    trecho vetorizado não é erro: a lista vem vazia.
    """
    if k < 1:
        raise ValueError(f"k deve ser pelo menos 1, veio {k}")

    inicio = time.perf_counter()
    vetor = await gerar_embedding_consulta(pergunta)
    tempo_embedding_ms = (time.perf_counter() - inicio) * 1000

    distancia = Trecho.embedding.cosine_distance(vetor).label("distancia")
    consulta = (
        select(
            Trecho.id,
            Documento.arquivo,
            Documento.titulo,
            Trecho.titulo,
            Trecho.conteudo,
            distancia,
        )
        .join(Trecho.documento)
        # Os dois filtros cobrem tudo o que não deve aparecer. Quem garante
        # isso é a ingestão (`scripts.ingest`): trecho órfão tem o vetor
        # zerado, documento sem arquivo indexável tem `indexar = false`.
        .where(Documento.indexar.is_(True), Trecho.embedding.is_not(None))
        .order_by(distancia)
        .limit(k)
    )

    inicio = time.perf_counter()
    linhas = (await session.execute(consulta)).all()
    tempo_banco_ms = (time.perf_counter() - inicio) * 1000

    trechos = [
        TrechoEncontrado(
            posicao=posicao,
            trecho_id=trecho_id,
            arquivo=arquivo,
            titulo_documento=titulo_documento,
            titulo_secao=titulo_secao,
            # Calculada aqui, e não como segunda coluna no SQL, para o
            # operador de distância ser avaliado uma vez só por linha.
            similaridade=1 - distancia_trecho,
            conteudo=conteudo,
        )
        for posicao, (
            trecho_id,
            arquivo,
            titulo_documento,
            titulo_secao,
            conteudo,
            distancia_trecho,
        ) in enumerate(linhas, start=1)
    ]
    return ResultadoBusca(
        modelo=MODELO_EMBEDDING_CONSULTAS,
        tempo_embedding_ms=tempo_embedding_ms,
        tempo_banco_ms=tempo_banco_ms,
        trechos=trechos,
    )


__all__ = ["ResultadoBusca", "TrechoEncontrado", "buscar_trechos"]
