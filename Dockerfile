FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Copiar só o pyproject antes do código faz o layer de dependências ser
# reaproveitado enquanto as dependências não mudarem.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install -e ".[dev]"

COPY alembic.ini ./
COPY migrations ./migrations

# Sem EXPOSE fixo: quem decide a porta é quem sobe o container (Railway via
# PORT, docker-compose via `command`), não a imagem.

# Forma shell, não exec: só assim `$PORT` é expandida pelo interpretador.
# O Railway injeta PORT em tempo de execução e pode variar a cada deploy —
# fixar a porta faria o healthcheck da plataforma nunca encontrar o serviço.
# O `:-8000` é só para rodar a imagem fora do Railway, sem PORT definida.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
