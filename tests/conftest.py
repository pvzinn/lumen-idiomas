"""Infraestrutura dos testes: banco de teste, sessão isolada, Voyage falsa.

Banco de teste
--------------
Os testes que precisam do pgvector rodam contra o mesmo servidor Postgres do
desenvolvimento (as variáveis `POSTGRES_*`), mas num banco próprio:
`<POSTGRES_DB>_test`. A cada execução da suíte esse banco é apagado, recriado
e migrado com `alembic upgrade head` — o esquema dos testes é o das
migrations, não uma aproximação montada à parte, e toda execução confere de
quebra que as migrations sobem do zero.

Se o servidor não estiver acessível, os testes que dependem dele são pulados
com uma mensagem dizendo o que subir; os demais rodam normalmente.

Isolamento
----------
Cada teste recebe uma sessão presa a uma transação que é desfeita no fim.
Nada do que um teste grava é visto pelo seguinte, e não há limpeza de tabela.

Voyage
------
Nenhum teste fala com a Voyage. `voyage_falsa` troca a função de embedding da
pergunta por uma determinística, e `_voyage_bloqueada` faz qualquer caminho
que escape dela falhar na hora, em vez de gastar a API em silêncio.
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg  # type: ignore[import-untyped]
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app
from tests.fabricas import vetor

RAIZ = Path(__file__).resolve().parent.parent
SUFIXO_BANCO_DE_TESTE = "_test"


class _BancoInacessivel(Exception):
    pass


async def _recriar_banco(nome: str) -> None:
    settings = get_settings()
    try:
        # Banco de manutenção `postgres`: não se apaga nem se cria um banco
        # estando conectado a ele.
        conexao = await asyncpg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password,
            database="postgres",
            timeout=3,
        )
    except (OSError, TimeoutError, asyncpg.PostgresError, asyncpg.InterfaceError) as erro:
        raise _BancoInacessivel(f"{type(erro).__name__}: {erro}") from erro
    try:
        await conexao.execute(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)')
        await conexao.execute(f'CREATE DATABASE "{nome}"')
    finally:
        await conexao.close()


@pytest.fixture(scope="session")
def banco_de_teste() -> URL:
    """URL do banco de teste, recém-criado e migrado. Pula o teste se não houver servidor."""
    settings = get_settings()
    # Montado das partes `POSTGRES_*`, nunca de `DATABASE_URL`: essa variável
    # pode apontar para produção, e este código apaga o banco que encontra.
    nome = f"{settings.postgres_db}{SUFIXO_BANCO_DE_TESTE}"
    assert nome.endswith(SUFIXO_BANCO_DE_TESTE)

    try:
        asyncio.run(_recriar_banco(nome))
    except _BancoInacessivel as erro:
        pytest.skip(
            f"Postgres de teste inacessível em {settings.postgres_host}:{settings.postgres_port} "
            f"({erro}). Suba o banco com `docker compose up -d db` e confira POSTGRES_HOST e "
            "POSTGRES_PORT no .env."
        )

    url = URL.create(
        "postgresql+asyncpg",
        username=settings.postgres_user,
        password=settings.postgres_password,
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=nome,
    )
    # Em subprocesso porque o `env.py` do Alembic lê a URL do ambiente e chama
    # `asyncio.run` por conta própria. `MIGRATION_DATABASE_URL` tem prioridade
    # sobre tudo o mais em `app.core.config`.
    migracao = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=RAIZ,
        env={**os.environ, "MIGRATION_DATABASE_URL": url.render_as_string(hide_password=False)},
        capture_output=True,
        text=True,
    )
    if migracao.returncode != 0:
        pytest.fail(f"alembic upgrade head falhou no banco de teste:\n{migracao.stderr}")
    return url


@pytest.fixture
async def sessao(banco_de_teste: URL) -> AsyncIterator[AsyncSession]:
    """Sessão cujas gravações somem no fim do teste.

    A sessão é ligada a uma conexão que já está numa transação. Com
    `join_transaction_mode="create_savepoint"`, um `commit()` ou `begin()` do
    código testado mexe só num SAVEPOINT; a transação de fora continua aberta
    e é desfeita aqui.
    """
    # Engine por teste e sem pool: cada teste roda no seu próprio event loop,
    # e uma conexão do asyncpg não sobrevive à troca de loop.
    engine = create_async_engine(banco_de_teste, poolclass=NullPool)
    async with engine.connect() as conexao:
        transacao = await conexao.begin()
        async with AsyncSession(
            bind=conexao,
            join_transaction_mode="create_savepoint",
            # As mesmas opções de `app.db.session.SessionLocal`.
            expire_on_commit=False,
            autoflush=False,
        ) as sessao:
            yield sessao
        await transacao.rollback()
    await engine.dispose()


class _SessaoProibida:
    """No lugar da sessão nos testes que não deveriam chegar ao banco."""

    def __getattr__(self, nome: str) -> None:
        raise AssertionError(f"este teste não deveria tocar o banco (acessou session.{nome})")


@pytest.fixture
def aplicacao() -> Iterator[FastAPI]:
    """App novo por teste, com o banco proibido até `cliente_com_banco` liberar."""
    app = create_app()

    async def sem_banco() -> AsyncIterator[_SessaoProibida]:
        yield _SessaoProibida()

    app.dependency_overrides[get_session] = sem_banco
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def cliente(aplicacao: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Cliente HTTP que chama o app em memória, no mesmo event loop do teste.

    `ASGITransport` em vez do `TestClient` do FastAPI: o `TestClient` roda o
    app em outra thread, com outro loop, e a conexão do banco aberta pelo
    teste não pode ser usada de lá.
    """
    transporte = httpx.ASGITransport(app=aplicacao)
    async with httpx.AsyncClient(transport=transporte, base_url="http://teste") as cliente:
        yield cliente


@pytest.fixture
def cliente_com_banco(
    aplicacao: FastAPI, cliente: httpx.AsyncClient, sessao: AsyncSession
) -> httpx.AsyncClient:
    """O mesmo cliente, com a rota recebendo a sessão isolada do teste."""

    async def sessao_do_teste() -> AsyncIterator[AsyncSession]:
        yield sessao

    aplicacao.dependency_overrides[get_session] = sessao_do_teste
    return cliente


@pytest.fixture(autouse=True)
def _voyage_bloqueada(monkeypatch: pytest.MonkeyPatch) -> None:
    def bloqueio() -> None:
        raise AssertionError("o teste tentou chamar a Voyage de verdade; use `voyage_falsa`")

    monkeypatch.setattr("app.embeddings._client", bloqueio)


@pytest.fixture
def voyage_falsa(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Embedding de pergunta falso e determinístico: sempre `vetor(0)`.

    Devolve a lista dos textos que chegaram à função, para o teste conferir o
    que seria enviado à Voyage (ou que nada foi).
    """
    recebidos: list[str] = []

    async def embedding_falso(texto: str) -> list[float]:
        recebidos.append(texto)
        return vetor(0)

    # No módulo que *usa* a função, não em `app.embeddings`: `busca.py` fez
    # `from app.embeddings import gerar_embedding_consulta` e guarda a própria
    # referência.
    monkeypatch.setattr("app.services.busca.gerar_embedding_consulta", embedding_falso)
    return recebidos
