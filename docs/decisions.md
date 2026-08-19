# Decisions & Open Items

## Confirmed decisions (asked directly during Phase 1 planning)

1. **Ambiguous Kannel response** (timeout / unrecognized body after
   submission — we genuinely don't know if the message went out): mark
   `messages.status = 'FAILED_UNCONFIRMED'`, **never auto-retry**. Surfaced
   to an ops review queue for a manual resend decision instead. Chosen over
   auto-retry because Kannel's `sendsms` HTTP API returns no idempotency
   token, so blind retry on an ambiguous outcome risks a real duplicate
   SMS/call to a customer — judged worse than requiring manual follow-up.

2. **Auth**: local JWT auth against a new `campaign.users` table with the 5
   fixed roles (`SUPER_ADMIN`, `CAMPAIGN_MANAGER`, `OPERATIONS`, `ANALYST`,
   `VIEWER`). No external SSO integration in v1. Auth is isolated behind
   `app.core.security`/`app.core.deps` so OIDC/SSO can be swapped in later
   without touching the RBAC model.

3. **Channel TPS split** under the global 200 ceiling: placeholder config
   (SMS 140 / IVR 40 / Doctor 20), stored in `campaign.channel_configs` as
   editable data — not hardcoded — so it can be retuned without a code
   change once real usage patterns are known. **Not authoritative** — needs
   real business input once Phase 5 dispatch is live.

## Corrected during implementation (worth recording, not just fixing silently)

4. **MSISDN length**: the requirements doc's ASCII placeholder
   `255xxxxxxxxxxx` was miscounted at design time as 13 digits total
   (`CHAR(13)`). While verifying the Phase 1 migration live against the
   real database, a smoke-test insert of a genuine Tanzanian number
   (`255712345678`, 12 digits) was rejected by the very check constraint
   meant to validate it — which caught the error immediately. Cross-checked
   against the legacy PHP scripts' actual production regex
   (`^255\d{9}$`, i.e. `255` + 9 digits = 12 total) and real Tanzanian
   mobile numbering (country code + 9-digit subscriber number): 12 digits
   is correct. Fixed to `VARCHAR(12)` / `^255[0-9]{9}$` across the
   migration and all SQLAlchemy models before any real data was loaded
   (migration was downgraded and re-applied clean).

## Still open — need business sign-off before the relevant phase

These were flagged during architecture design with a default chosen only to
keep moving; none are blocking for Phase 1, but should be confirmed before
the phase that depends on them ships.

5. **Zone granularity**: legacy data shows both `TERRITORY` (finer) and
   `COMMERCIAL_REGION` (coarser). Schema supports either via
   `zone_configs.parent_zone_id`, seeded from legacy values. Needs: which
   granularity is the operative "zone" for daily quota allocation, and
   whether the hierarchy must be enforced in rotation quotas. — *Phase 4*.

6. **DND regime scoping**: default is one global DND state (union of all
   active `dnd_lists` records), applied uniformly to every campaign. Needs:
   whether different campaign categories (e.g. regulatory vs. promotional)
   should have independent DND regimes. — *Phase 3*.

7. **"Subscribed to any product" exact definition**: schema supports a
   per-product `customer_subscription_state` with a campaign-level
   configurable `product_exclusion_codes` list (generalizing the legacy
   `matched_msisdns.py` DOCSUB+CHATBOT precedent). Needs: the default
   exclusion set for acquisition campaigns, and whether any products are
   deliberately excluded from the rule. — *Phase 3*.

8. **Cooldown rules**: default 7 days, scoped per `campaign_category` (not
   global — a customer could be in an SMS campaign and an IVR campaign the
   same week unless categories are linked). Needs: actual duration and
   whether cross-channel cooldown linkage is required for compliance. —
   *Phase 4*.

9. **Channel priority under contention**: no cross-channel preemption in
   v1 — each channel independently draws from its static TPS
   sub-allocation. If SMS should be able to outrank Doctor when both are
   backlogged, that needs a priority-weighted scheduler, currently out of
   scope. — *Phase 5*.

10. **Kannel response-code enumeration**: the classifier (SENT / DEAD /
    FAILED_UNCONFIRMED) needs a real enumeration of `sendsms` response
    bodies from the live gateway at `192.168.1.10` — the legacy scripts
    never handled this either (they just logged curl success/failure), so
    there's no prior art to lean on. Needs a short spike against the real
    gateway. — *Phase 5*.

11. **Real per-channel TPS split values** (item 3 above) — needs
    confirmation from actual usage/business priority, not just the
    placeholder. — *Phase 5*.

12. **Kafka payload schema**: plain JSON with a versioned envelope, no
    schema registry service (keeps the compose service count down).
    Revisit only if external teams need strict schema contracts. — no
    urgency.

## Corrected during Phase 2 implementation

13. **nginx upstream DNS caching**: `proxy_pass http://backend-api:8000` (a
    bare hostname, no variable) resolves once at nginx startup/config-load
    and is then cached for the container's lifetime. The first time
    backend-api was recreated (a normal rebuild/redeploy, not a failure),
    nginx kept sending traffic to the old container's dead IP and every
    request 502'd until nginx itself was restarted. Fixed by adding
    `resolver 127.0.0.11 valid=10s;` (Docker's embedded DNS) and routing
    `proxy_pass` through a `set $backend_upstream ...`/`set
    $frontend_upstream ...` variable, which forces nginx to actually
    re-resolve the hostname per the TTL instead of once. This matters
    operationally: without it, every backend-api/frontend deploy would
    require a manual `nginx` restart to avoid an outage.

14. **SQLAlchemy models silently sending explicit NULL for server-default
    timestamps**: several models not using `TimestampMixin`
    (`BaseVersion.created_at`, `AudienceSnapshot/AudienceMember.created_at`,
    `DndRecord.created_at`, `MessageAttempt.attempted_at`,
    `Event.created_at`, `AuditLog.created_at`) were declared as bare
    `Mapped[datetime]` with no `mapped_column(server_default=...)`. The
    actual DB column has `DEFAULT now()` (set in the 0001 migration's raw
    SQL), but SQLAlchemy doesn't know that unless told - so it sent an
    explicit `NULL` on INSERT, hitting the `NOT NULL` constraint. Caught
    live: the first real `commit_import()` call failed with
    `NotNullViolation` on `base_versions.created_at`. Fixed all 7
    occurrences (`func.now()` added to each `mapped_column`) - the
    `app.models.*` docstring's warning about keeping the ORM mirror in
    sync by hand was correct to be worried about, and this was exactly the
    kind of drift it anticipated.

15. **structlog reserved `event` kwarg collision**: `logger.exception(...,
    event=event)` in `ingestion_worker.py` crashed with `TypeError:
    exception() got multiple values for argument 'event'` because
    structlog's logging methods use `event` as their own first positional
    parameter (the log message). This bug was actively *masking* the real
    NotNullViolation above in the first failure - the exception handler
    itself threw before the real traceback could be logged cleanly (though
    Python still printed both tracebacks chained, so the root cause was
    still visible). Fixed by renaming the kwarg to `kafka_event`. Lesson:
    never name a structlog kwarg `event`.

16. **`stage_import` had no resumability story for a mid-stream kill**:
    discovered via an actual incident during real-scale testing (see
    below) - a `stage_requested` event only triggered `stage_import` when
    `imports.status` was `IMPORT_CREATED`/`UPLOADED`; if a worker was
    killed mid-stream (not a clean Python exception, e.g. `docker rm -f`,
    OOM-kill, host reboot), the row was left in `VALIDATING` with partial
    staging data and Kafka redelivery of the original event would have
    just silently no-op'd (status didn't match the expected set) even if
    the message *had* still been in Kafka. Fixed two ways: (a)
    `stage_import` now deletes any existing staging rows for the import
    before re-streaming, making it safe to redo from scratch regardless of
    how far a prior attempt got; (b) the worker now also accepts
    `VALIDATING` as a valid starting state for `stage_requested`. Also
    added `POST /imports/{id}/retry-staging` (gated by `IMPORT_CREATE`) as
    an operator-facing recovery lever for the rarer case where the
    triggering event is gone from Kafka entirely (see the incident below) -
    "operators must be able to recover without SSH" applies to imports,
    not just campaign execution.

### Incident: full Docker stack (containers + images + volumes) removed mid-test

While running the real-scale 17M-row ingestion test, something external to
this session removed the entire `campaign-engine` Docker stack - not a
graceful `stop`, but containers *and* images gone (`docker compose ps -a`
empty, `docker images` showed none), and the named volumes
(`kafka_data`/`redis_data`/`import_uploads`) came back empty on the next
`docker compose up` despite still being listed by `docker volume ls` (i.e.
they were re-created empty under the same names, consistent with a
`docker compose down -v` or `docker system prune --volumes` having run).
`last` showed an active `derrick` session independent of this one, so this
was very likely manual intervention on the host, not a bug in this system.

What this proved, and what it didn't:
- **Postgres (the actual source of truth) was completely unaffected** -
  external to Docker entirely. Import #2's row was still exactly where the
  interrupted worker left it: `status=VALIDATING`, and **10.98M of the 17M
  rows were still durably present** in `import_staging_rows` from the
  per-chunk-commit design - concrete proof that "commit per chunk, not one
  giant transaction" actually protects real progress across a hard kill,
  not just in theory.
- Kafka's own storage was wiped along with everything else, so the
  `stage_requested` event that would have triggered a self-healing
  redelivery was gone too - the automatic at-least-once recovery path
  (designed for "worker crashes, Kafka survives") doesn't cover "the
  broker's own storage is wiped." This is what motivated adding the manual
  `retry-staging` endpoint (item 16) rather than treating Kafka redelivery
  as the only recovery path.
- After rebuilding all images and redeploying, `POST
  /imports/2/retry-staging` correctly discarded the 10.98M stale rows and
  re-streamed the full file from scratch with the exact same flat-memory
  behavior as the first attempt (see verification below).

## Portal authentication (post-Phase-3 gap fix)

27. **The frontend had a login page and JWT storage from Phase 1 but no
    actual route protection or visible sign-in entry point** - every
    portal page rendered regardless of auth state, silently 401'd on data
    fetches, and there was no nav link to `/login`, no logout, and no
    indication of who (if anyone) was signed in. Caught by direct user
    feedback, not internal testing - a reminder that "the API enforces
    auth" (true, and still the real security boundary) is not the same as
    "the portal has a usable auth experience."

    Fixed with a standard client-side-JWT pattern (chosen because the
    architecture deliberately keeps auth stateless via a bearer token in
    localStorage, not cookies - see decisions.md item 2; that rules out
    Next.js edge middleware, which has no access to localStorage):
    - `AuthProvider` (`src/features/auth/AuthProvider.tsx`) - a React
      context that resolves the current user via `GET /auth/me` on mount
      and exposes `login`/`logout`.
    - All existing portal pages moved into a `(portal)` route group whose
      `layout.tsx` wraps them in `RequireAuth`, which redirects to
      `/login` whenever there's no valid session - `/login` itself sits
      outside the group (no nav chrome, and redirects *away* to `/` if
      already authenticated).
    - `NavShell` now shows the signed-in user's email/role and a sign-out
      control.
    - `apiFetch` dispatches a shared `campaign-engine:auth-expired` event
      on any `401` (which `get_current_user` is the sole source of, so a
      401 always means "not authenticated" - never confused with a `403`
      RBAC denial, which stays a normal in-page error); `AuthProvider`
      listens and force-redirects to `/login` from wherever the app
      currently is, covering a token expiring mid-session, not just at
      initial load.

    Verified live through the real deployed stack: server-rendered HTML
    for `/` (unauthenticated) shows the `RequireAuth` loading state (not
    portal content) before the client-side redirect fires; `/login`
    renders outside the `(portal)` route tree with no nav chrome; the
    backend issues/validates tokens correctly (`POST /auth/login` →
    `GET /auth/me` round-trip confirmed) and still 401s with no token. The
    actual client-side redirect (curl can't execute JS) needs confirming
    in a real browser.

## Phase 4 — Campaign Engine / Rotation

28. **Zone quotas simplified from "compute a base-wide eligibility snapshot
    once, then slice it across runs" (the original §5 sketch) to "recompute
    eligibility per zone on every rotation call."** Trades a bit of redundant
    anti-join work (once per zone instead of once per base) for a much
    simpler resumability story — a zone's rotation is one self-contained
    transaction with no dependency on a separately-materialized snapshot.
    Justified by the Phase 3 measurement that the full-base anti-join runs
    in 18.5s at 16.9M rows; one zone's slice of that is proportionally
    cheaper, so this hasn't needed revisiting.

29. **`POST /campaigns` creates a campaign directly in `CONFIGURED` status**,
    not the documented `DRAFT → CONFIGURED` two-step. There's no
    partial-save UX yet (the portal form is a single submit), so the extra
    state transition would be unused ceremony. `DRAFT` stays a valid,
    unused-for-now status for when incremental save is built.

30. **A standalone `worker-rotation` was deliberately not built.** Rotation
    (rank + slice + insert + advance cursor) is one atomic transaction
    per zone; splitting "select a zone's slice" and "advance its cursor"
    across two processes would need cross-process coordination for what is
    fundamentally indivisible. `worker-audience` performs rotation directly
    (`app.rotation.engine.rotate_zone`, called from
    `app.services.campaign_service.generate_audience`). `worker-rotation`
    remains a heartbeat stub — a candidate future role is scheduling *which*
    runs are due, not performing rotation itself.

31. **Resumability verified live, two ways:**
    - **Real crash via Kafka redelivery**: created a campaign run, `docker
      kill -9`'d `worker-audience` in the gap between the run being created
      and the worker consuming the triggering event (so the consumer group
      offset was never committed), then restarted the worker. It re-consumed
      the same message from the last committed offset and completed the run
      cleanly — exactly 7 members, matching the fixture, no duplicates.
    - **Deterministic mid-rotation state**: bypassing Kafka, manually called
      `rotate_zone()` for one zone only and committed (simulating "the
      worker died right after this zone's transaction committed, before the
      next zone"), then invoked the real `generate_audience()` resumption
      path. It logged `zone_already_done` for the pre-committed zone,
      rotated the remaining three zones, and produced the same 7-member,
      zero-duplicate result. This is the actual mechanism (see
      `app.rotation.engine`/`app.services.campaign_service` docstrings) that
      makes rotation safe to resume after a kill at any point in the
      per-zone loop, not just before the first zone.
    - Cycle-wrap logic was exercised as a side effect: a second run against
      the same exhausted 7-row zone pool correctly advanced
      `rotation_state.cycle_number` and wrapped `last_offset` back to 0
      before selecting.

32. **Exact-count verification reused the Phase 3 "Phase3 Eligibility Test
    Base" fixture** (10 rows, 3 DND, 4 zones) rather than building a new
    one — a campaign configured with no product exclusions and no cooldown
    category selects exactly `10 - 3(DND) = 7` members, matching hand
    computation exactly and confirming the rotation engine's DND anti-join
    composes correctly with the Phase 3 eligibility logic it reuses.

33. **Frontend campaign creation and run-trigger UI**, built on the same
    single-page master-detail pattern as Imports/Bases (no dedicated
    `/campaigns/new` route or modal) so it matches the rest of the portal.
    Added a `Select` component (native `<select>` styled to match `Input`)
    since no dropdown primitive existed yet. The new-campaign form's zone
    allocation inputs are generated dynamically from `GET /system/zones`
    rather than hardcoded, so it stays correct if zones are added/removed.
    Verified live through a real browser (Playwright, not curl): filled
    and submitted the form against the real API (base picker populated
    with the real "Phase3 Eligibility Test Base", zone inputs summing to
    a live "100% allocated" indicator), triggered a run, watched the
    client-side 3-second poll flip status `CONFIGURED → READY` without a
    manual refresh, and opened the members table — 7 rows, matching the
    backend verification in #31/#32 exactly. Zero browser console errors
    across the whole flow. Test campaign/run cleaned up from the
    production DB afterward.

## Phase 5 — Kafka Execution / Dispatch

34. **Bug found and fixed live: GCRA burst == rate does not converge to
    the configured ceiling within any realistic campaign-run duration.**
    The standard GCRA parameterization (burst capacity == rate, "bucket
    starts full") was implemented first and measured against the real
    Redis instance: a cold key let a full extra second's worth of
    requests through immediately, and a *5-second continuous hammer*
    still ran at 169/s against a 140/s configured rate (measured, not
    calculated) - the overshoot only amortizes away as the window
    approaches infinity, so for any run of realistic duration the
    "ceiling" would run meaningfully hot for its entire length. Since
    this ceiling exists specifically so the platform never again
    overwhelms the real SMSC the way the uncoordinated legacy scripts
    did, this was treated as a real bug, not a tuning nuance. Fixed by
    setting burst=0 (strict pacing, no allowance beyond one request per
    1/rate-second slot, including the very first request after an idle
    period) - re-measured afterward at 139/140 in 1s and 139.0/s
    sustained over 5s, matching the configured rate almost exactly. See
    `app/redis/ratelimit.py` for the full reasoning kept in-line since
    this is the single most consequential parameter in that file.

35. **Bug found and fixed live, affecting every Kafka-consuming worker in
    the codebase (not just Phase 5's new ones): skipping a commit on a
    per-message failure does not actually guarantee redelivery.** The
    established pattern since Phase 2 (`except Exception: log; rollback;
    continue` - deliberately *not* calling `consumer.commit(msg)`) was
    written on the assumption that skipping the commit alone causes the
    same message to be redelivered on the next `poll()`. It does not,
    within a single running process: librdkafka's fetch position already
    advances past a message once `poll()` returns it, commit or no
    commit. If a *later* message is then processed successfully and
    commits, that commit's offset high-water-mark silently jumps past the
    earlier failed one - Kafka offset commits are one moving watermark
    per partition, not sparse per-message acknowledgments - permanently
    losing the failed message with no exception, no log line indicating
    loss, and no recovery even across a future restart. This only bites
    a narrower case than every crash-recovery test already run this
    session (those killed the *whole worker*, which happens to not
    trigger the gap): a single message erroring transiently while the
    worker keeps running and later messages succeed. Found while writing
    `app.workers.dispatch_worker` (a genuinely new instance: the rate
    limiter's bounded wait needed a redelivery story) and traced back to
    being a latent, live bug in `worker-ingestion` and `worker-audience`
    too. Fixed everywhere it appears with an explicit
    `consumer.seek(TopicPartition(...))` back to the failed message's own
    offset before the next `poll()`, so it is genuinely re-fetched in
    place rather than silently skipped - see the module docstring in
    `app/workers/dispatch_worker.py` for the full explanation (the other
    three workers point back to it rather than repeating it).

36. **Message state machine simplified**: the documented path
    `SUBMITTING → FAILED → RETRYING → (SENT | DEAD)` includes a distinct
    transient `FAILED` `messages.status` between an attempt and the
    retry/dead decision. The implementation skips that intermediate
    persisted state and transitions directly from `SUBMITTING` to
    `RETRYING`/`DEAD`/`SENT`/`FAILED_UNCONFIRMED` in one update, since the
    attempt-level detail (http_status, response body, coarse outcome) is
    already fully captured in `message_attempts` for every attempt
    regardless - a transient `FAILED` row on `messages` itself would be
    an extra write with no additional observability. `message_attempts.
    outcome` also collapses the richer `DispatchOutcome` 4-way
    classification (SENT/FAILED_PERMANENT/FAILED_TRANSIENT/
    FAILED_UNCONFIRMED, which drives retry decisions) down to the
    schema's 3-value CHECK constraint (SENT/FAILED/AMBIGUOUS) - the finer
    distinction that matters for retry-worthiness lives in
    `messages.status`, which already has the full 9-value enum.

37. **Kannel response classification** (resolves the "needs real business
    input" flag from decisions.md item 10): 200/202 with a body starting
    `"0:"` → SENT; 400/401/403/404 → FAILED_PERMANENT (DEAD immediately,
    no retry - a bad request/bad auth/forbidden/unknown-service won't be
    fixed by retrying the identical request); 500/503 → FAILED_TRANSIENT
    (RETRYING with exponential backoff, 30s/60s/120s/240s capped at 300s,
    up to `channel_configs.default_retry_policy.max_attempts` - default
    5 - then DEAD); a network-level exception (timeout, connection
    refused/reset) or any other status/body shape → FAILED_UNCONFIRMED,
    never auto-retried (confirmed decision - Kannel's HTTP API has no
    idempotency token, so a blind retry on a genuinely ambiguous outcome
    risks a real duplicate send). Verified live against a mock Kannel
    server exercising all four paths through the real dispatch pipeline
    (see below) - the real gateway's exact response format still needs
    one live confirmation with a safe test number before this is treated
    as fully validated against production Kannel, not just the documented
    HTTP interface contract.

38. **Pause/resume is DB-driven, not Kafka-native**, exactly as designed:
    a dispatcher's claim CAS
    (`UPDATE messages ... FROM campaign_runs WHERE ... status='QUEUED'
    AND campaign_runs.status='RUNNING'`) simply doesn't match while a run
    is PAUSED, so a still-QUEUED message for a paused run is left
    untouched no matter how many times a dispatcher polls it - verified
    live by pausing a run, then *starting* (not stopping) its dispatch
    consumer afterward and confirming the messages stayed QUEUED despite
    the consumer being active and polling. `resume` republishes every
    still-QUEUED message for that run back onto its dispatch topic (the
    same "DB is authoritative, Kafka is a refillable work queue"
    principle already used for retry) - chosen over leaving the consumer
    offset uncommitted and blocking that topic partition indefinitely,
    which would head-of-line-block unrelated messages sharing the same
    partition (dispatch topics are shared across all campaigns/runs,
    keyed by customer_msisdn). `stop` is terminal: CANCELS the run and
    bulk-updates every CREATED/QUEUED/RETRYING message to CANCELLED;
    anything already SUBMITTING/SENT/DEAD/FAILED_UNCONFIRMED is left as
    its real outcome, never overwritten.

39. **Frontend Execution Monitor UI**, built on the same live-polling
    pattern as the rest of the portal, added to the previously-stub
    `/runs` page: every campaign run with start/pause/resume/stop
    controls appropriate to its current status, and an expandable
    per-run message-status-count panel backed by a new
    `GET /messages/runs/{id}/summary` endpoint (a single grouped-COUNT
    query, not a paginated row fetch - stays cheap on a run with millions
    of messages).

    **Bug found and fixed live while browser-testing this page**: the
    poll loop was initially gated on "is any run's *last-fetched* status
    still active" (`PENDING/AUDIENCE_GENERATING/RUNNING/PAUSED`). Clicking
    Start only writes an outbox event and returns immediately - the very
    next status fetch can still show the pre-start status (e.g. READY)
    before worker-scheduler has caught up - so the gate saw "nothing
    active" and never started polling again, leaving the page frozen on
    a stale status forever. Caught by an actual Playwright screenshot
    still showing "READY" after clicking Start, cross-checked against the
    real API showing the run had already reached RUNNING and completed -
    a real functional bug, not a screenshot-timing artifact. Fixed by
    always polling while this page is mounted (its whole purpose is a
    live view, so "poll unconditionally" is the correct behavior here,
    not a compromise).

40. **Kannel classify() confirmed against one real live send through the
    actual gateway** (192.168.1.10), closing the open item from #37/"Known
    follow-ups": called `app.gateways.kannel.send()` directly (bypassing
    the campaign/audience/dispatch pipeline entirely - a single, isolated
    request, not a full run) against an operator-supplied safe test
    MSISDN. Real response: HTTP 202, body `"0: Accepted for delivery"` -
    classified SENT, exactly matching the assumed format `classify()` was
    built against. No other campaign run was RUNNING/PAUSED at the time
    (checked first), so this was unambiguously the only live send that
    occurred.

## What was verified live during Phase 5 (not just designed)

- **GCRA rate limiter, live against the real Redis instance** (not a
  calculation): hammered a single channel for 1s and 5s continuously,
  confirmed the burst=rate bug (169/s sustained against a 140/s ceiling),
  fixed to burst=0, re-measured at 139/140 (1s) and 139.0/s (5s
  sustained) - see item 34. Also verified the channel and global limiters
  are enforced independently but both gate every attempt (draining
  IVR+DOCTOR's own channel ceilings does not, by itself, exhaust the
  shared global bucket).
- **Kannel response classification, live HTTP round trips** through a
  purpose-built mock Kannel server (`ThreadingHTTPServer` on the real
  `campaign-net` Docker network, routing behavior by MSISDN suffix) with
  a real dispatch-sms worker instance pointed at it (the production
  worker was stopped first so no test traffic could reach the real
  gateway) - all 4 `DispatchOutcome` paths confirmed end-to-end through
  the real state machine: SENT (200), DEAD via FAILED_PERMANENT (400, no
  retry), RETRYING → DEAD-eventually via FAILED_TRANSIENT (503, backoff
  observed live: attempt_count advanced 1→2→3 with growing
  next_attempt_at, retry-scheduler visibly re-dispatching it), and
  FAILED_UNCONFIRMED via a real client-side timeout (mock server made to
  sleep past the 8s httpx timeout). `classify()` was additionally unit
  verified against 12 synthetic input combinations covering every branch.
- **DLQ and message-events**, both real Kafka topics read back via
  `kafka-console-consumer`: every DEAD message produced a matching
  `campaign.dispatch.sms.dlq` event, and every attempt produced a
  `campaign.message-events` event with the correct status/outcome -
  confirming the transactional-outbox write-path (`app.services.outbox.
  write_event`) works correctly for Phase 5's new event types, not just
  the audience/import lifecycle events it already carried.
- **Full run lifecycle** (start/pause/resume/stop) against real campaigns
  created through the real API, using synthetic fixture bases inserted
  directly (same methodology as the Phase 3/4 fixtures): start correctly
  transitions READY→RUNNING and materializes+publishes messages; pause
  correctly blocks new dispatch claims (proven with the dispatch consumer
  *running*, not stopped, during the pause window); resume republishes
  and completes dispatch of the exact same messages with no loss or
  duplication; stop cascades CANCELLED to every not-yet-dispatched
  message while leaving already-resolved ones untouched; a stale/
  already-CANCELLED message consumed after a stop correctly no-ops via
  the same CAS (`dispatch.claim_skipped`), for free, from the existing
  idempotency design.
- **Manual retry endpoint**: retried a FAILED_UNCONFIRMED message
  successfully (→ RETRYING → picked up by retry-scheduler), and confirmed
  a 409 when attempting to retry an already-SENT message.
- **Execution Monitor UI**, real browser (Playwright), full click-driven
  flow against the real deployed stack (mock Kannel server still in
  place for this - see item 39): Start → live poll picks up READY→RUNNING
  with no manual refresh → Pause → status flips to PAUSED, Resume/Stop
  controls appear → Resume → republish confirmed ("1 queued message(s)
  republished") and status returns to RUNNING. Zero browser console
  errors across the whole flow. The polling bug in item 39 was caught
  exactly this way - a screenshot that didn't match the real backend
  state - not by code review.
- All test campaigns/runs/messages/bases created for this phase's
  verification were deleted from the production database afterward; the
  mock Kannel server and its dedicated dispatch-worker instance were
  removed and the real `worker-dispatch-sms` container (which never
  received any test traffic - it was stopped for the full duration of the
  mock-server testing) was restarted.

## Post-Phase-5 addendum — configurable sender ID, staff notification roster, timezone

Operator-supplied catch-up items, applied as migration 0006 plus the
corresponding backend/frontend changes (not part of any single numbered
phase, since they cut across campaigns/messages/system-config/portal):

41. **Sender ID correction and GUI configurability**: the real per-product
    sender IDs are SMS/IVR = `"15723"`, DOCTOR = `"AFYACALL"` (matching the
    legacy `drmaster.php` vs. `smsmaster.php`/`ivrmaster.php` split) - the
    0001 seed data had DOCTOR wrong (`"15723"`, copied from the other two).
    Fixed as a data migration, and made genuinely GUI-editable at two
    levels rather than only fixed in seed data:
    - **System-wide default per channel**: `PUT /system/channels/{channel}
      /sender-id`, editable from System Configuration - what a campaign
      falls back to when it doesn't specify its own.
    - **Per-campaign override**: `campaigns.sender_id` (nullable) - when
      set, overrides every channel's default for that campaign's entire
      dispatch. Resolved once at queue time via
      `COALESCE(campaigns.sender_id, channel_configs.sender_id)` in the
      same set-based `INSERT...SELECT` that materializes `messages`, and
      persisted onto `messages.sender_id` itself (denormalized, same
      rationale as `channel` already being denormalized there) so the
      dispatch/retry hot path never re-queries `channel_configs` per
      message, and so a retry hours later still uses the sender ID that
      was actually configured at send time, not whatever the default
      happens to be by then.
    - The campaign-creation form shows a live hint of what "blank" resolves
      to, computed from the actually-selected channels against real
      `channel_configs` data (not hardcoded) - e.g. selecting only SMS
      shows `Leave blank to use the default for SMS: "15723"`; selecting
      channels with different defaults shows both and asks for an explicit
      choice.

42. **Staff compliance notification roster** (`campaign.staff_contacts`,
    full CRUD at `/staff`): when a campaign has `include_staff_notifications
    = true`, every currently-active staff contact is snapshotted into that
    run's `messages` at queue time, alongside the real audience - same
    `INSERT...SELECT ... ON CONFLICT DO NOTHING` mechanism as the audience
    portion, just sourced from `staff_contacts` instead of
    `audience_members`. A staff member who also happens to be in the real
    audience is naturally deduplicated by the existing
    `(campaign_run_id, customer_msisdn, channel)` uniqueness constraint -
    never a duplicate send. Deliberately **no foreign key** from `messages`
    to `staff_contacts` (same pattern as `audience_members` already storing
    `customer_msisdn` as plain data, not an FK to a customers table) - a
    staff member removed from the roster later can never retroactively
    alter or break a historical message record, and `DELETE /staff/{id}`
    can be a genuine hard delete rather than a soft-delete workaround.

43. **Audit log write-path built for real** (`app.services.audit.
    write_audit_log`): `GET /audit` has existed since Phase 1, but nothing
    ever wrote to `audit_logs` before this - it was a real, empty table.
    The staff roster (explicitly compliance-sensitive - it controls who
    receives every campaign message) was the first feature to actually
    need this, so its write-path was built now rather than deferred
    further to Phase 6. Every staff create/update/delete and every channel
    default sender-ID edit writes one row with `old_value`/`new_value`
    JSONB diffs and the acting user's id. `AuditLogOut` and the Audit Log
    portal page were extended to surface that diff (a compact
    red-old → green-new inline rendering) rather than just the bare
    action/entity that was there before. Full audit coverage across every
    high-impact action (import approval, campaign start/pause/stop, ...)
    remains Phase 6 scope - this only covers the two write-paths just
    built.

44. **Container timezone set to `Africa/Dar_es_Salaam`** (`TZ` env var +
    `tzdata` package, both build- and run-time) across every service -
    backend-api, migrate, all workers, frontend, nginx, kafka, kafka-init,
    redis. Every business timestamp is already `TIMESTAMPTZ` and stored
    UTC internally regardless of session timezone (see the Idempotency/
    Partitioning sections of `docs/architecture.md`), so this changes
    nothing about correctness or storage - it only makes container-local
    time (log lines, anything rendered from a naive local-time call) match
    the business's real timezone instead of defaulting to UTC. Verified
    live: `date` inside `backend-api` and `frontend` both report `EAT`
    (UTC+3) after redeploy.

Verified live (real API + real browser, not just designed): staff CRUD
(create, duplicate-MSISDN 409, update, hard delete) each produced a
correct audit row; sender ID resolution tested both paths through the
real dispatch pipeline against a mock Kannel server (no override -> the
real per-channel default was received as `from=`; explicit override -> the
override string was received) with `include_staff_notifications=true`
correctly adding a snapshotted staff message alongside the real audience
member; the channel sender-ID edit endpoint round-tripped and was
audit-logged. All test data (campaigns, runs, bases, the one test staff
contact, and its test audit rows) was removed afterward so the operator's
first real audit log view starts clean.

## Phase 6 — Operations (RBAC enforcement, audit logging, user management)

45. **Bug found and fixed live, real severity: several read endpoints had
    zero authentication - not even "must be logged in," let alone a role
    check.** `GET /bases`, `GET /bases/{id}/versions`, `GET /dnd/lists`,
    `GET /campaigns`, `GET /campaigns/{id}`, `GET /campaign-runs`,
    `GET /campaign-runs/{id}`, `GET /imports`, `GET /imports/{id}/preview`,
    `GET /system/zones`, and `GET /system/channels` had no `Depends(...)`
    at all, discovered by grepping every router for
    `require_action`/`get_current_user` coverage at the start of this
    phase - there is no global auth middleware in `app/main.py` (only
    `CorrelationIdMiddleware`), so each endpoint is individually
    responsible for its own auth, and these eleven simply never got it.
    Confirmed live: an unauthenticated `curl` to every one of them returned
    real campaign/import/base/DND/config data with a 200, not a 401.
    Fixed by adding `dependencies=[Depends(require_action(Action.
    CAMPAIGN_VIEW))]` to all eleven - `CAMPAIGN_VIEW` because that's
    already the de facto "you have read access to the operational domain"
    permission (it already gated `audience`/`messages` GETs, which aren't
    literally campaign data either), not because these are narrowly
    "campaign" endpoints. Re-verified live after the fix: all eleven now
    401 with no token, and a VIEWER-role token gets 200 on reads and 403
    on every mutation tried (campaign create, run start, staff list).

46. **User management, built for real** (`/users`, full CRUD, gated by the
    existing `Action.USER_MANAGE` which was already defined but had no
    router behind it - the Settings page literally said "ships in Phase
    6"). Two self-protection guards, checked live: a user cannot
    deactivate or delete their own account (`400`, not a 403 - this isn't
    a permission problem, it's a "don't lock yourself out" problem), and
    cannot change their own role. Every create/update/delete writes an
    audit row with old/new value diffs, same as staff CRUD.

47. **Audit logging extended to every remaining high-impact action** (the
    write-path itself, `app.services.audit.write_audit_log`, was built in
    the Phase 5 addendum for staff CRUD and channel sender-ID edits only -
    see item 43): import approve/reject/retry-staging/retry-commit,
    campaign create, campaign-run start/pause/resume/stop, manual message
    retry, and subscription sync. Deliberately **not** wired onto
    lower-impact/precursor actions that don't change production state or
    send anything (import upload/staging-trigger, campaign-run creation/
    audience-generation-request) - matching the existing DND/staff/
    channel-config precedent of only auditing state changes and
    real-world-affecting actions, not every read or every intermediate
    step, to keep the audit log meaningful rather than noisy.

48. **Bug found and fixed live during audit-log wiring: the run-lifecycle
    functions in `app.services.dispatch_service` (`pause_run`,
    `resume_run`, `stop_run`, `request_run_start`) already call
    `db.commit()` internally.** Writing the audit log from the API router
    *after* calling them (the first pass) would have committed the audit
    row in a separate, later transaction - for the single most
    consequential action class in this whole system (pausing/stopping a
    live campaign, or starting one), a crash between the two commits would
    leave the state change durable but silently undocumented in the audit
    trail. Fixed by threading `actor_id` into all four functions and
    writing the audit row immediately before each function's own existing
    commit, so the audit entry is atomic with the state change it
    describes - not a "good enough, mostly atomic" compromise. Verified
    live: created a campaign, ran it through start → pause → resume → stop
    against a mock Kannel server, and confirmed all five actions
    (including the initial `campaign.create`) appear in the audit log in
    the correct order with the correct detail (e.g. `resume` recorded
    `{"republished": 1}`).

49. **Frontend RBAC gating** (`frontend/src/lib/permissions.ts`, a hand-kept
    mirror of `backend/app/core/permissions.py`'s `ROLE_ACTIONS`, exposed
    as `useAuth().can(action)`): applied to every mutation control this
    session touched - New Campaign, Generate Audience, Start/Pause/Resume/
    Stop, import upload/scan/create-from-drop/approve/reject/retry, staff
    Add/Edit/Remove, channel sender-ID Edit, subscriber Run Sync, and the
    entire Users & Roles panel. This is explicitly **not** the security
    boundary (the API 403 is, per the architecture doc's own words,
    unchanged by this) - it's ergonomics, so a VIEWER or ANALYST user never
    sees a control that would 403 if clicked. Verified live in a real
    browser as SUPER_ADMIN (all controls present, Users & Roles panel
    fully functional, zero console errors); role-differentiated rendering
    for other roles was verified via the API-level 403 tests rather than
    logging in as each role separately, since the gating logic is a
    direct, mechanical mirror of the exact same `ROLE_ACTIONS` map already
    proven correct server-side.

## Post-Phase-6 addendum — GUI-configurable roles & permissions matrix

Operator-requested catch-up (migration 0007): the 5 roles and their
`ROLE_ACTIONS` mapping were hardcoded Python (a `Role` StrEnum + a dict
literal in `app/core/permissions.py`) - correct, but invisible and
uneditable from the portal. Replaced with two tables, `campaign.roles`
(the assignable role catalog) and `campaign.role_permissions` (which
`Action` each role grants), both fully GUI-editable via a new
"Roles & Permissions" page and `/roles` API.

50. **`Action` stays a fixed code-level enum; roles and their permission
    sets are now the GUI-configurable part.** Each `Action` value
    corresponds to a real `require_action(Action.X)` call already wired
    into a specific endpoint - there'd be nothing for a GUI-invented new
    action to actually gate, so only the *assignment* of existing actions
    to roles is dynamic, not the action catalog itself. `GET /roles/actions`
    exposes that fixed catalog (with human-readable labels) so the matrix
    UI's columns/rows aren't hardcoded on the frontend either.

51. **`role_can()` was deliberately kept a pure, DB-agnostic set-membership
    check** (`action.value in granted_actions`), with the actual "which
    actions does this role have" query isolated in
    `app.services.rbac.get_role_actions` - one query per request, fetching
    a role's whole permission set at once rather than one query per
    action-check. This keeps `role_can()` fast to unit test without a live
    database (`tests/test_permissions.py` still runs with zero DB
    dependency, now against literal action-sets matching migration 0007's
    seed data rather than a removed hardcoded dict - live DB state,
    including any GUI edits, is verified via curl against the real stack,
    same as every other DB-dependent behavior in this codebase).

52. **`users.role`'s old inline `CHECK (role IN (...5 literal values...))`
    was replaced with a real FK to `roles.code`** - the DB now enforces
    "role must be a real registered role" without hardcoding which ones,
    which is what actually makes assigning a custom role to a user safe
    (an invalid role would either violate the FK at write time or, before
    this fix, have silently passed a hand-maintained Python validator that
    could drift from what `role_can()` actually recognized).

53. **Two safety guards prevent a permissions mistake from becoming a
    lockout**: `SUPER_ADMIN`'s permission set cannot be edited via
    `PUT /roles/SUPER_ADMIN` (always literally every `Action` - verified
    live, returns 400) - this guarantees there's always at least one role
    that can fix any other mistake. System roles (the original 5,
    `is_system=true`) cannot be deleted (400, verified live). A role
    currently assigned to any user cannot be deleted regardless of
    system/custom status (409 with the count, verified live) - prevents a
    user silently ending up with a role that resolves to zero permissions.
    Every role create/update/delete writes an audit row with old/new
    action-set diffs, same as every other high-impact action wired in
    Phase 6.

54. **`GET /auth/me` now returns the user's actual computed `permissions`
    list, not just their role name** - this is what makes the frontend's
    `useAuth().can()` correct by construction instead of the hand-kept
    static mirror (`frontend/src/lib/permissions.ts`) Phase 6 built and
    flagged as a drift risk in its own "Known follow-ups": that file is
    now deleted entirely, since a static mirror simply cannot reflect a
    GUI-edited or custom role's permissions. A useful side effect verified
    live: because permissions are computed fresh from the DB on every
    request rather than baked into the JWT at login, editing a role's
    permissions via the matrix takes effect for every user with that role
    **immediately**, using their existing session token - no re-login
    required. Confirmed by granting a custom role's user `staff:manage`
    mid-session and re-testing the exact same still-valid token against
    `GET /staff` (403 → 200, no new login).

## What was verified live for the roles & permissions matrix (not just designed)

- Created a fully custom role (`REGIONAL_MANAGER`) via the real API with a
  hand-picked action set, assigned it to a real test user, and confirmed
  enforcement end-to-end: granted actions passed the 403 check (reached
  real business logic - a 404 on a nonexistent `base_id`, not a
  permission error), non-granted actions (`campaign:start_stop`,
  `staff:manage`) correctly 403'd.
- Confirmed both safety guards live: editing `SUPER_ADMIN`'s actions →
  400; deleting a system role (`VIEWER`) → 400; deleting a role with an
  active user assigned → 409 with the exact count.
- Confirmed the immediate-effect property described in item 54 (grant a
  permission mid-session, re-test the same token, no re-login).
- Real browser, zero console errors: the matrix renders all 5 system
  roles plus the custom role with correct checked/unchecked state per
  cell, `SYSTEM`-badged columns show no delete control, the custom role's
  column shows one; clicked a live cell (granted `audit:view` to
  `VIEWER`) and confirmed the checkbox rendered checked immediately, then
  reverted it the same way; used the "New Role" form end-to-end (typed
  code/label, checked one permission, submitted) and confirmed the new
  role appeared as a correctly-populated new matrix column with a success
  alert.
- All test roles/users/audit rows created for this verification were
  removed afterward - the 5 original system roles are the only ones left
  in the database.

## Phase 7 — Analytics

55. **Bug found and fixed live: a campaign run never naturally left
    `RUNNING`.** Every run-lifecycle path (start/pause/resume/stop) was
    driven by an explicit operator action - nothing transitioned a run to
    a terminal state once its dispatch simply finished on its own. A
    completed run would sit in `RUNNING` forever. Fixed by making
    `worker-message-events` (a heartbeat stub since Phase 1 - `campaign.
    message-events` has existed and been written to since Phase 5, with
    literally nothing consuming it until now) check, on every terminal
    message outcome, whether the whole run is now done
    (`app.services.dispatch_service.check_and_complete_run`) via a cheap
    single-partition indexed query (`ix_messages_run_status`, already
    existed from Phase 5) rather than a table scan. CAS'd
    (`WHERE status = 'RUNNING'`) so Kafka redelivery of the same check is
    a harmless no-op. Verified live: a real run auto-transitioned to
    `COMPLETED` in under one second of its last message going terminal -
    the first time any campaign run in this project has ever reached
    that status without a manual stop.

56. **The rollup worker pattern**: `check_and_complete_run` publishes to
    `campaign.analytics.events` (provisioned since Phase 1, also unused
    until now) on the `RUNNING -> COMPLETED` transition; `worker-
    analytics` (also a heartbeat stub until this phase) consumes it and
    computes+caches that run's full analytics via `app.analytics.rollup.
    compute_and_store_rollup` into the new `campaign.analytics_rollups`
    table - once, when the run finishes, not recomputed on every
    dashboard page view. `GET /analytics/runs/{id}` serves the cache for
    a terminal run; for a still-`RUNNING` run (or `?refresh=true`) it
    computes fresh, so the same primitives serve both the cached and
    live-preview cases.

57. **Reusable primitives, not one-off reports** - the requirements doc's
    explicit instruction (§32: "Do not hard-code these as one-off
    reports. Build reusable analytics primitives.") shaped the module
    boundaries directly: `app.analytics.core_metrics.compute_core_metrics`
    (one campaign_run_id in, every requirements-doc §31 core metric out -
    audience/unique customers/status counts/success rate/duration/actual
    TPS/zone/channel/demographic breakdown, all set-based SQL, never a
    per-row Python loop) and `app.analytics.engagement.
    compute_chat_engagement`/`compute_provider_engagement` (an arbitrary
    MSISDN list + time window in, not hardcoded to one campaign or
    promotion - any future ad-hoc date-range report can reuse the exact
    same function a campaign rollup uses).

58. **APU/HGU/Engagement Rate implemented against a real, previously
    unused external table** (`chat.chat_history`, 2.08M rows - read
    access granted this phase, see `deploy/scripts/bootstrap_db.sh`),
    using the requirements doc's exact §32 definitions: APU = users who
    interacted at least once, HGU = users with **>5** SMS (strictly
    greater, not ≥ - verified live with a real customer at exactly 5
    messages correctly excluded), Engagement Rate = HGU / APU. The table
    has no per-message timestamp and no MSISDN column - `chat_history.
    session_id` encodes `"{msisdn}-{dd-mm-yyyy}"` (a real, load-bearing
    assumption, not guessed: verified against all 2.08M live rows before
    writing a query around it - 99.99% match the format, and of those
    100% have a canonical `255XXXXXXXXX` MSISDN; the ~0.01% that don't
    are test/synthetic session ids like `"conv_<ts>_<rand>"`, excluded by
    the format regex itself rather than hard-failing, same tolerance
    principle as the Phase 2 import parser). Only `message->>'type' =
    'human'` rows count as "SMS" (the customer's own messages), never the
    bot's replies.

59. **Attribution honestly scoped to what the source database actually
    contains**, not fabricated to match the requirements doc's full
    wishlist (subscriptions / chatbot engagement / doctor calls / IVR
    engagement / product activation):
    - **Subscriptions/product activation**: reuses `campaign.
      customer_subscription_state` (Phase 3). Explicitly documented as
      correlation, not causation - the table has no per-customer
      activation timestamp, only current `is_subscribed` + last sync
      time, so "conversion" here means "currently subscribed among the
      audience," not "activated because of this campaign."
      Deliberately **not** auto-computed into the cached rollup: a
      campaign isn't tied to one "product it promotes" in this schema
      (`product_exclusion_codes` is an exclusion list, not a target), so
      guessing a product_code would misrepresent a parameterized
      primitive as a fixed report. Exposed instead as `GET /analytics/
      runs/{id}/conversion?product_code=X`, the caller's explicit choice.
    - **"Doctor calls"**: no telephony call log exists anywhere in the
      source database (confirmed by searching every schema for a table
      matching `%call%`/`%ivr%`/`%voice%` - zero results). The closest
      real proxy is `provider.provider_appearances`/`provider_impressions`
      (a provider surfaced in search / actually viewed) - used, but
      honestly labeled "provider (doctor discovery) engagement" in both
      the API and the dashboard, never "doctor calls," since that would
      overstate what a marketplace-impression event actually represents.
    - **IVR engagement**: no engagement log exists beyond what `campaign.
      messages`/`message_attempts` already capture (dispatch outcome -
      sent/failed - not whether the customer actually answered/engaged).
      Omitted as a distinct attribution dimension rather than double-
      counting the same dispatch-outcome data under a new name.

60. **Reports & Analytics dashboard** built per the dataviz skill's method
    (loaded before writing any chart code, per its own trigger
    instructions): message status is modeled as a **status** palette
    (reusing this app's existing Badge.tsx success/warning/danger/neutral
    vocabulary as hex, since status is state, not identity - the skill
    explicitly separates the two), not a categorical one - every
    breakdown chart in this dashboard (zone/channel/gender/ARPU-segment ×
    status) colors by status, so no identity-categorical palette was
    needed at all. The skill's own validated default categorical set
    (`references/palette.md`) was checked against this app's brand teal
    first and rejected - `#0f3f43` fails the categorical chroma floor
    (reads as gray at that saturation), confirming teal stays a UI-chrome
    color, not a chart series color. Built a reusable `StackedBarChart`
    component (24px-capped thin bars, 4px rounded data-end only on the
    bar's outward tip, 2px surface gaps between segments, per-segment
    hover tooltip with a lift effect, legend for 2+ series/none for one)
    used for every breakdown. Verified live in a real browser against
    real, *continuously changing* production chat data (not a static
    fixture) - confirmed the hover tooltip, the "Check Conversion" button
    round-tripping to the real API, and the full-page render with zero
    console errors. One byproduct of testing against live data: a
    fixture MSISDN counted at 5/7 messages when the test base was built
    minutes earlier had grown to 7/8/10 by the time the run actually
    dispatched, because real customers were actively chatting in
    production during the test - not a bug, just proof the numbers are
    live rather than cached-stale.

## Post-Phase-7 addendum — Dashboard rate-limit card fix, mobile responsiveness

61. **The Dashboard's "Global rate limit" card was a static stub that never
    got wired up** - it displayed a hardcoded "200" and the literal text
    "Live throughput dashboards ship with Kafka dispatch (Phase 5)," a
    Phase 1 placeholder that outlived the phase it referenced (Phase 5
    shipped the real GCRA limiter - `app.redis.ratelimit` - but nothing
    ever came back to connect this card to it). Confirmed live before
    touching anything: the card never called an API at all.

    Fixed with a real `GET /system/rate-limit-status` endpoint. Rather
    than trying to read a rate *out of* the GCRA limiter's Redis state
    (a TAT float isn't a rate - it's a theoretical-arrival-time, and the
    keys self-expire after 30s idle by design, see `app.redis.
    ratelimit`), it counts real dispatch attempts
    (`campaign.message_attempts.attempted_at`) in the trailing 5 seconds,
    per channel and combined, against the real configured ceilings
    (`channel_configs.tps_allocation` / `settings.global_tps_limit`).
    Checked query performance live first (`EXPLAIN ANALYZE`): 0.4ms,
    partition-pruned to the current month automatically since
    `message_attempts` is RANGE-partitioned by `attempted_at` - no new
    index needed. The dashboard card now polls it every 3s and shows a
    per-channel progress bar, not just the combined number.

    Verified live, not just at idle: dispatched a real 150-message batch
    (mock Kannel, same harness as every dispatch verification this
    session) and polled the endpoint every 300ms *during* dispatch -
    caught it climbing 0 → 2.0 → 2.2 TPS in real time, tracking actual
    send activity. Confirmed it correctly returns to 0/200 at idle
    afterward, not stuck or lagging.

62. **Three real mobile-navigation bugs, all traced to one root cause in
    `NavShell.tsx`.** The mobile drawer rendered `SidebarContent` (which
    internally assumes it owns a `h-full flex flex-col` container, with
    its footer/logout section relying on `flex-1` on the nav list to get
    pushed to the bottom) as a *second* element after a separate,
    sibling close-button row - so the two pieces' heights didn't compose:
    `SidebarContent`'s own `h-full` resolved against the drawer's full
    viewport height *starting from where it began*, overflowing the
    drawer's actual bounds by exactly the close-button row's height, with
    no scroll affordance to reach the excess.
    - **Logo pushed down with an empty gap on top**: the close (X) button
      sat alone in its own row above the logo, instead of sharing the
      logo's row.
    - **No visible Logout in mobile view**: the footer (user info +
      sign-out) was the part pushed past the drawer's visible bounds by
      the overflow above - not hidden by a style rule, just genuinely
      unreachable.
    - **Hamburger menu "not well placed"**: on inspection this meant a
      bare 36×36px icon with no visible boundary and no `sticky`
      positioning - it scrolled out of reach on any page taller than one
      screen (the Roles & Permissions matrix, a long campaign list), and
      at 36px sat under the 44px touch-target guideline.

    Fixed at the root: `SidebarContent` now accepts an optional `onClose`
    prop and renders the close button *inside* its own logo row when
    provided, so the drawer passes it a single child that correctly owns
    100% of the drawer's height as one flex column - no more competing
    siblings, so the footer is always reachable regardless of how many
    nav items exist. The hamburger trigger grew to a 44×44px hit target
    with a visible border (matching the app's `outline` button style) and
    became `sticky top-0`, so it never scrolls away.

    Verified live in a real mobile browser (390×844, iPhone-class
    viewport): before/after screenshots of the closed bar and the open
    drawer: confirmed the logo and close button now share one row with no
    gap, the sign-out footer is visible and reachable at the bottom of
    the drawer, and an actual click on it signs out and redirects to
    `/login` (not just visually present - functionally verified). A
    broader responsiveness sweep followed rather than trusting the nav
    fix alone to mean "responsive": every portal page checked
    (Dashboard, Campaigns incl. the New Campaign form, Roles &
    Permissions' wide matrix, Settings, Reports, Staff, Audit, Imports,
    Bases, DND, Login) at both a 390px mobile width and a 768px tablet
    width reported zero horizontal page overflow
    (`scrollWidth > clientWidth`, checked programmatically, not eyeballed)
    - the widest content (the Roles matrix, the multi-column campaign
      form) already degrades correctly: the matrix scrolls within its own
    card (the existing `Table` component's `overflow-x-auto` wrapper,
    established since Phase 4), and the form collapses to one column via
    its existing `sm:`/`lg:` grid breakpoints - both patterns already
    correct, not something this pass needed to change.

## Known follow-ups

- ~~Phase 6 UI gating was verified for SUPER_ADMIN and VIEWER only, not
  CAMPAIGN_MANAGER/OPERATIONS/ANALYST~~ - **resolved by the Post-Phase-6
  addendum**: the hand-kept static mirror (`frontend/src/lib/permissions.ts`)
  this note was about no longer exists. `useAuth().can()` now reads
  `GET /auth/me`'s server-computed `permissions` list directly, so there is
  no separate frontend copy of the permission map left to drift from the
  backend or verify per-role - the same code path is exercised regardless
  of which role is logged in.
- The IDE's built-in image scanner flags known CVEs (2 critical, 2 high) in
  the `python:3.12-slim` base image used by `Dockerfile.backend` and
  `Dockerfile.worker`. This is expected of any base image at a point in
  time and is exactly what the CI/CD "image scan" pipeline step (already
  in the roadmap, §51 of the original prompt) is meant to catch and gate
  on going forward - not something to chase ad hoc during Phase 1. Revisit
  when CI/CD is wired up: pin a digest, scan with Trivy/Docker Scout, and
  rebuild on a schedule to pick up patched base layers.
- Cosmetic-only SQLAlchemy warning on every INSERT into `events`/
  `messages`/`message_attempts` (composite-PK identity columns, e.g.
  `Event.id`/`Event.created_at`): "Column ... is marked as a member of
  the primary key ... but has no Python-side or server-side default
  generator indicated". Pre-existing since Phase 2, not something Phase 5
  introduced - noticed live in worker logs while verifying dispatch.
  Harmless: the DB-side `GENERATED ALWAYS AS IDENTITY` populates the
  column correctly regardless of what SQLAlchemy's model believes, proven
  by every successful insert throughout every phase. The real fix is
  `autoincrement=True` on those `mapped_column` declarations; low
  priority since it's log noise, not a functional bug.

## Security notes carried forward

- The requirements doc's Appendix A contains real, plaintext operational
  credentials (Postgres superuser password, Kannel gateway password) that
  were **only** used to (a) bootstrap the least-privilege `campaign_app`
  role via `deploy/scripts/bootstrap_db.sh`, and (b) populate a local,
  git-ignored `.env` for this session's verification. They are not present
  in any committed file — `.env.example` has placeholders only, `.env` is
  git-ignored.
- `campaign_app` was verified live to have exactly the intended access:
  full read/write on `campaign.*`, `SELECT`-only on
  `subscription.subscribers` (Phase 1) plus `chat.chat_history` and
  `provider.provider_appearances`/`provider_impressions` (Phase 7, for
  engagement attribution - see decisions.md #58-59), and explicit
  `permission denied` on every other schema tested (e.g.
  `billing.payments`).
- Kannel and Postgres credentials should be rotated before this document or
  the original requirements `.docx` leaves the trusted internal
  environment, per the doc's own security note.

## What was verified live during Phase 2 (not just designed)

- **Full 17,000,000-row synthetic base, real host-to-host flow**: server
  drop path → scan → create-from-drop (SHA256 checksum of a 972MB file) →
  Kafka-driven `worker-ingestion` streaming stage → Odoo-like preview →
  approve → committed INSERT...SELECT into `base_members`. Final counts:
  `total_rows=17,000,000`, `valid_rows=16,898,000`, `invalid_rows=68,001`
  (~0.4%), `duplicate_rows=33,999` (~0.2%) — matching the synthetic
  generator's injected rates almost exactly (arithmetic: 16,898,000 +
  68,001 + 33,999 = 17,000,000 ✓), even zone distribution across all 4
  zones (~4.2M each). `base_versions.member_count = 16,898,000`, exactly
  equal to `valid_rows` — the commit moved precisely the right rows, no
  more, no less.
- **Memory-flat streaming proven directly, not inferred**: `docker stats`
  on `worker-ingestion` during the run stayed at ~96–112MB regardless of
  whether 380K or 3.6M+ rows had been processed - concrete evidence the
  chunked Polars/csv-module pipeline + per-chunk COPY never loads the file
  into memory, independent of file size.
- **Legacy malformed-row bug class reproduced and correctly handled**: a
  fixture reproducing the exact `not_in_base.py` finding (MSISDN+GENDER+AGE
  glued into one quoted CSV field; a truncated final line with an
  unterminated quote) parsed without failing the import - the glued
  field's MSISDN was correctly extracted, the truncated line was
  tolerated. Verified via both a unit test (`tests/test_parsers.py`) and
  live through the real API against the small end-to-end test file.
- **Idempotency and RBAC end-to-end through the real stack**: duplicate
  `(campaign_run_id, ...)`-style checks aren't applicable here, but the
  equivalent import-level idempotency held - duplicate-file upload
  detection via checksum, and the message-level CAS pattern
  (`UPDATE ... WHERE status = 'QUEUED'`) design was reconfirmed sound by
  the same category of concurrency bug this phase found and fixed (below).
  RBAC-gated endpoints correctly required auth/role through nginx→
  backend-api end to end.

### Bugs found and fixed live during Phase 2 (all via real failures, not code review)

17. **nginx upstream DNS caching** (502s after a normal container
    recreate) - see item 13 above; listed here too since it was Phase 2's
    first real-world hit of it.
18. **SQLAlchemy bare timestamp columns silently sending NULL** instead of
    honoring the DB's `DEFAULT now()` - see item 14.
19. **structlog's reserved `event` kwarg collision** crashing the error
    handler itself - see item 15.
20. **Kafka `MAX_POLL_EXCEEDED`**: the default `max.poll.interval.ms`
    (5 min) assumes a fast per-message handler; `worker-ingestion`'s
    handler can legitimately run 15-20+ minutes on a large file with no
    intermediate `poll()` call. The consumer group's liveness watchdog
    evicted the worker mid-processing even though the work itself was
    completing correctly. Fixed by raising `max.poll.interval.ms` to 1h -
    an explicit config choice appropriate for a fundamentally long-running
    consumer, not a universal default. Follow-up noted: this worker
    doesn't yet heartbeat into Redis during long processing, so liveness
    dashboards can't distinguish "still streaming a large file" from
    "wedged" - deferred to the Phase 5 observability pass.
21. **TOCTOU race between two concurrent `commit_import()` invocations for
    the same import** - the most significant bug this session. Root
    cause: `_should_process()` reads `imports.status` in its own
    transaction before calling `commit_import()`; under READ COMMITTED,
    two concurrent invocations (traced to an old worker instance not yet
    torn down overlapping with its just-redeployed replacement, both
    holding the same Kafka message before either committed its offset)
    can both read the same pre-claim status and both proceed, each
    creating its **own** new `base_version` and racing to
    `INSERT...SELECT` ~16.9M rows into it simultaneously. Caught live via
    `pg_stat_activity`: one transaction actively running the bulk INSERT,
    a second genuinely blocked on a row lock (`wait_event_type=Lock,
    wait_event=transactionid`) trying to update the same `imports` row.
    **A status check alone can never fully solve this** - it can't
    distinguish "another live worker has this right now" from "a worker
    died holding this status." The correct fix, already specified in
    Phase 1's architecture doc but never actually implemented until this
    incident forced the issue: the `campaign:lock:import:{id}` Redis
    distributed lock now wraps the entire status-check-then-act critical
    section in `app.workers.ingestion_worker.handle_event` (`SET NX PX`
    acquire, Lua compare-and-delete release - see `app/redis/locks.py`).
    Verified fixed live: after the fix, `pg_stat_activity` showed exactly
    one transaction for the retried commit, and a genuinely duplicate
    `commit_requested` redelivery afterward was correctly and harmlessly
    skipped (`ingestion.skip_stale_event`, `current_status=READY`) rather
    than starting a second commit.
22. Added `POST /imports/{id}/retry-staging` and `POST
    /imports/{id}/retry-commit` as operator recovery levers for the case
    Kafka redelivery can't cover on its own - the triggering event itself
    being lost (e.g. broker storage wiped), not just a worker crash with
    Kafka intact. Matches "operators must be able to recover without SSH"
    for imports, not just campaign execution.

## Phase 3 scoping notes

23. **Subscription sync targets one generic product code, not the richer
    per-product model the schema supports**: `subscription.subscribers` is
    a single flat table (confirmed live: 2,093,596 rows, 100% already in
    canonical `255XXXXXXXXX` form - no normalization needed), not
    per-product. Synced against a default `AFYACALL_SUBSCRIBER` product
    code. `customer_subscription_state` still supports per-product rows
    (per decisions.md item 7); this just isn't populated yet because no
    per-product source tables have been identified. Revisit once
    DOCSUB/CHATBOT-style per-product sources are found.
24. **Subscription sync is synchronous (no Kafka/worker), unlike file
    ingestion**: it's a single set-based SQL statement pair entirely
    inside Postgres (source and target are the same database, different
    schema) - confirmed live to complete in well under a minute even
    across ~1.9M distinct subscribers, so routing it through the
    async Kafka pipeline built for multi-minute file streams would be
    unnecessary complexity. Revisit if the source table's scale changes
    that math.
25. **Eligibility preview returns aggregate counts only, not persisted
    rows**: `campaigns`/`campaign_runs` don't exist until Phase 4, so
    there's no `campaign_run_id` yet to attach `audience_members` rows to.
    `POST /audience/preview` implements the exact same anti-join query
    design as an aggregate `SELECT`; Phase 4 reuses the identical logic
    for the persisted `INSERT...SELECT` version once a run exists.
26. **Testing gap, noted rather than hidden**: Phase 3's new logic
    (`app/audience/eligibility.py`, `app/services/subscription_service.py`,
    the DND branch of `commit_import`) has no automated unit-test coverage
    - it's inherently SQL/DB-dependent logic that would need a real
    Postgres fixture (transactional rollback per test) to test properly in
    isolation, which wasn't built this session. In its place, all of it
    was verified live against the real database with a precisely
    constructed fixture (below) where every count was hand-computed in
    advance and matched exactly - stronger evidence for this specific run
    than a mocked unit test, but not a substitute for regression coverage
    going forward. A `tests/integration/` suite against a real (or
    dockerized) Postgres is a good candidate for a future session.

## What was verified live during Phase 3 (not just designed)

- **DND import reusing the Phase 2 pipeline end to end**: a headerless,
  single-column DND file was correctly auto-detected as headerless
  (`sniff_has_header`), staged through the identical parser/normalizer/COPY
  path as a BASE import, and committed via `commit_import`'s DND branch
  into a new `dnd_lists` (version auto-incremented) + `dnd_records` -
  proving the "same pipeline, different commit target" design actually
  works, not just BASE.
- **Subscriber sync against the real, live `subscription.subscribers`**:
  `1,901,169` distinct MSISDNs upserted (the ~192K gap from the table's
  2,093,596 total rows is real customers with multiple subscription
  records, not a bug). The companion unsubscribe-detection query found 3
  rows to flip to `is_subscribed=false` on this very first sync - initially
  surprising (there should be nothing pre-existing to flip on a first run),
  but consistent with genuine concurrent writes to the live production
  `subscription.subscribers` table during the ~20s the sync took: each SQL
  statement in a transaction gets its own READ COMMITTED snapshot, so a
  real subscriber row changing between the INSERT's snapshot and the
  UPDATE's snapshot a few seconds later is exactly what would produce this.
  Not a bug - a live demonstration of why periodic re-sync (not a
  one-time seed) is the right model.
- **Eligibility query verified for exact correctness, not just "it runs"**:
  a 10-row test base was constructed with 5 MSISDNs sampled from the real,
  live `subscription.subscribers` table, 3 different MSISDNs committed to
  a test DND list (deliberately non-overlapping with the 5 subscriber
  ones), and 2 genuinely clean MSISDNs. Every count was hand-computed
  before running: expected `total=10, dnd_excluded=3, subscriber_excluded=5,
  cooldown_excluded=0, final_eligible=2`. The live query returned exactly
  that, including the correct zone breakdown for the 2 surviving eligible
  customers.
- **Eligibility query performance at real 17M-row scale**: run against the
  full committed 16,898,000-row base from the Phase 2 test, the same
  aggregate query (candidate count + 3-way anti-join + zone breakdown)
  completed in **18.5 seconds** - fast enough for an interactive preview,
  not just a batch job. `dnd_excluded=0` (no overlap with the tiny test
  DND list, as expected for a synthetic base) and `subscriber_excluded=1`
  (one coincidental MSISDN collision between the synthetic generator's
  output and a real subscriber, statistically unsurprising at this scale)
  - both sane results, not errors.
- **A build-pipeline gap caught before it caused confusion**: `migrate` is
  built from the same Dockerfile as `backend-api` but is a *separate*
  image under Compose - rebuilding `backend-api` does not rebuild
  `migrate`. Ran into this directly: `migrate` failed with `Can't locate
  revision identified by '0004'` because its stale image didn't have the
  new migration files, even though the database's `alembic_version` (from
  applying migrations via the local dev venv) already expected it. Fixed
  by rebuilding `migrate` explicitly. Worth remembering for future
  phases: any migration-adding change needs `docker compose build migrate`
  alongside whichever service actually uses the new code.

## What was verified live during Phase 1 (not just designed)

- `campaign_app` role + `campaign` schema created via
  `deploy/scripts/bootstrap_db.sh` against the real production Postgres
  (`192.168.1.11`, PostgreSQL 12.22) — additive, reversible, least-privilege.
- Migration `0001` applied cleanly: 24 logical tables, 192 total relations
  (partitions included), e.g. `messages` confirmed with exactly 32 hash
  partitions.
- Constraint/partitioning smoke test (transaction rolled back, no data
  left behind): valid MSISDN accepted; duplicate `(campaign_run_id,
  customer_msisdn, channel)` rejected; local-format and 13-digit MSISDNs
  rejected; cross-partition FK `message_attempts → messages(campaign_run_id,
  id)` works; the dispatcher's idempotent CAS pattern (`UPDATE ... WHERE
  status='QUEUED'`) correctly no-ops (0 rows affected) on a simulated
  duplicate Kafka delivery; partial unique index enforcing one
  `is_current` `base_version` per base works.
- FastAPI app boots, `/api/v1/health` returns 200, `/api/v1/ready` reports
  real dependency status (correctly reported `degraded` when a dependency
  was genuinely unavailable in the trimmed local venv, rather than a false
  green check), OpenAPI docs exposed 27 routes, RBAC-gated endpoints
  correctly 401 without a token.
- This Docker host sits on the same LAN as both target hosts
  (`192.168.1.200/24`), confirmed reachable to Postgres (`192.168.1.11:5432`)
  and Kannel (`192.168.1.10:6016`) via normal bridge-network egress.
- Full `docker compose` stack build/up — see the session record for final
  verification of `/health`, `/ready` through nginx, OpenAPI docs, TLS via
  the real cert, and Kafka topic bootstrap.
