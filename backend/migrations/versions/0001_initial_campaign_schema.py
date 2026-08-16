"""Initial campaign schema: full table set, partitioning, constraints.

Creates the entire `campaign` schema table set in one revision rather than
building it up incrementally, since the ERD was fully specified up front
during architecture design (see /home/derrick/AfyaForge/afyacall-campaign-engine/docs/architecture.md).
Post-launch schema changes should be normal incremental Alembic revisions.

Written as raw SQL (op.execute) rather than SQLAlchemy's op.create_table/
op.create_index helpers because this schema relies heavily on PostgreSQL
features those helpers don't model well: declarative HASH/RANGE partitioning,
partial indexes, array containment checks, and composite-key foreign keys
into partitioned tables. The app.models.* SQLAlchemy models are the ORM-facing
mirror of this exact DDL and must be kept in sync by hand for this revision.

Assumes the `campaign` schema and `campaign_app` role already exist, created
by deploy/scripts/bootstrap_db.sh (a one-time superuser bootstrap step run
outside of Alembic, since role/schema/cross-schema-grant creation is an
infrequent administrative action, not a versioned application migration).

Revision ID: 0001
Revises:
Create Date: 2026-08-21
"""

from calendar import monthrange
from datetime import date, timedelta
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "campaign"
HASH_PARTITIONS = 32

# Pre-created partition windows for time-RANGE-partitioned tables. A real
# deployment needs a periodic ops job (documented in docs/architecture.md
# "Operational runbooks") to create partitions further out before this
# window runs out; a DEFAULT partition on every RANGE-partitioned table
# catches anything that falls outside it in the meantime so inserts never
# hard-fail.
MONTHLY_WINDOW_START = date(2026, 1, 1)
MONTHLY_WINDOW_MONTHS = 24  # covers 2026-01 .. 2027-12
WEEKLY_WINDOW_START = date(2026, 1, 5)  # first Monday of the window
WEEKLY_WINDOW_WEEKS = 26  # ~6 months


def _next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _month_ranges(start: date, count: int) -> list[tuple[date, date]]:
    ranges = []
    cur = date(start.year, start.month, 1)
    for _ in range(count):
        nxt = _next_month(cur)
        ranges.append((cur, nxt))
        cur = nxt
    return ranges


def _week_ranges(start: date, count: int) -> list[tuple[date, date]]:
    ranges = []
    cur = start
    for _ in range(count):
        nxt = cur + timedelta(days=7)
        ranges.append((cur, nxt))
        cur = nxt
    return ranges


def _create_hash_partitions(parent: str) -> None:
    for i in range(HASH_PARTITIONS):
        op.execute(
            f"CREATE TABLE {SCHEMA}.{parent}_p{i} "
            f"PARTITION OF {SCHEMA}.{parent} "
            f"FOR VALUES WITH (MODULUS {HASH_PARTITIONS}, REMAINDER {i});"
        )


def _create_range_partitions(parent: str, ranges: list[tuple[date, date]], label_fmt: str) -> None:
    for start, end in ranges:
        label = start.strftime(label_fmt)
        op.execute(
            f"CREATE TABLE {SCHEMA}.{parent}_{label} "
            f"PARTITION OF {SCHEMA}.{parent} "
            f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}');"
        )
    op.execute(f"CREATE TABLE {SCHEMA}.{parent}_default PARTITION OF {SCHEMA}.{parent} DEFAULT;")


MSISDN_CHECK = "customer_msisdn ~ '^255[0-9]{9}$'"


def upgrade() -> None:
    # ---------------------------------------------------------------
    # Reference / config
    # ---------------------------------------------------------------
    op.execute(f"""
        CREATE TABLE {SCHEMA}.zone_configs (
            id BIGSERIAL PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL,
            parent_zone_id BIGINT REFERENCES {SCHEMA}.zone_configs(id),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    op.execute(f"""
        CREATE TABLE {SCHEMA}.channel_configs (
            channel TEXT PRIMARY KEY CHECK (channel IN ('SMS','IVR','DOCTOR')),
            sender_id TEXT NOT NULL,
            tps_allocation INTEGER NOT NULL CHECK (tps_allocation > 0),
            default_retry_policy JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    op.execute(f"""
        CREATE TABLE {SCHEMA}.customer_products (
            code TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true
        );
    """)

    op.execute(f"""
        CREATE TABLE {SCHEMA}.users (
            id BIGSERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN
                ('SUPER_ADMIN','CAMPAIGN_MANAGER','OPERATIONS','ANALYST','VIEWER')),
            full_name TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    op.execute(f"""
        CREATE TABLE {SCHEMA}.import_profiles (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            delimiter TEXT NOT NULL DEFAULT ',',
            encoding TEXT NOT NULL DEFAULT 'utf-8',
            column_mapping JSONB NOT NULL,
            product_scope TEXT,
            created_by BIGINT REFERENCES {SCHEMA}.users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    # ---------------------------------------------------------------
    # Import pipeline
    # ---------------------------------------------------------------
    op.execute(f"""
        CREATE TABLE {SCHEMA}.imports (
            id BIGSERIAL PRIMARY KEY,
            import_profile_id BIGINT REFERENCES {SCHEMA}.import_profiles(id),
            source_type TEXT NOT NULL CHECK (source_type IN ('UPLOAD','SERVER_DROP')),
            source_path TEXT NOT NULL,
            original_filename TEXT,
            file_hash TEXT,
            status TEXT NOT NULL DEFAULT 'IMPORT_CREATED' CHECK (status IN (
                'DETECTED','UPLOADED','IMPORT_CREATED','STAGED','VALIDATING',
                'PREVIEW_READY','APPROVED','COMMITTING','READY','REJECTED','FAILED'
            )),
            total_rows BIGINT,
            valid_rows BIGINT,
            invalid_rows BIGINT,
            duplicate_rows BIGINT,
            dnd_impact_count BIGINT,
            zone_distribution JSONB,
            sample_rows JSONB,
            error_summary JSONB,
            approved_by BIGINT REFERENCES {SCHEMA}.users(id),
            approved_at TIMESTAMPTZ,
            committed_base_version_id BIGINT,
            created_by BIGINT REFERENCES {SCHEMA}.users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute(
        f"CREATE UNIQUE INDEX uq_imports_file_hash ON {SCHEMA}.imports (file_hash) "
        f"WHERE file_hash IS NOT NULL;"
    )
    op.execute(f"CREATE INDEX ix_imports_status ON {SCHEMA}.imports (status);")

    op.execute(f"""
        CREATE TABLE {SCHEMA}.import_staging_rows (
            id BIGSERIAL PRIMARY KEY,
            import_id BIGINT NOT NULL REFERENCES {SCHEMA}.imports(id) ON DELETE CASCADE,
            row_number BIGINT NOT NULL,
            raw JSONB NOT NULL,
            normalized_msisdn VARCHAR(12),
            validation_status TEXT NOT NULL CHECK (validation_status IN ('VALID','INVALID','DUPLICATE')),
            rejection_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute(
        f"CREATE INDEX ix_import_staging_rows_import_status "
        f"ON {SCHEMA}.import_staging_rows (import_id, validation_status);"
    )

    # ---------------------------------------------------------------
    # Base data
    # ---------------------------------------------------------------
    op.execute(f"""
        CREATE TABLE {SCHEMA}.bases (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    op.execute(f"""
        CREATE TABLE {SCHEMA}.base_versions (
            id BIGSERIAL PRIMARY KEY,
            base_id BIGINT NOT NULL REFERENCES {SCHEMA}.bases(id),
            source_import_id BIGINT REFERENCES {SCHEMA}.imports(id),
            member_count BIGINT,
            is_current BOOLEAN NOT NULL DEFAULT false,
            committed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute(
        f"CREATE UNIQUE INDEX uq_base_versions_current_per_base "
        f"ON {SCHEMA}.base_versions (base_id) WHERE is_current;"
    )

    op.execute(
        f"ALTER TABLE {SCHEMA}.imports ADD CONSTRAINT fk_imports_committed_base_version "
        f"FOREIGN KEY (committed_base_version_id) REFERENCES {SCHEMA}.base_versions(id);"
    )

    op.execute(f"""
        CREATE TABLE {SCHEMA}.base_members (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            base_version_id BIGINT NOT NULL REFERENCES {SCHEMA}.base_versions(id),
            customer_msisdn VARCHAR(12) NOT NULL CHECK ({MSISDN_CHECK}),
            territory TEXT,
            commercial_region TEXT,
            gender TEXT,
            age INTEGER,
            arpu_segment TEXT,
            source_snapshot JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, base_version_id),
            UNIQUE (base_version_id, customer_msisdn)
        ) PARTITION BY HASH (base_version_id);
    """)
    _create_hash_partitions("base_members")
    op.execute(
        f"CREATE INDEX ix_base_members_version_territory "
        f"ON {SCHEMA}.base_members (base_version_id, territory);"
    )

    # ---------------------------------------------------------------
    # DND
    # ---------------------------------------------------------------
    op.execute(f"""
        CREATE TABLE {SCHEMA}.dnd_lists (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            source_import_id BIGINT REFERENCES {SCHEMA}.imports(id),
            version INTEGER NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            effective_from TIMESTAMPTZ,
            effective_to TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (name, version)
        );
    """)

    op.execute(f"""
        CREATE TABLE {SCHEMA}.dnd_records (
            id BIGSERIAL PRIMARY KEY,
            dnd_list_id BIGINT NOT NULL REFERENCES {SCHEMA}.dnd_lists(id) ON DELETE CASCADE,
            customer_msisdn VARCHAR(12) NOT NULL CHECK ({MSISDN_CHECK}),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (dnd_list_id, customer_msisdn)
        );
    """)
    op.execute(
        f"CREATE INDEX ix_dnd_records_msisdn_active ON {SCHEMA}.dnd_records (customer_msisdn) "
        f"WHERE is_active;"
    )

    # ---------------------------------------------------------------
    # Subscription state (per-product projection)
    # ---------------------------------------------------------------
    op.execute(f"""
        CREATE TABLE {SCHEMA}.customer_subscription_state (
            customer_msisdn VARCHAR(12) NOT NULL CHECK ({MSISDN_CHECK}),
            product_code TEXT NOT NULL REFERENCES {SCHEMA}.customer_products(code),
            is_subscribed BOOLEAN NOT NULL DEFAULT true,
            source TEXT NOT NULL CHECK (source IN ('BATCH_SYNC','KAFKA_EVENT')),
            synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (customer_msisdn, product_code)
        );
    """)
    op.execute(
        f"CREATE INDEX ix_customer_subscription_state_subscribed "
        f"ON {SCHEMA}.customer_subscription_state (customer_msisdn) WHERE is_subscribed;"
    )

    # ---------------------------------------------------------------
    # Campaigns / rotation
    # ---------------------------------------------------------------
    op.execute(f"""
        CREATE TABLE {SCHEMA}.campaigns (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            channels TEXT[] NOT NULL DEFAULT '{{}}'
                CHECK (channels <@ ARRAY['SMS','IVR','DOCTOR']::text[]),
            base_id BIGINT NOT NULL REFERENCES {SCHEMA}.bases(id),
            product_exclusion_codes TEXT[] NOT NULL DEFAULT '{{}}',
            dnd_list_id BIGINT REFERENCES {SCHEMA}.dnd_lists(id),
            cooldown_days INTEGER NOT NULL DEFAULT 7,
            cooldown_category TEXT,
            zone_quota_mode TEXT NOT NULL DEFAULT 'PERCENT' CHECK (zone_quota_mode IN ('PERCENT','ABSOLUTE')),
            daily_target BIGINT,
            status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
                'DRAFT','CONFIGURED','AUDIENCE_GENERATING','READY','SCHEDULED',
                'RUNNING','PAUSED','COMPLETED','CANCELLED','FAILED'
            )),
            owner_id BIGINT REFERENCES {SCHEMA}.users(id),
            message_template TEXT,
            execution_window JSONB,
            priority INTEGER NOT NULL DEFAULT 100,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute(f"CREATE INDEX ix_campaigns_status ON {SCHEMA}.campaigns (status);")

    op.execute(f"""
        CREATE TABLE {SCHEMA}.campaign_runs (
            id BIGSERIAL PRIMARY KEY,
            campaign_id BIGINT NOT NULL REFERENCES {SCHEMA}.campaigns(id),
            run_date DATE NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN (
                'PENDING','AUDIENCE_GENERATING','READY','SCHEDULED','RUNNING',
                'PAUSED','COMPLETED','CANCELLED','FAILED'
            )),
            audience_snapshot_id BIGINT,
            scheduled_at TIMESTAMPTZ,
            started_at TIMESTAMPTZ,
            paused_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            stats JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (campaign_id, run_date)
        );
    """)
    op.execute(f"CREATE INDEX ix_campaign_runs_status ON {SCHEMA}.campaign_runs (status);")

    op.execute(f"""
        CREATE TABLE {SCHEMA}.schedules (
            id BIGSERIAL PRIMARY KEY,
            campaign_id BIGINT NOT NULL REFERENCES {SCHEMA}.campaigns(id),
            schedule_type TEXT NOT NULL CHECK (schedule_type IN
                ('IMMEDIATE','ONE_TIME','DAILY_ROTATION','RECURRING')),
            cron_expr TEXT,
            run_at TIMESTAMPTZ,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    op.execute(f"""
        CREATE TABLE {SCHEMA}.rotation_state (
            id BIGSERIAL PRIMARY KEY,
            base_id BIGINT NOT NULL REFERENCES {SCHEMA}.bases(id),
            zone TEXT NOT NULL,
            last_offset BIGINT NOT NULL DEFAULT 0,
            cycle_number INTEGER NOT NULL DEFAULT 1,
            total_eligible_at_cycle_start BIGINT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (base_id, zone)
        );
    """)

    op.execute(f"""
        CREATE TABLE {SCHEMA}.cooldown_state (
            customer_msisdn VARCHAR(12) NOT NULL CHECK ({MSISDN_CHECK}),
            campaign_category TEXT NOT NULL,
            cooldown_until TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (customer_msisdn, campaign_category)
        );
    """)
    op.execute(
        f"CREATE INDEX ix_cooldown_state_until ON {SCHEMA}.cooldown_state (cooldown_until);"
    )

    # ---------------------------------------------------------------
    # Audience snapshot
    # ---------------------------------------------------------------
    op.execute(f"""
        CREATE TABLE {SCHEMA}.audience_snapshots (
            id BIGSERIAL PRIMARY KEY,
            campaign_run_id BIGINT NOT NULL UNIQUE REFERENCES {SCHEMA}.campaign_runs(id),
            base_version_id BIGINT REFERENCES {SCHEMA}.base_versions(id),
            dnd_list_id BIGINT REFERENCES {SCHEMA}.dnd_lists(id),
            generated_at TIMESTAMPTZ,
            total_candidates BIGINT,
            total_eligible BIGINT,
            exclusion_breakdown JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    op.execute(
        f"ALTER TABLE {SCHEMA}.campaign_runs ADD CONSTRAINT fk_campaign_runs_audience_snapshot "
        f"FOREIGN KEY (audience_snapshot_id) REFERENCES {SCHEMA}.audience_snapshots(id);"
    )

    op.execute(f"""
        CREATE TABLE {SCHEMA}.audience_members (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            campaign_run_id BIGINT NOT NULL REFERENCES {SCHEMA}.campaign_runs(id),
            customer_msisdn VARCHAR(12) NOT NULL CHECK ({MSISDN_CHECK}),
            zone TEXT,
            eligible BOOLEAN NOT NULL,
            exclusion_reason TEXT CHECK (
                exclusion_reason IS NULL OR
                exclusion_reason IN ('DND','ALREADY_SUBSCRIBED','COOLDOWN','INVALID')
            ),
            source_snapshot JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, campaign_run_id),
            UNIQUE (campaign_run_id, customer_msisdn)
        ) PARTITION BY HASH (campaign_run_id);
    """)
    _create_hash_partitions("audience_members")
    op.execute(
        f"CREATE INDEX ix_audience_members_run_zone "
        f"ON {SCHEMA}.audience_members (campaign_run_id, zone);"
    )
    op.execute(
        f"CREATE INDEX ix_audience_members_run_eligible "
        f"ON {SCHEMA}.audience_members (campaign_run_id, eligible);"
    )

    # ---------------------------------------------------------------
    # Messages (write-heaviest tables)
    # ---------------------------------------------------------------
    op.execute(f"""
        CREATE TABLE {SCHEMA}.messages (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            campaign_run_id BIGINT NOT NULL REFERENCES {SCHEMA}.campaign_runs(id),
            customer_msisdn VARCHAR(12) NOT NULL CHECK ({MSISDN_CHECK}),
            channel TEXT NOT NULL CHECK (channel IN ('SMS','IVR','DOCTOR')),
            status TEXT NOT NULL DEFAULT 'CREATED' CHECK (status IN (
                'CREATED','QUEUED','SUBMITTING','SENT','FAILED','RETRYING',
                'DEAD','FAILED_UNCONFIRMED','CANCELLED'
            )),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TIMESTAMPTZ,
            message_body TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, campaign_run_id),
            UNIQUE (campaign_run_id, customer_msisdn, channel)
        ) PARTITION BY HASH (campaign_run_id);
    """)
    _create_hash_partitions("messages")
    op.execute(
        f"CREATE INDEX ix_messages_retrying_due ON {SCHEMA}.messages (status, next_attempt_at) "
        f"WHERE status = 'RETRYING';"
    )
    op.execute(f"CREATE INDEX ix_messages_run_status ON {SCHEMA}.messages (campaign_run_id, status);")

    op.execute(f"""
        CREATE TABLE {SCHEMA}.message_attempts (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            campaign_run_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            attempt_number INTEGER NOT NULL,
            kannel_port INTEGER,
            http_status INTEGER,
            kannel_response_body TEXT,
            outcome TEXT CHECK (outcome IS NULL OR outcome IN ('SENT','FAILED','AMBIGUOUS')),
            PRIMARY KEY (id, attempted_at),
            UNIQUE (message_id, attempt_number, attempted_at),
            FOREIGN KEY (campaign_run_id, message_id)
                REFERENCES {SCHEMA}.messages (campaign_run_id, id)
        ) PARTITION BY RANGE (attempted_at);
    """)
    _create_range_partitions(
        "message_attempts", _month_ranges(MONTHLY_WINDOW_START, MONTHLY_WINDOW_MONTHS), "%Y%m"
    )
    op.execute(
        f"CREATE INDEX ix_message_attempts_message ON {SCHEMA}.message_attempts (message_id);"
    )

    # ---------------------------------------------------------------
    # Events (transactional outbox) and audit
    # ---------------------------------------------------------------
    op.execute(f"""
        CREATE TABLE {SCHEMA}.events (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload JSONB NOT NULL,
            kafka_topic TEXT NOT NULL,
            kafka_key TEXT NOT NULL,
            published_at TIMESTAMPTZ,
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """)
    _create_range_partitions(
        "events", _week_ranges(WEEKLY_WINDOW_START, WEEKLY_WINDOW_WEEKS), "%Y%m%d"
    )
    op.execute(
        f"CREATE INDEX ix_events_unpublished ON {SCHEMA}.events (published_at) "
        f"WHERE published_at IS NULL;"
    )
    op.execute(
        f"CREATE INDEX ix_events_aggregate ON {SCHEMA}.events (aggregate_type, aggregate_id);"
    )

    op.execute(f"""
        CREATE TABLE {SCHEMA}.audit_logs (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            actor_id BIGINT REFERENCES {SCHEMA}.users(id),
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            old_value JSONB,
            new_value JSONB,
            reason TEXT,
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """)
    _create_range_partitions(
        "audit_logs", _month_ranges(MONTHLY_WINDOW_START, MONTHLY_WINDOW_MONTHS), "%Y%m"
    )
    op.execute(
        f"CREATE INDEX ix_audit_logs_entity ON {SCHEMA}.audit_logs (entity_type, entity_id);"
    )
    op.execute(
        f"CREATE INDEX ix_audit_logs_actor_time ON {SCHEMA}.audit_logs (actor_id, created_at);"
    )


def downgrade() -> None:
    # Reverse dependency order. Partitions drop automatically with their parent.
    for table in [
        "audit_logs",
        "events",
        "message_attempts",
        "messages",
        "audience_members",
        "audience_snapshots",
        "cooldown_state",
        "rotation_state",
        "schedules",
        "campaign_runs",
        "campaigns",
        "customer_subscription_state",
        "dnd_records",
        "dnd_lists",
        "base_members",
        "base_versions",
        "bases",
        "import_staging_rows",
        "imports",
        "import_profiles",
        "users",
        "customer_products",
        "channel_configs",
        "zone_configs",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.{table} CASCADE;")
