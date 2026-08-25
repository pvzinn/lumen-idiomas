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

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
