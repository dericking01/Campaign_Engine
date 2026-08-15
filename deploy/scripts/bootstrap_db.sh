#!/usr/bin/env bash
# One-time bootstrap for the AfyaCall Campaign Engine database footprint.
# Run ONCE by a Postgres superuser against the existing `afyacall` database.
# Creates a least-privilege application role and the `campaign` schema it owns,
# and grants it read-only access to the existing subscription domain it depends on.
# Idempotent: safe to re-run.
#
# Required env vars:
#   PG_SUPERUSER_HOST, PG_SUPERUSER_PORT, PG_SUPERUSER_DB, PG_SUPERUSER_USER, PG_SUPERUSER_PASSWORD
#   CAMPAIGN_APP_DB_PASSWORD  (password to (re)set for the campaign_app role)
set -euo pipefail

: "${PG_SUPERUSER_HOST:?}" "${PG_SUPERUSER_PORT:?}" "${PG_SUPERUSER_DB:?}" \
  "${PG_SUPERUSER_USER:?}" "${PG_SUPERUSER_PASSWORD:?}" "${CAMPAIGN_APP_DB_PASSWORD:?}"

PGPASSWORD="$PG_SUPERUSER_PASSWORD" psql \
  -h "$PG_SUPERUSER_HOST" -p "$PG_SUPERUSER_PORT" -U "$PG_SUPERUSER_USER" -d "$PG_SUPERUSER_DB" \
  -v ON_ERROR_STOP=1 <<SQL
DO \$do\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'campaign_app') THEN
    CREATE ROLE campaign_app LOGIN PASSWORD '${CAMPAIGN_APP_DB_PASSWORD}';
  ELSE
    ALTER ROLE campaign_app LOGIN PASSWORD '${CAMPAIGN_APP_DB_PASSWORD}';
  END IF;
END
\$do\$;

CREATE SCHEMA IF NOT EXISTS campaign AUTHORIZATION campaign_app;

GRANT USAGE ON SCHEMA subscription TO campaign_app;
GRANT SELECT ON subscription.subscribers TO campaign_app;

-- Phase 7 (Analytics): read-only access to the real engagement-attribution
-- sources - chat.chat_history (chatbot/APU/HGU engagement, see
-- app.analytics.engagement) and provider.provider_appearances/
-- provider_impressions (doctor/provider discovery engagement). No IVR
-- engagement log or product-activation log exists in this database - see
-- docs/decisions.md for why those two attribution dimensions are honestly
-- scoped out rather than fabricated.
GRANT USAGE ON SCHEMA chat TO campaign_app;
GRANT SELECT ON chat.chat_history TO campaign_app;
GRANT USAGE ON SCHEMA provider TO campaign_app;
GRANT SELECT ON provider.provider_appearances TO campaign_app;
GRANT SELECT ON provider.provider_impressions TO campaign_app;

ALTER DEFAULT PRIVILEGES FOR ROLE campaign_app IN SCHEMA campaign
  GRANT ALL ON TABLES TO campaign_app;
SQL

echo "Bootstrap complete: campaign_app role + campaign schema + read-only subscription/chat/provider grants."
