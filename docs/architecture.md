# AfyaCall Campaign Engine — Architecture

Status: Phases 1-7 implemented and verified live, plus two post-Phase-7
addenda - most recently phone numbers, SMS 2FA, sliding sessions, and
self-service profile management (migration 0009, see "Post-Phase-7
addendum #2" below). This document is the durable reference;
`/root/.claude/plans/buzzing-meandering-rocket.md` is the session's working
plan and duplicates parts of this for history; `docs/decisions.md` has the
full log of live verifications and bugs found.

## Why this exists

AfyaCall's current campaign process (SMS/IVR/Doctor to a 17M+ MSISDN base)
is entirely manual: TXT/CSV files, hand-run PHP/Python scripts in `screen`
sessions, manual DND/subscriber filtering, hand-sliced daily rotation
(~2-2.5M/day), and uncoordinated dispatch to Kannel. The real SMSC ceiling is
a **global 200 TPS**, not per-script — the legacy `smsmaster.php`/
`drmaster.php` scripts have *no* rate limiting at all (only `ivrmaster.php`
does), so concurrent scripts can and do exceed the gateway's real capacity,
backing up inside Kannel. There's no queue manager, no audit trail, no
resumability after a crash, and a recurring manual handoff to a data analyst
for reporting.

This platform replaces that with: PostgreSQL (existing instance, new
`campaign` schema) as source of truth, Kafka as the durable execution queue,
Redis for distributed coordination and the global rate limiter, Python
workers for high-volume processing, FastAPI as the control-plane API, and a
Next.js operator portal. See the requirements document
(`AfyaCall_Campaign_Engine_Requirements_and_Architecture_v1.docx`) for the
full original spec, and the legacy codebase at `/home/derrick/sourcecode`
for the business logic this replaces (referenced throughout this doc where
relevant).

## Core principle (never invert)

```
PostgreSQL = source of truth
Kafka      = durable event backbone + work queue
Redis      = distributed coordination + rate limiting + cache
Python     = high-volume processing + workers
FastAPI    = control-plane API
Next.js    = admin portal
Kannel     = downstream SMS gateway (never the queue)
Global 200 TPS = hard constraint, enforced centrally, never per-worker
```

## PostgreSQL `campaign` schema

The existing AfyaCall Postgres instance (`192.168.1.11:5432`, db `afyacall`)
is reused — **never a second database**. A dedicated `campaign` schema holds
every table this platform owns. A least-privilege role, `campaign_app`,
owns that schema and has `SELECT`-only access to `subscription.subscribers`
(the one existing table this platform reads) — nothing else outside
`campaign.*`. See `deploy/scripts/bootstrap_db.sh` for the one-time
superuser bootstrap that creates this role/schema/grant (run once, outside
Alembic, since role/cross-schema-grant creation is an infrequent
administrative action).

MSISDN canonical format: `255` + 9 digits (`VARCHAR(12)`, `CHECK
(customer_msisdn ~ '^255[0-9]{9}$')`) on every MSISDN column. **Note:** the
requirements doc's ASCII placeholder `255xxxxxxxxxxx` is imprecise; the
legacy PHP scripts' actual working regex (`^255\d{9}$`) and real Tanzanian
mobile numbering (country code + 9-digit subscriber number) both confirm 12
digits total, not 13 — this was caught and fixed via a live constraint
violation during Phase 1 verification (see `docs/decisions.md`).

### Table groups

- **Reference/config**: `zone_configs` (supports a parent hierarchy — legacy
  bases carry both `TERRITORY` and coarser `COMMERCIAL_REGION`),
  `channel_configs` (per-channel sender_id/tps_allocation — fixes the legacy
  inconsistency where `drmaster.php` used `"AFYACALL"` as sender id while
  `smsmaster.php`/`ivrmaster.php` used `"15723"`), `users` (role is an FK
  to `roles.code`, not a fixed set - see "Post-Phase-6 addendum"; also
  carries `phone`, `two_factor_enabled`, and `last_login_at/ip/browser` -
  see "Post-Phase-7 addendum #2"), `roles`
  + `role_permissions` (GUI-configurable role → `Action` grants; 5 seeded
  system roles, plus any custom ones created via the portal),
  `otp_codes` (purpose-tagged SMS one-time-codes for login 2FA, password
  change, and password reset), `user_sessions` (the sliding-30-minute
  session backing each JWT's `sid` claim); `users.phone` is `UNIQUE`
  (migration `0010`, since it's the sole OTP delivery target - two
  accounts sharing one phone would receive each other's codes),
  `import_profiles` (reusable column-mapping templates), `customer_products`.
- **Import pipeline**: `imports` (full import state machine), `import_staging_rows`
  (transient, per-import preview data).
- **Base data**: `bases`, `base_versions` (immutable per-commit snapshot,
  exactly one `is_current=true` per base via partial unique index),
  `base_members` — promoted columns (`territory`, `gender`, `age`,
  `arpu_segment`) plus a `source_snapshot JSONB` catch-all for the richer
  telco attributes real legacy bases carry (`SUB_TYPE`, `SMARTPHONE_USER`,
  `ACS_CHARGE`, `VAS_USER`, `COMMERCIAL_REGION`, ...) that the requirements
  doc's basic MSISDN/age/gender/zone model doesn't mention.
- **DND**: `dnd_lists` (versioned), `dnd_records` — "on DND" = union of all
  active records across active lists.
- **Subscription state**: `customer_subscription_state`, keyed
  `(customer_msisdn, product_code)` — **per-product, not one flat boolean**.
  This directly reflects a real finding from the legacy codebase:
  `matched_msisdns.py` computes campaign exclusion by intersecting two
  *separate* per-product "not subscribed" files (DOCSUB, CHATBOT), which is
  concrete evidence that "subscribed to any product" in practice means
  checking membership across multiple distinct product signals, not one
  table. Synced via batch `COPY`+`ON CONFLICT` (never per-row remote
  queries — see the anti-pattern note on `not_in_base.py` below); same shape
  works unchanged if a `campaign.subscription-events` Kafka consumer is
  added later.
- **Campaigns**: `campaigns` (`sender_id` optionally overrides every
  channel's default sender ID for the whole campaign;
  `include_staff_notifications` snapshots the staff roster into every run
  when true — see "Post-Phase-5 addendum"), `campaign_runs`
  (`UNIQUE(campaign_id, run_date)`), `schedules`, `rotation_state`
  (`UNIQUE(base_id, zone)` — the **authoritative** resumable rotation
  cursor; replaces the legacy `extract_msisdns.php` pattern of an operator
  hand-editing a start-line constant), `cooldown_state`.
- **Audience**: `audience_snapshots` (frozen per-run header),
  `audience_members` — records both included *and* excluded candidates with
  a reason, so "why was customer X excluded" is always answerable.
- **Messages** (write-heaviest): `messages` — `UNIQUE(campaign_run_id,
  customer_msisdn, channel)` is the canonical idempotency identity used
  throughout dispatch; `sender_id` is resolved once at queue time
  (campaign override, else channel default) and carried on the row so
  dispatch/retry never re-look it up; `message_attempts` — append-only
  attempt/audit detail.
- **Staff notifications**: `staff_contacts` (`name`, `msisdn`, `is_active`)
  — a compliance roster, not linked by FK to `messages` (see "Post-Phase-5
  addendum") so a removed staff member never retroactively affects
  historical message records.
- **Events/audit**: `events` — a transactional outbox (a business
  transaction writes its state change and an outbox row together; a relay
  worker tails unpublished rows and publishes to Kafka, avoiding the
  dual-write problem without XA transactions); `audit_logs` — every
  high-impact action.
- **Analytics**: `analytics_rollups` — one cached row per `campaign_run_id`
  (core metrics + chat/provider engagement JSONB), computed once by
  `worker-analytics` when a run completes rather than recomputed on every
  dashboard view - see the Phase 7 entry below and `docs/decisions.md`.

### Partitioning

Every high-volume table needing a uniqueness constraint (`base_members`,
`audience_members`, `messages`) is **HASH-partitioned on the column that's
also in its uniqueness constraint** (`base_version_id` / `campaign_run_id`,
32 partitions each) — PostgreSQL requires unique constraints on partitioned
tables to include the partition key, and these tables' natural idempotency
keys already contain a good hash-distribution column. Append-only,
no-cross-partition-uniqueness-needed audit tables (`message_attempts`,
`events`, `audit_logs`) are **RANGE-partitioned by time** instead, so
retention is "drop old partitions," with a `DEFAULT` partition on each to
catch anything outside the pre-created window.

`message_attempts` denormalizes `campaign_run_id` from `messages` purely so
its FK to `messages(campaign_run_id, id)` — the only way to reference a row
in a table whose PK must include the partition key — is expressible.

**Operational runbook note:** the initial migration pre-creates RANGE
partitions through 2027-12 (monthly tables) / ~6 months out (weekly
`events` partitions). A periodic ops job must create further partitions
before that window runs out; the `DEFAULT` partition prevents hard failures
in the meantime but should not become the steady-state destination for new
rows (query performance degrades without partition pruning).

## Kafka

8 logical topics — deliberately not one per status/retry variant:

| Topic | Key | Partitions | Retention | Purpose |
|---|---|---|---|---|
| `campaign.import.events` | import_id | 6 | 14d | import lifecycle |
| `campaign.audience.events` | campaign_run_id | 6 | 14d | audience-gen lifecycle |
| `campaign.dispatch.sms` | customer_msisdn | 12 | 48h | SMS dispatch commands |
| `campaign.dispatch.ivr` | customer_msisdn | 12 | 48h | IVR dispatch commands |
| `campaign.dispatch.doctor` | customer_msisdn | 12 | 48h | Doctor dispatch commands |
| `campaign.message-events` | message_id | 12 | 48h | attempt/terminal status |
| `campaign.subscription-events` | customer_msisdn | 6 | 14d | future subscription-domain events |
| `campaign.analytics.events` | campaign_run_id | 6 | 14d | rollup feed |

Plus `.dlq` topics (90d retention) on the 3 dispatch topics + message-events.

Dispatch topics are keyed by `customer_msisdn` (not `message_id`) so all
messages for one customer land on the same partition and process in
relative order — a customer can be targeted by overlapping
campaigns/channels, and per-customer ordering matters more here than
perfectly uniform partition load (per-customer volume is inherently low).

**Retry is DB-driven, not Kafka-native**: `messages.status='RETRYING'` +
`next_attempt_at` is authoritative; a retry-scheduler worker polls due work
and re-publishes to the *original* dispatch topic. No `.retry` topics.
**Pause/resume/stop is not a Kafka topic either** — `campaign_runs.status`
in Postgres is authoritative; dispatchers poll it cheaply.

Bootstrapped idempotently by `deploy/scripts/bootstrap-kafka-topics.sh`
(`kafka-topics.sh --create --if-not-exists`), run once by the `kafka-init`
compose service.

## Redis

**Global 200 TPS limiter**: GCRA (leaky-bucket via theoretical-arrival-time)
in one atomic Lua script per dispatch attempt — checks the per-channel
sub-allocation, then the global ceiling; both must pass. A single float
timestamp key per limiter is self-correcting after a Redis restart (worst
case: a brief burst right after restart, never a permanent wedge — an
accepted, documented trade-off). Keys: `campaign:ratelimit:global:tat`,
`campaign:ratelimit:channel:{sms|ivr|doctor}:tat`.

**Locks**: `SET NX PX` + Lua compare-and-delete release + heartbeat-extend.
`campaign:lock:rotation:{base_id}`, `campaign:lock:import:{import_id}` —
concurrency guards only, never the correctness mechanism. Rotation's actual
resumability lives in `rotation_state.last_offset`, committed
transactionally in Postgres — a lost lock just lets a new worker resume
from the DB watermark.

Redis holds nothing that is the system of record.

## Idempotency

Canonical identity: `(campaign_run_id, customer_msisdn, channel)`, enforced
by the `messages` unique constraint. Every stage is a DB compare-and-swap:
audience-gen uses `INSERT...ON CONFLICT DO NOTHING`; queuing is
`UPDATE...WHERE status='CREATED'`; the dispatcher does `UPDATE...WHERE
status='QUEUED'` **before** calling Kannel, so a duplicate Kafka delivery
finds 0 rows and no-ops without ever double-calling Kannel. Kafka offsets
commit only after the DB transition succeeds. Verified live in Phase 1 (see
`docs/decisions.md`): a simulated duplicate delivery's CAS update correctly
affected 0 rows.

**Ambiguous Kannel response** (timeout / unrecognized body): `messages.status
= 'FAILED_UNCONFIRMED'`, never auto-retried — confirmed decision, avoids
risking a duplicate SMS/call to a real customer; surfaced to an ops review
queue instead.

## State machines

- **Import**: `IMPORT_CREATED → STAGED → VALIDATING → PREVIEW_READY →
  APPROVED → COMMITTING → READY | REJECTED/FAILED` (plus `DETECTED`/
  `UPLOADED` at file-arrival).
- **Campaign**: `DRAFT → CONFIGURED → AUDIENCE_GENERATING → READY →
  SCHEDULED → RUNNING ⇄ PAUSED → COMPLETED`, terminal `CANCELLED`/`FAILED`.
- **Message**: `CREATED → QUEUED → SUBMITTING → SENT`; failure path
  `SUBMITTING → FAILED → RETRYING → (SENT | DEAD)`, plus
  `FAILED_UNCONFIRMED` for ambiguous Kannel outcomes.

## Eligibility & rotation (set-based SQL, not Python loops)

Audience generation is one `INSERT...SELECT` from `base_members` with
`LEFT JOIN`s against active DND records, subscribed products (per campaign's
excluded product list), and cooldown state. This directly replaces the
legacy `not_in_base.py` anti-pattern — pulling all of
`subscription.subscribers` (2.09M rows, confirmed live during Phase 1) into
a Python/pandas set and diffing in application memory — with an indexed
anti-join pushed into Postgres.

Rotation runs inside one transaction, guarded by the rotation lock: rank
eligible members per zone by `row_number()`, select the slice past
`rotation_state.last_offset` up to the zone quota, insert into
`audience_members`, advance `last_offset` (wrapping to a new cycle when a
zone's eligible pool is exhausted). A crash before commit just retries from
the last committed offset — no double-select, no skip. This replaces the
legacy `extract_msisdns.php` pattern of an operator hand-editing a
`$start`/`$limit` constant each day (a comment in that script literally
tracks rotation position via tribal knowledge: "ended at 240001").

Full SQL for both is in `/root/.claude/plans/buzzing-meandering-rocket.md`
and will be implemented as the `app.audience`/`app.rotation` modules in
Phase 3/4.

## Docker / networking

Everything except Postgres and Kannel runs in Docker: `nginx`, `frontend`,
`backend-api`, `migrate` (one-shot Alembic job), `kafka` (single-node
KRaft, no Zookeeper), `kafka-init` (idempotent topic bootstrap), `redis`,
and 11 worker services sharing one image (`WORKER_TYPE` env var selects the
loop). Host Postgres (`192.168.1.11`) and Kannel (`192.168.1.10`) are
routable LAN IPs on the same network as the Docker host — reached via
normal bridge-network egress, no `host-gateway` trick needed. Verified live:
this Docker host itself sits at `192.168.1.200` on the same `/24` as both.

Every service runs with `TZ=Africa/Dar_es_Salaam` (see "Post-Phase-5
addendum") — container-local time only, business timestamps stay UTC.

**Port hygiene**: this host already runs other production containers,
including an unrelated `kafka` container on `9092` and a bare-metal
`redis-server` on `6379`. The compose Kafka/Redis services are deliberately
**not** published to the host at all (internal `campaign-net` only) — both
to satisfy "never expose Kafka/Redis publicly" and to avoid colliding with
those pre-existing services. `backend-api`/`frontend` are likewise
unpublished, reachable only through `nginx`. Only `nginx` publishes a host
port: `5674:443`, exactly as specified.

## Nginx

`simba.afyacall.co.tz`, TLS terminated with the real existing wildcard cert
at `/home/derrick/afyacall/afyacall.co.tz.{crt,key}` (confirmed present),
mounted read-only. Port 80 redirect block is present in the config for
completeness but not published to the host (only `5674:443` was specified;
publishing 80 as well is a one-line change if the network edge needs it).
`client_max_body_size` raised for large CSV/TXT uploads; `proxy_buffering
off` on `/api/` to avoid buffering issues on async/long-poll endpoints.

## Repository structure

```
afyacall-campaign-engine/
  backend/app/{core,models,schemas,api/routers,services,repositories,
               workers,kafka,redis,gateways,ingestion,audience,rotation,
               analytics,utils}
  backend/migrations/          # Alembic; 0001 creates the full schema
  backend/tests/
  frontend/src/{app,components,features,services,hooks,types}
  deploy/{nginx,docker,scripts}
  docs/
  docker-compose.yml
  .env / .env.example
```

## Phased roadmap

1. **Foundation** — done, see `docs/decisions.md` for what was verified
   live.
2. **Ingestion** — done, verified live at full 17M-row real scale (see
   `docs/decisions.md`): import_profiles/imports/staging/base commit, a
   csv-module-based streaming parser (chunked, malformed-row-tolerant —
   reproduces and correctly handles the exact `not_in_base.py` legacy bug
   class), MSISDN normalizer, GUI upload + server-drop scanner,
   Kafka-driven (`campaign.import.events`) async stage/commit via
   `worker-ingestion`, Odoo-like preview/approve/commit, transactional
   outbox + `worker-outbox-relay` now doing real work (not a stub), and a
   `campaign:lock:import:{id}` Redis lock (finally wired up after a real
   concurrency bug forced the issue — see decisions.md #21) guarding the
   stage/commit critical section against overlapping workers.
3. **Eligibility/DND/Subscriber** — done, verified live (see
   `docs/decisions.md`): DND import reuses the entire Phase 2 pipeline
   (`imports.import_kind` branches `commit_import` between
   `base_members`/`dnd_records`); subscriber sync is a same-database
   set-based `INSERT...SELECT`/`UPDATE` pair against the real
   `subscription.subscribers` (never a Python-side diff, replacing the
   `not_in_base.py` anti-pattern directly); `POST /audience/preview`
   implements the eligibility query below as a real endpoint, verified
   both for exact correctness (a hand-computed 10-row fixture using real
   subscriber MSISDNs) and at real 17M-row scale (18.5s).
4. **Campaign Engine/Rotation** — done, verified live (see
   `docs/decisions.md` #28-32): `POST /campaigns` (full validation against
   base/DND/zone existence), `POST /campaign-runs` (creates the run,
   writes the outbox event that triggers `worker-audience`),
   `GET /audience/runs/{id}/members` (paginated). Rotation
   (`app.rotation.engine.rotate_zone`) runs per-zone inside one
   transaction guarded by `campaign:lock:rotation:{base_id}`, folded into
   `worker-audience` rather than a separate rotation worker (a standalone
   process would need cross-process coordination for what is fundamentally
   one atomic step). Crash-resume verified two ways: a real `docker kill
   -9` of the worker mid-flight followed by clean Kafka redelivery, and a
   deterministic test that pre-commits one zone then confirms
   `generate_audience()` skips it and finishes the rest with zero
   duplicates. Cycle-wrap (a zone's eligible pool exhausted, cursor wraps
   to a new cycle) exercised as a side effect of the same test.
5. **Kafka Execution/Dispatch** — done, verified live (see
   `docs/decisions.md` #34-38): `POST /campaign-runs/{id}/{start,pause,
   resume,stop}`, `GET /messages/runs/{id}` (paginated, status-filterable),
   `POST /messages/{id}/retry`. `worker-scheduler` materializes+publishes
   a run's messages on start; `worker-dispatch-{sms,ivr,doctor}` call the
   real Kannel HTTP API (`app.gateways.kannel`) under a GCRA rate limiter
   (`app.redis.ratelimit`, global 200 TPS + per-channel sub-allocations,
   burst=0 - a burst>0 parameterization was tried first and measured to
   never converge to the ceiling within a realistic run's duration, see
   decisions.md #34); `worker-retry-scheduler` polls DB-driven retries
   (`messages.status='RETRYING' AND next_attempt_at<=now()`) and
   republishes to the original dispatch topic - no `.retry` topics.
   Pause/resume is DB-authoritative: a dispatcher's claim CAS checks
   `campaign_runs.status='RUNNING'` inline, so a paused run's queued
   messages are simply never claimed (verified live with the consumer
   actively polling, not stopped); resume republishes them. All 4 Kannel
   response classes (SENT/permanent-fail/transient-fail/ambiguous-timeout)
   verified end-to-end through the real dispatch pipeline against a mock
   Kannel server, then confirmed against one real live send through the
   actual gateway (192.168.1.10, HTTP 202 / "0: Accepted for delivery",
   classified SENT - exactly matching the assumed format, see
   decisions.md #40). A general Kafka-consumer bug (skipping a commit
   does not actually guarantee redelivery within a live process) was
   found while building this phase and fixed across every consumer in
   the codebase, not just the new ones - see decisions.md #35. The
   Execution Monitor portal page (start/pause/resume/stop controls,
   live per-run message-status counts) is also done - see decisions.md
   #39 for a real UI polling bug found and fixed via a Playwright
   screenshot that didn't match backend state.
6. **Operations** — done, verified live (see `docs/decisions.md` #45-49):
   closed a real gap where 11 read endpoints (bases/DND/campaigns/
   campaign-runs/imports/system config) had no auth at all - confirmed via
   unauthenticated `curl` returning real data, fixed with
   `Action.CAMPAIGN_VIEW`, re-verified 401/403 afterward. Full user
   management (`/users`, CRUD, self-deactivate/self-delete/self-role-change
   guards). Audit logging (write-path built in the Phase 5 addendum, see
   #43) extended to every remaining high-impact action - import approve/
   reject/retry, campaign create, run start/pause/resume/stop, manual
   message retry, subscription sync - with a real atomicity bug caught and
   fixed along the way (the run-lifecycle audit row now commits in the
   same transaction as the state change it describes, not a separate one
   after). Frontend RBAC gating (`useAuth().can()`) applied to every
   mutation control across the portal - ergonomics only, the API 403
   remains the actual security boundary.

   **Post-Phase-6 addendum** (see decisions.md #50-54): roles and their
   permission sets became fully GUI-configurable. `campaign.roles` +
   `campaign.role_permissions` replace the hardcoded `Role` StrEnum +
   `ROLE_ACTIONS` dict; a new "Roles & Permissions" page renders an
   actual permissions matrix (click a cell to grant/revoke) and supports
   creating custom roles with any subset of the fixed `Action` catalog.
   `Action` itself stays fixed (each value is a real
   `require_action(Action.X)` call already wired into an endpoint - there
   would be nothing for a GUI-invented action to gate). Two guards prevent
   a lockout: `SUPER_ADMIN`'s permissions can't be edited (always every
   action), and system roles can't be deleted. `GET /auth/me` now returns
   the user's actual computed permission list (not just their role name),
   so `useAuth().can()` reads real backend state directly - the static
   frontend permission mirror this phase originally built is gone, along
   with the drift risk it was flagged as carrying. A useful consequence,
   verified live: editing a role's permissions takes effect for every
   user holding that role immediately, using their existing session
   token, since permissions are computed fresh per request rather than
   baked into the JWT.
7. **Analytics** — done, verified live against real production data (see
   `docs/decisions.md` #55-60): closed a real gap where a campaign run
   never naturally left `RUNNING` once dispatch finished - `worker-
   message-events` (a real consumer for the first time; `campaign.
   message-events` had existed since Phase 5 with nothing reading it)
   detects every message reaching a terminal status and flips the run to
   `COMPLETED`, publishing to `campaign.analytics.events`, which
   `worker-analytics` (also real for the first time) consumes to compute
   and cache that run's rollup in `campaign.analytics_rollups` - once,
   not on every dashboard view. Reusable primitives (`app.analytics.
   core_metrics/engagement/conversion`, callable with an arbitrary
   MSISDN set + window, not hardcoded to one campaign) implement every
   requirements-doc §31/§32 metric: core metrics (audience/sent/failed/
   success rate/actual TPS/zone/channel/demographic breakdown), and the
   exact promo-analytics definitions (APU/HGU/Engagement Rate = HGU/APU/
   avg messages per user/days-active distribution) against
   `chat.chat_history` - a real external table (2.08M rows, read-only
   grant added this phase) whose `session_id` encodes `"{msisdn}-{dd-mm-
   yyyy}"`, verified live against 99.99% of real rows before relying on
   it. Attribution is honestly scoped to what the source database
   actually contains: subscription/product-activation via `campaign.
   customer_subscription_state` (correlation, not causation - documented,
   not overstated), "doctor calls" via `provider.provider_appearances`/
   `provider_impressions` (the real proxy - a marketplace discovery
   event, not a telephony call log, which doesn't exist), and IVR
   engagement omitted entirely (no engagement log exists beyond dispatch
   outcome, already covered by core metrics) rather than fabricated.
   Dashboard: a new Reports & Analytics page (campaign/run selector,
   stat tiles, stacked bar charts colored by message status using the
   dataviz skill's method - validated palette, hover tooltips, legends),
   verified in a real browser against real live-changing production chat
   data, not a static fixture.

## Post-Phase-5 addendum — sender ID, staff notifications, timezone

Operator catch-up (migration 0006), verified live - see `docs/decisions.md`
#41-44 for full detail:

- **Sender ID**: the real per-product values are SMS/IVR = `"15723"`,
  DOCTOR = `"AFYACALL"` (the 0001 seed had DOCTOR wrong). Two-level
  GUI-editable config: `channel_configs.sender_id` is the system-wide
  default per channel (`PUT /system/channels/{channel}/sender-id`);
  `campaigns.sender_id` optionally overrides it for one campaign's entire
  dispatch. Resolved once at queue time (`COALESCE(campaign override,
  channel default)`) and persisted onto `messages.sender_id` so the
  dispatch/retry hot path never re-queries config.
- **Staff compliance roster** (`campaign.staff_contacts`, full CRUD at
  `/staff`): `campaigns.include_staff_notifications`, when true,
  snapshots every active staff contact into that run's `messages`
  alongside the real audience at queue time - same mechanism as the
  audience insert, no FK from `messages` to `staff_contacts` (so removing
  a staff member later never touches historical message records).
- **Audit logging actually writes now**: `GET /audit` existed since Phase
  1 but nothing wrote to it. `app.services.audit.write_audit_log` is the
  first real write-path, used by staff CRUD and channel sender-ID edits -
  both compliance/config-sensitive actions. Full audit coverage of every
  high-impact action remains Phase 6 scope.
- **Container timezone**: `TZ=Africa/Dar_es_Salaam` + `tzdata`, build- and
  run-time, across every service. All business timestamps are already
  `TIMESTAMPTZ` (stored UTC regardless) - this only affects container-local
  time display (logs, etc.), not correctness or storage.

## Post-Phase-7 addendum #2 — phone numbers, SMS 2FA, sliding sessions, self-service profile

Migration `0009`, verified live end-to-end including a first real-browser UI
pass - see `docs/decisions.md` #63-72 for full detail:

- **Phone numbers on users** (`users.phone`, `CHECK ^255[0-9]{9}$`) are now
  a required field on user creation and the delivery channel for every
  security-sensitive message this addendum adds - OTPs and welcome/reset
  credentials alike. Existing users with no phone (in practice, only the
  seed admin) were migrated to `two_factor_enabled=false` rather than
  left at the new default of `true`, avoiding a self-inflicted lockout.
- **SMS 2FA on login** via a purpose-tagged `otp_codes` table
  (`LOGIN_2FA` / `PASSWORD_CHANGE` / `PASSWORD_RESET`) rather than three
  separate tables - same "reusable primitive" pattern as
  `customer_subscription_state`'s `product_code` column. Codes are 3
  digits + 1 uppercase letter at a random position
  (`app.services.otp_service._generate_code`), hashed with the same
  bcrypt helpers as user passwords, sent via the existing
  `app.gateways.kannel.send()` dispatch path with a dedicated
  `OTP_SENDER_ID="AFYACALL"`. `two_factor_enabled` gates *login* OTP
  only - password change and forgot-password always require OTP
  regardless of that setting, since a credential change is treated as
  higher-risk than an ordinary login.
- **Sliding 30-minute sessions** (`SESSION_IDLE_TIMEOUT_MINUTES`), layered
  under a longer JWT ceiling (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES=480`) rather
  than replacing it: the JWT carries a `sid` claim into a DB-backed
  `user_sessions` row, and that row's `last_activity_at` - not the JWT's
  own expiry - is what `get_current_user()` actually checks and extends
  on every request. Caught and fixed a real bug pre-ship: `get_db()`
  never auto-commits, so the session-touch update needs its own explicit
  `db.commit()` independent of the endpoint's business transaction, or it
  silently rolls back on every plain `GET`. Verified live by manually
  aging a session past 30 minutes (rejected despite a still-valid JWT)
  and by aging one to 25 minutes then confirming one real request bumped
  `last_activity_at` to within 68ms of wall-clock now.
- **Non-enumerating forgot-password**: `POST /auth/forgot-password/request`
  always returns the same response shape whether or not the identifier
  matches a real account - a dummy `pending_token` is generated for
  unmatched identifiers that can never successfully verify, so there's no
  API-response oracle for account discovery.
- **Login accepts email or phone** in a single identifier field,
  disambiguated server-side by `^255[0-9]{9}$`.
- **Admin never sees a plaintext password**: `POST /users` no longer
  accepts a client-supplied password at all - a temp password is
  generated server-side and delivered only via welcome SMS (with
  `PORTAL_URL`); a new `POST /users/{id}/reset-password` applies the same
  posture to admin-triggered resets.
- **"Manage Users" split from "Roles & Permissions"** into two dedicated
  portal pages/nav items - the former is user CRUD plus new
  phone/2FA-status/last-login (timestamp, browser, IP) columns; the
  latter (unchanged from the Post-Phase-6 addendum) is the role → action
  matrix. A new self-service `/profile` page (reached from the sidebar's
  user-identity row) covers name/email/phone edits, the 2FA toggle
  (disabled without a phone), and an OTP-gated change-password flow.
- **One shared `OtpInput` frontend component** (4 auto-advancing,
  auto-verify-on-completion boxes, plus an explicit Confirm-button
  fallback) reused across login 2FA, forgot-password, and profile
  change-password - verified in a real browser (a disposable Playwright
  container on the app's own Docker network, correct Host header/SNI, no
  mocking) rather than only at the component level: the 2FA step
  genuinely withholds a token until verified, the 4th typed character
  genuinely auto-submits with zero clicks, and `/users` genuinely renders
  a just-completed login's real last-login/browser/IP data.

## Post-Phase-7 addendum #4 — idle auto-logout enforced client-side too

A genuinely idle tab sends no requests at all, so the server-side idle
check inside `get_current_user()` (addendum #2 above) never got a chance
to run - "auto logged out after N minutes idle" silently never fired for
a truly inactive tab. Fixed by adding a client-side idle timer to
`AuthProvider.tsx`: `GET /auth/me` now also returns
`session_idle_timeout_minutes` (previously server-only config), and the
frontend independently tracks elapsed local idle time, forcing a logout
the moment it crosses that value - no request needed to discover the
session had gone stale. Verified with a real ~85-second timed browser
test against a temporarily-shortened 1-minute timeout (restored to 30
afterward): the tab redirected itself to `/login` with a cleared token,
zero interaction, well inside the expected window. See
`docs/decisions.md` #74.

## Post-Phase-7 addendum #5 — pre-logout warning modal

`SessionTimeoutModal` (centered backdrop + card, amber alarm-clock icon,
live countdown, "Stay signed in" / "Sign out now") appears once local idle
time reaches within `min(30s, idleTimeoutMs / 2)` of the real auto-logout
added in addendum #4 - a friendlier notice layered in front of that
existing mechanism, not a replacement for it. The idle-check interval
moved from 15s to 1s ticks so the countdown visibly moves; state is always
recomputed on each tick rather than read back from React state, to avoid a
stale-closure bug in an effect that only re-runs on `[user]`. "Stay signed
in" resets the local idle clock (a real click already extends it via the
existing activity listeners) and hides the modal; ignoring it still ends
in the same `logout()` from addendum #4. Verified with one continuous
timed browser test covering the full cycle - warning appears with a
genuinely decrementing countdown, "Stay signed in" provably resets the
clock (confirmed still-authenticated well past where the original,
un-reset timeout would have fired), the warning reappears on its own new
schedule, and full auto-logout still fires when truly ignored. See
`docs/decisions.md` #75.
