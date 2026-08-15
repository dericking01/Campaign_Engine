# AfyaCall Campaign Engine

Production campaign management and execution platform, replacing the
manual TXT/CSV + `screen`-session process described in
`../AfyaCall_Campaign_Engine_Requirements_and_Architecture_v1.docx`.

See `docs/architecture.md` for the full design and `docs/decisions.md` for
confirmed decisions, corrections made during implementation, and open items
still needing business sign-off.

## Stack

PostgreSQL (existing host instance, `campaign` schema) · Kafka · Redis ·
Python/FastAPI · Next.js/React/TypeScript · Docker · Nginx. Kannel (existing
host gateway) is a downstream target, never containerized here.

## First-time setup

1. **Bootstrap the database role/schema** (once, by a Postgres superuser):
   ```bash
   PG_SUPERUSER_HOST=192.168.1.11 PG_SUPERUSER_PORT=5432 PG_SUPERUSER_DB=afyacall \
   PG_SUPERUSER_USER=<superuser> PG_SUPERUSER_PASSWORD=<password> \
   CAMPAIGN_APP_DB_PASSWORD=<new random password> \
   bash deploy/scripts/bootstrap_db.sh
   ```
2. **Configure environment**:
   ```bash
   cp .env.example .env
   # fill in POSTGRES_PASSWORD (the campaign_app password from step 1),
   # KANNEL_USERNAME/PASSWORD, and a random JWT_SECRET_KEY.
   ```
3. **Bring up the stack**:
   ```bash
   docker compose up -d --build
   ```
   This builds and starts: `redis`, `kafka` (KRaft), `kafka-init` (topic
   bootstrap), `migrate` (Alembic, creates `campaign.*`), `backend-api`,
   `frontend`, `nginx`, and 11 worker containers (Phase 1: stub loops that
   prove connectivity + heartbeat; real logic lands Phase 2 onward).
4. **Verify**:
   - `https://simba.afyacall.co.tz:5674/` — portal shell
   - `https://simba.afyacall.co.tz:5674/api/v1/health` — liveness
   - `https://simba.afyacall.co.tz:5674/api/v1/ready` — dependency status
   - `https://simba.afyacall.co.tz:5674/api/v1/docs` — OpenAPI docs

## Local backend development (without Docker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env  # then edit; point REDIS_HOST/KAFKA_BOOTSTRAP_SERVERS
                       # at localhost or a running compose stack as needed
python -m alembic upgrade head
uvicorn app.main:app --reload
```

## Repository layout

```
backend/app/{core,models,schemas,api/routers,services,repositories,
             workers,kafka,redis,gateways,ingestion,audience,rotation,
             analytics,utils}
backend/migrations/      # Alembic — 0001 creates the full campaign schema
frontend/src/{app,components,services,types}
deploy/{nginx,docker,scripts}
docs/
```
