from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "AfyaCall Campaign Engine"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    # --- Postgres (existing host instance; NEVER a second database) ---
    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_pool_size: int = 10
    postgres_max_overflow: int = 20

    @property
    def sqlalchemy_database_uri(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # --- Kafka ---
    kafka_bootstrap_servers: str = "kafka:9092"

    # --- Kannel (downstream gateway; never called directly from the API) ---
    kannel_host: str = "192.168.1.10"
    kannel_ports: str = "6016,6017,6018"
    kannel_username: str = ""
    kannel_password: str = ""

    @property
    def kannel_port_list(self) -> list[int]:
        return [int(p) for p in self.kannel_ports.split(",") if p]

    # --- Global rate limit (hard constraint: SMS + IVR + Doctor <= this, combined) ---
    global_tps_limit: int = 200
    sms_tps_allocation: int = 140
    ivr_tps_allocation: int = 40
    doctor_tps_allocation: int = 20

    # --- Auth ---
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # --- Server-side import drop path (operator-controlled, manual trigger only) ---
    server_drop_path: str = "/data/campaign/incoming"

    # --- GUI-upload staging area (separate namespace from the drop path) ---
    import_storage_path: str = "/var/lib/campaign-engine/imports/uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()
