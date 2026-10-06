"""Migra a coluna de embedding para a Voyage AI: vector(1536) -> vector(1024)

O modelo escolhido (família Voyage 4) não oferece 1536 dimensões — só 256,
512, 1024 e 2048. `trechos.embedding` está inteiro NULL hoje (a geração de
vetores é da tarefa 3.2, ainda não rodou), então não há vetor nenhum a
converter ou perder nesta migração especificamente.

`USING NULL` em vez de um `USING` que tente converter o vetor existente:
vetores de dimensões diferentes não são conversíveis entre si (não é um
cast, é outro espaço vetorial), então mesmo que houvesse dado, a única
opção sem inventar valores seria descartá-lo. Explicitar isso no `USING`
também é o que torna o downgrade simétrico: ele faz o mesmo na volta.

`embedding_modelo` registra qual modelo gerou cada vetor. Existe porque a
tarefa 3.2 detecta trecho desatualizado por comparação de modelo (não só por
NULL): trocar de modelo de embedding no futuro precisa revetorizar tudo o
que foi gerado pelo modelo anterior, e sem essa coluna não haveria como
saber quais trechos são esses.

Nota sobre `vector(1024)`: como na 0002, a dimensão está escrita à mão, e
não importada de `app.core.constants.EMBEDDING_DIM`. Este arquivo é um
registro do que este upgrade fez num banco numa data; ele não deve mudar de
comportamento se a constante mudar depois.

Revision ID: 0003_voyage_1024
Revises: 0002_modelagem_dominio
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_voyage_1024"
down_revision: str | None = "0002_modelagem_dominio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE trechos ALTER COLUMN embedding TYPE vector(1024) USING NULL")
    op.add_column(
        "trechos",
        sa.Column("embedding_modelo", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    # Descarta todos os vetores gerados sob vector(1024): a mesma
    # inconversibilidade entre dimensões vale na volta, e um vetor de 1024
    # posições não é um vetor de 1536 truncado ou preenchido — é outra coisa.
    # Quem rodar este downgrade precisa revetorizar a base inteira depois.
    op.drop_column("trechos", "embedding_modelo")
    op.execute("ALTER TABLE trechos ALTER COLUMN embedding TYPE vector(1536) USING NULL")
