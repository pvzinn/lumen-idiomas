"""Ambiente de execução do Alembic, em modo assíncrono.

A URL do banco nunca é escrita no `alembic.ini` — vem de `app.core.config`,
que a monta das variáveis de ambiente. Assim migration e aplicação apontam
sempre para o mesmo banco, sem risco de divergirem.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings

# Importar `app.models` popula Base.metadata com todos os modelos registrados.
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", str(get_settings().database_url))

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Mantém fora do autogenerate o que não é gerido pelo ORM.

    A tabela de embeddings do pgvector cria índices (HNSW/IVFFlat) que o
    SQLAlchemy não descreve; sem este filtro o autogenerate tentaria removê-los
    a cada nova migration.
    """
    if type_ == "index" and reflected and name and name.startswith("ix_vector_"):
        return False
    return True


def run_migrations_offline() -> None:
    """Gera o SQL sem conectar ao banco (`alembic upgrade head --sql`)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # compare_type detecta mudança de tipo de coluna — importante quando a
        # dimensão do vector(n) mudar junto com o modelo de embedding.
        compare_type=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
