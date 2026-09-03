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
banco não roda na subida da aplicação (ver `app/main.py`, `lifespan`), porque
rodar `alembic upgrade head` a cada réplica subindo faz todas competirem pelo
mesmo lock de migration.

### ⚠️ Estado temporário: migração fora do deploy automático

O `preDeployCommand` (`alembic upgrade head`) foi **removido do
`railway.json`** e a migração é aplicada **manualmente**:

```bash
railway run alembic upgrade head
```

Motivo: o pre-deploy falhava com
`socket.gaierror: [Errno -2] Name or service not known`. A causa é que o TCP
Proxy do serviço pgvector não estava ativado, então
`RAILWAY_TCP_PROXY_DOMAIN` não existe e a `DATABASE_URL` montada pelo template
(`postgres://${{PGUSER}}:${{PGPASSWORD}}@${{PGHOST}}:${{PGPORT}}/${{PGDATABASE}}`)
resolve com host vazio. Rodar a migração à parte dá retorno em segundos, em vez
de exigir um ciclo completo de deploy a cada tentativa.

**Isto é pendência aberta, não decisão definitiva.** Assim que a conexão
estiver validada (TCP Proxy ativo e `railway run alembic upgrade head` passando
de forma consistente), o `preDeployCommand` deve ser restaurado em
`railway.json`:

```json
"deploy": {
  "preDeployCommand": "alembic upgrade head",
  "healthcheckPath": "/health"
}
```

Enquanto não for restaurado, todo deploy que inclua uma migration nova exige
rodar o comando manual antes ou depois da subida — o que é fácil de esquecer.

### Passos manuais no painel do Railway

1. Criar um projeto novo no Railway.
2. Adicionar o template **Postgres** com pgvector ao projeto (não o Postgres
   genérico — precisa vir com a extensão pgvector).
3. No serviço do banco (pgvector), em **Settings → Networking**, ativar o
   **TCP Proxy** apontando para a porta **5432**. Sem isso o Railway não define
   `RAILWAY_TCP_PROXY_DOMAIN`, e como o template monta a DSN a partir de
   `${{PGHOST}}`, a `DATABASE_URL` sai com **host vazio** — que é exatamente o
   `socket.gaierror: [Errno -2] Name or service not known` descrito acima.
   Depois de ativar, conferir em Variables que `DATABASE_URL` (ou
   `DATABASE_PUBLIC_URL`) tem host e porta preenchidos.
4. Adicionar um serviço a partir deste repositório Git.
5. No serviço da aplicação, em Variables, adicionar `DATABASE_URL` referenciando
   o serviço do banco: `DATABASE_URL=${{Postgres.DATABASE_URL}}`. Isso substitui
   as variáveis `POSTGRES_*` do `.env.example` — não defina as duas formas.
   `MIGRATION_DATABASE_URL=${{Postgres.DATABASE_PUBLIC_URL}}` é opcional: se
   não for definida, a migração cai para `DATABASE_URL` (ver
   `app/core/config.py`, `migration_database_url`). Ela só faz diferença quando
   a migração precisa sair pela URL pública em vez da rede privada.
6. Conferir que o Railway detectou o `Dockerfile` como builder (config já
   fixada em `railway.json`, mas vale checar na aba Settings → Build).
7. Fazer o primeiro deploy e acompanhar em Deployments → View Logs: o log de
   build e depois o log do processo da aplicação. **Não há mais log de
   pre-deploy** enquanto o estado temporário acima estiver valendo.
8. Confirmar que o healthcheck (`/health`, configurado em `railway.json`)
   fica verde antes de considerar o deploy concluído.
9. Aplicar a migração com `railway run alembic upgrade head` (ver o estado
   temporário acima).
10. Gerar um domínio público em Settings → Networking, se o serviço precisar
    ser acessível de fora do projeto.
