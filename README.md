# Lumen Idiomas — atendimento virtual

API de RAG sobre a base de conhecimento da Lumen Idiomas, escola de idiomas
em Goiânia. Hoje faz a recuperação — indexa a base e busca os trechos mais
próximos de uma pergunta. Ainda não gera resposta nem registra conversa.

- `knowledge-base/` — corpus de origem (RAG).
- `docs/comportamento.md` — especificação de comportamento do chatbot.
- `app/` — API FastAPI: modelos SQLAlchemy, cliente de embeddings, busca.
- `scripts/ingest.py` — indexa `knowledge-base/` no banco, com embeddings.
- `migrations/` — migrations Alembic.
- `tests/` — testes automatizados (pytest) e `perguntas.md`, a spec de
  comportamento esperado do chatbot (vira avaliação automatizada na fase 6).

## Desenvolvimento local

Requer Docker e Python 3.12 ou mais novo.

```bash
cp .env.example .env              # preencha VOYAGE_API_KEY
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

docker compose up -d db
alembic upgrade head
python -m scripts.ingest          # indexa knowledge-base/ e gera os embeddings
docker compose up api
```

A API sobe em `http://localhost:8000` (`API_PORT` no `.env`). `GET /health`
confirma que o processo está de pé, e `http://localhost:8000/docs` traz a
documentação interativa das rotas.

`scripts.ingest` é idempotente: rode de novo sempre que `knowledge-base/`
mudar. Ele reprocessa só os arquivos alterados e só chama a Voyage para os
trechos novos ou modificados. `--sem-embeddings` faz só o parsing, sem chamar
a API.

## Busca semântica

`POST /busca` recebe uma pergunta e devolve os `k` trechos da base mais
próximos dela, com a similaridade de cada um. Não chama modelo de linguagem e
não grava nada.

```bash
curl -s -X POST http://localhost:8000/busca \
  -H 'Content-Type: application/json' \
  -d '{"pergunta": "Quanto custa a mensalidade?", "k": 3}'
```

- `pergunta`: obrigatória, de 1 a 1000 caracteres depois de removidos os
  espaços das pontas.
- `k`: opcional, de 1 a 20; o padrão é 5.

```json
{
  "pergunta": "Quanto custa a mensalidade?",
  "modelo": "voyage-4-lite",
  "tempo_ms": { "embedding": 343.3, "banco": 4.1 },
  "resultados": [
    {
      "posicao": 1,
      "trecho_id": 36,
      "arquivo": "06-valores-e-pagamento.md",
      "titulo_documento": "Valores e pagamento",
      "titulo_secao": "Quanto custa a mensalidade das turmas em grupo",
      "similaridade": 0.5787,
      "conteudo": "A mensalidade das turmas em grupo da Lumen Idiomas custa…"
    }
  ]
}
```

`similaridade` é a similaridade de cosseno (1 menos a distância): quanto
maior, mais próximo. Não há nota mínima — a busca sempre devolve os `k` mais
próximos, mesmo para uma pergunta fora do assunto. O limiar entra na fase 4.

Só aparecem trechos de documentos com `indexar: true` e que já têm embedding.
Com a base vazia ou sem vetores, `resultados` vem vazio. Corpo inválido
devolve 422; falha no serviço de embeddings devolve 503.

É `POST` para a pergunta ir no corpo, e não na URL, e o texto dela não é
gravado em log: a aplicação registra só o tamanho, o `k` e os tempos.

## Testes

```bash
docker compose up -d db
pytest
```

Os testes que precisam do pgvector usam o mesmo servidor Postgres do
desenvolvimento, mas um banco separado, `<POSTGRES_DB>_test` (`lumen_test`).
A cada execução ele é apagado, recriado e migrado com `alembic upgrade head`;
o banco de desenvolvimento não é tocado. Cada teste roda numa transação
desfeita no fim.

Sem Postgres acessível, esses testes são **pulados** — `pytest -rs` mostra o
motivo — e os demais rodam normalmente.

Nenhum teste chama a Voyage: o embedding é trocado por um vetor falso e
determinístico, então a suíte não consome a API nem depende de rede.

Lint e tipos: `ruff check .`, `ruff format --check .` e `mypy app scripts tests`.

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
   Adicionar também `VOYAGE_API_KEY`: sem ela, `POST /busca` responde 503.
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
