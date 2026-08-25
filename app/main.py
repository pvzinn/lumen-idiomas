"""Ponto de entrada da API.

Sem rotas de negócio por enquanto. O único endpoint é o `/health`, que existe
para o healthcheck do container e não representa comportamento do atendimento.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Ciclo de vida da aplicação.

    A subida não roda migration: o esquema é responsabilidade do Alembic,
    executado como passo separado do deploy.
    """
    yield
    await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Fábrica da aplicação.

    Recebe `settings` para que o teste possa montar o app com outra
    configuração sem mexer no ambiente do processo.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )

    @app.get("/health", tags=["infra"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
