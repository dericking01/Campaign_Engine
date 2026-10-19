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
   # KANNEL_USERNAME/PASSWORD, a random JWT_SECRET_KEY, and the
   # SUPER_USERNAME/EMAIL/PASSWORD/PHONE initial admin.
   ```
3. **Bring up the stack**:
   ```bash
   docker compose up -d --build
   ```
   This builds and starts: `redis`, `kafka` (KRaft), `kafka-init` (topic
   bootstrap), `migrate` (Alembic creates `campaign.*`, then
   `app.scripts.bootstrap` creates the SUPER_ADMIN and the SMS/IVR/DOCTOR
   `channel_configs` rows; both idempotent), `backend-api`,
   `frontend`, `nginx`, and 11 worker containers (Phase 1: stub loops that
   prove connectivity + heartbeat; real logic lands Phase 2 onward).
4. **Verify**:
   - `https://simba.afyacall.co.tz:5674/` — portal shell
   - `https://simba.afyacall.co.tz:5674/api/v1/health` — liveness
   - `https://simba.afyacall.co.tz:5674/api/v1/ready` — dependency status
   - `https://simba.afyacall.co.tz:5674/api/v1/docs` — OpenAPI docs

### New environments

Always let `migrate` build the `campaign` schema from empty. **Never** clone
an environment with a schema-only `pg_dump`: it copies every table but leaves
`campaign.alembic_version` empty and drops the seed rows migrations insert
(0007's roles), so Alembic tries to re-run 0001 and the app has no roles.
`migrations/env.py` now refuses to run in that state with an explanatory
error. If you hit it on a schema you've verified matches revision `<rev>`:
`alembic -x allow_unversioned=1 stamp <rev>`, re-insert that revision's seed
rows, then redeploy. To copy *data* between environments, dump schema and
data together (including `campaign.alembic_version`).

`app.scripts.seed` is dev/demo data only (default password, demo zones) and
refuses to run when `ENVIRONMENT=production`.

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
