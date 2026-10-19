from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.core.config import get_settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_uri)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="campaign",
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _assert_not_unversioned_schema(connection) -> None:
    """Fail fast, with an actionable message, when campaign.* already has
    tables but no recorded Alembic revision - e.g. a schema-only pg_dump
    restore, which copies every table but leaves alembic_version empty.
    Without this, 0001 re-runs and dies on a bare "relation already
    exists", and the seed rows migrations insert (0007's roles) are
    silently missing too."""
    tables = connection.execute(
        text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'campaign' AND table_name <> 'alembic_version'"
        )
    ).scalar()
    if not tables:
        return
    has_version_table = connection.execute(text("SELECT to_regclass('campaign.alembic_version')")).scalar()
    if has_version_table and connection.execute(text("SELECT count(*) FROM campaign.alembic_version")).scalar():
        return
    raise RuntimeError(
        f"campaign schema has {tables} tables but no Alembic revision recorded in "
        "campaign.alembic_version. Refusing to re-run migrations over it. Set up new "
        "environments by running migrations against an EMPTY campaign schema, never by "
        "restoring a schema-only dump. If the schema genuinely matches a revision, stamp "
        "it (`alembic -x allow_unversioned=1 stamp <rev>`) and re-insert any seed rows "
        "that revision's migrations add (e.g. 0007's roles) - see README 'New environments'."
    )


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if context.get_x_argument(as_dictionary=True).get("allow_unversioned") != "1":
            _assert_not_unversioned_schema(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema="campaign",
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
