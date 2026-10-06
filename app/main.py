"""Ponto de entrada da API.

Rotas: `/health`, que existe para o healthcheck do container, e `POST /busca`
(`app.api.busca`), a busca semântica nos trechos da base.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.busca import router as busca_router
from app.core.config import Settings, get_settings
from app.db.session import engine


def _configurar_logs(nivel: str) -> None:
    """Dá um destino aos logs dos módulos `app.*`, no nível de `LOG_LEVEL`.

    Configura só o logger `app`, e não o raiz: o uvicorn e o echo do SQLAlchemy
    já têm seus próprios handlers, e um handler no raiz duplicaria as linhas
    deles.
    """
    logger = logging.getLogger("app")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(nivel.upper())


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
    _configurar_logs(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )

    @app.get("/health", tags=["infra"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    app.include_router(busca_router)

    return app


app = create_app()
