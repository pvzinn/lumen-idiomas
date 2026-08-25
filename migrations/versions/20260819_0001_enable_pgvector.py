"""Habilita a extensão pgvector

Precisa ser a primeira migration: nenhuma coluna `vector(n)` pode ser criada
antes de a extensão existir no banco.

Revision ID: 0001_enable_pgvector
Revises:
Create Date: 2026-08-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_enable_pgvector"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Sem DROP EXTENSION: derrubar a extensão apagaria em cascata qualquer
    # coluna vector ainda existente. A remoção, se um dia for necessária,
    # é manual e consciente.
    pass
