# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

A FastAPI + SQLAlchemy (async) + Postgres/pgvector application for a RAG-based support chatbot for **Lumen Idiomas**, a language school in Goiânia, Brazil. Retrieval is implemented (ingestion with Voyage AI embeddings, `POST /busca`); answer generation and conversation logging are not yet.

All content, code comments, identifiers, and commit messages in this repo are written in **Brazilian Portuguese** — keep new content in the same language and register unless told otherwise.

## Commands

```bash
pip install -e ".[dev]"            # into .venv
docker compose up -d db            # Postgres 16 + pgvector on localhost:5432
alembic upgrade head               # apply migrations
python -m scripts.ingest           # index knowledge-base/ (calls Voyage; --sem-embeddings skips it)
docker compose up api              # API on http://localhost:8000 (/docs)

pytest                             # full suite
pytest tests/test_busca.py -k k_limita   # a single test
ruff check . && ruff format --check .
mypy app scripts tests             # strict
```

Tests that need pgvector run against a separate `<POSTGRES_DB>_test` database on the same server, dropped and re-migrated on every run, and are **skipped** (not failed) when Postgres is unreachable — a green run with skips has not exercised the search query. Tests never call Voyage (`tests/conftest.py` blocks the client).

## Architecture notes

- `app/embeddings.py` is the only module that talks to Voyage. `app/services/busca.py` holds the search logic and takes a session, so scripts can call it without HTTP; `app/api/busca.py` is the thin route.
- Search filters on exactly two columns: `documentos.indexar = true` and `trechos.embedding IS NOT NULL`. `scripts/ingest.py` is responsible for keeping both truthful (it nulls the vector of orphaned sections and flips `indexar` when a file disappears or is marked `indexar: false`). A new way for a chunk to become "should not be retrieved" must be expressed through one of those two columns.
- `EMBEDDING_DIM` and the embedding model names are constants in `app/core/constants.py`, not env vars, because the dimension is part of the column type. Changing them requires a migration; migrations hard-code the dimension on purpose.
- Migrations are not run on app startup.

## Repository structure

- `knowledge-base/` — the source-of-truth content the future chatbot will retrieve answers from (RAG corpus).
- `tests/perguntas.md` — the behavioral spec for the chatbot, written **before** any implementation. Per its own description, it "vira teste automatizado na fase 6" (becomes an automated test in phase 6) — treat it as a spec/eval set, not yet a runnable test suite.
- `tests/*.py` — the pytest suite (search endpoint and ingestion).
- `app/`, `scripts/`, `migrations/` — the application (see Commands and Architecture notes above).

## Knowledge base structure (`knowledge-base/`)

Files are numbered (`01-a-escola.md` … `11-particulares-e-empresas.md`) and each covers one topic area (institutional info, courses, levels, class modalities, calendar/enrollment, pricing, certifications, policies, methodology/teachers, facilities, private/corporate classes). Each file has YAML frontmatter with a consistent schema:

```yaml
---
id: <kebab-case-id>
titulo: <display title>
topico: institucional | academico | operacional | comercial
publico: [interessados, alunos, empresas]   # audience tags
indexar: true                                # whether this doc is included in retrieval
atualizado_em: <YYYY-MM-DD>
---
```

When editing or adding knowledge-base content, preserve this frontmatter shape and update `atualizado_em`.

**Avoid fact duplication across files.** `tests/perguntas.md` documents a known violation (P10: the grading-composition fact lives in both `03-niveis-e-nivelamento.md` and `09-metodologia-e-professores.md`) as a cautionary example — the same fact stated in two places risks silently diverging if only one is updated later. When adding content, check whether a fact already lives in another file before restating it.

## The eval spec (`tests/perguntas.md`)

This file defines the expected behavior of the chatbot as a table of test questions, each with:

- `id` — stable identifier; never renumber existing ids.
- `pergunta` — a realistic user question (including informal spelling/slang where relevant, to test retrieval robustness).
- `esperado` — one of three expected behaviors:
  - **`responder`** — the knowledge base fully covers the question; the bot answers from it and does not escalate.
  - **`parcial`** — the knowledge base partially covers it; the bot answers what it knows, states plainly what it doesn't, and escalates only the missing part.
  - **`recusar`** — out of scope by design (individual account data, negotiation, scheduling, complaints) or genuinely uncovered; the bot does not attempt an answer, logs the question, and hands off to a human.
- `origem` — which knowledge-base file(s) the answer should come from (empty for `recusar`).
- `nota` — what the question is specifically testing.

A closing "Achados" (findings) section tracks known knowledge-base gaps/duplications discovered while writing this spec (e.g. P10's duplication, P13's missing content about multiple trial classes). These are **intentionally left unfixed** until after the first retrieval-evaluation pass, so that fixes can be measured rather than applied blind — don't silently "fix" them without flagging it, since that would remove the ability to measure whether the fix helped.

When adding new test questions, keep the `esperado`/`origem`/`nota` columns filled in and update the distribution counts in the summary table if the mix changes. When measuring results later, track accuracy **per category** (`responder` / `parcial` / `recusar`) separately, not as a single global pass rate — the set is intentionally imbalanced toward `responder`, so a high overall score can mask poor performance on `recusar`, which is the highest-cost failure mode for the school.
