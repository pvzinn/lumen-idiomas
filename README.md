# Lumen Idiomas — atendimento virtual

API de RAG sobre a base de conhecimento da Lumen Idiomas, escola de idiomas
em Goiânia. Sem rotas de negócio ainda — fase de modelagem e infraestrutura.

- `knowledge-base/` — corpus de origem (RAG).
- `docs/comportamento.md` — especificação de comportamento do chatbot.
- `tests/perguntas.md` — spec de comportamento esperado (vira teste automatizado na fase 6).
- `app/` — API FastAPI, modelos SQLAlchemy, migrations Alembic.

## Desenvolvimento local

Requer Docker.

```bash
cp .env.example .env
docker compose up -d db
alembic upgrade head
docker compose up api
```

A API sobe em `http://localhost:8000` (`API_PORT` no `.env`). `GET /health`
confirma que o processo está de pé.

## Deploy (Railway)

O deploy roda a partir do `Dockerfile` deste repositório. A migração do
banco não roda na subida da aplicação (ver `app/main.py`, `lifespan`) — ela
roda como passo de pre-deploy, configurado em `railway.json`, porque rodar
`alembic upgrade head` a cada réplica subindo faz todas competirem pelo
mesmo lock de migration.

### Passos manuais no painel do Railway

1. Criar um projeto novo no Railway.
2. Adicionar o template **Postgres** com pgvector ao projeto (não o Postgres
   genérico — precisa vir com a extensão pgvector).
3. Adicionar um serviço a partir deste repositório Git.
4. No serviço da aplicação, em Variables, adicionar `DATABASE_URL` referenciando
   o serviço do banco: `DATABASE_URL=${{Postgres.DATABASE_URL}}`. Isso substitui
   as variáveis `POSTGRES_*` do `.env.example` — não defina as duas formas.
5. Conferir que o Railway detectou o `Dockerfile` como builder (config já
   fixada em `railway.json`, mas vale checar na aba Settings → Build).
6. Fazer o primeiro deploy e acompanhar em Deployments → View Logs: o log de
   build, depois o do `preDeployCommand` (`alembic upgrade head`), e por fim
   o log do processo da aplicação.
7. Confirmar que o healthcheck (`/health`, configurado em `railway.json`)
   fica verde antes de considerar o deploy concluído.
8. Gerar um domínio público em Settings → Networking, se o serviço precisar
   ser acessível de fora do projeto.
