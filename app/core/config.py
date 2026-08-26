"""Configuração da aplicação, lida exclusivamente de variáveis de ambiente."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Aplicação ---
    app_name: str = "Lumen Idiomas — atendimento virtual"
    environment: Literal["local", "staging", "producao"] = "local"
    debug: bool = False
    log_level: str = "INFO"

    # --- Banco de dados ---
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_user: str = "lumen"
    postgres_password: str = "lumen"
    postgres_db: str = "lumen"

    # DSN completa, quando existir. O Railway a injeta a partir do serviço
    # Postgres do template (`${{Postgres.DATABASE_URL}}`); localmente ela não
    # é definida, e a URL é montada das partes acima.
    database_url_env: str | None = Field(default=None, validation_alias="DATABASE_URL")

    # --- Recuperação (RAG) ---
    # A dimensão do embedding não está aqui: é `EMBEDDING_DIM`, em
    # `app.core.constants`. Ela faz parte do tipo da coluna no banco, então não
    # é configuração de ambiente.
    # Quantos trechos a busca devolve por consulta.
    retrieval_top_k: int = Field(default=5, ge=1, le=50)
    # Caminho da base de conhecimento a ser indexada.
    knowledge_base_path: str = "knowledge-base"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """DSN assíncrona, usado pela aplicação em tempo de execução.

        Se `DATABASE_URL` existir, ela tem prioridade sobre as partes acima —
        é o caso do Railway. Ela vem no esquema `postgresql://` (ou
        `postgres://`), mas o projeto usa asyncpg, que exige o driver no
        esquema; convertemos para `postgresql+asyncpg://` aqui em vez de pedir
        que a variável já venha correta, porque quem a fornece é a plataforma,
        não o projeto.
        """
        if self.database_url_env:
            url = self.database_url_env
            for esquema_pg in ("postgresql://", "postgres://"):
                if url.startswith(esquema_pg):
                    return "postgresql+asyncpg://" + url.removeprefix(esquema_pg)
            return url
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        )


@lru_cache
def get_settings() -> Settings:
    """Instância única. O cache existe para não reler o ambiente a cada request.

    Em teste, use `get_settings.cache_clear()` para forçar releitura.
    """
    return Settings()
