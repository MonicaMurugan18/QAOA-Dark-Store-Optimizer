"""Application settings, loaded from environment variables / .env.

Nothing here contains a credential. DATABASE_URL must be supplied by the
environment; see .env.example.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---------------------------------------------------------------- app
    app_name: str = "QAOA Dark-Store Optimization API"
    app_version: str = "0.1.0"
    debug: bool = False

    # ----------------------------------------------------------- database
    # No default password anywhere. If DATABASE_URL is unset the app falls back
    # to a local SQLite file so the API and the test suite can run without a
    # PostgreSQL server. PostgreSQL is the intended production target.
    database_url: str = Field(
        default="sqlite:///./darkstore.db",
        description="SQLAlchemy URL, e.g. postgresql+psycopg2://user:pass@host:5432/db",
    )
    sql_echo: bool = False

    # ------------------------------------------------------------------
    # SQLITE MUST NEVER ACTIVATE BY ACCIDENT.
    #
    # The default above exists so the test suite can run without database
    # credentials, but in any other context a silent fall back to a local file
    # would hide a broken PostgreSQL connection and quietly serve empty data.
    # So a SQLite URL is REFUSED at startup unless this flag is explicitly set.
    # If PostgreSQL is unreachable the app fails loudly instead of switching.
    # ------------------------------------------------------------------
    allow_sqlite: bool = Field(
        default=False,
        description="Set true ONLY for local tests. Required before any "
        "sqlite:// DATABASE_URL is accepted.",
    )

    # Browser origins allowed to call this API. Explicit list, not "*".
    cors_origins: str = Field(
        default=(
            "http://localhost:5173,http://127.0.0.1:5173,"
            "http://localhost:5174,http://127.0.0.1:5174,"
            "http://localhost:5177,http://127.0.0.1:5177"
        ),
        description="Comma-separated allowed browser origins for the frontend.",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ------------------------------------------------- optimization model
    # Reward per rupee of demand value actually served. This is the gross margin
    # a served order earns; it is what makes serving demand worth paying for.
    # Quick commerce runs thin: 15-25% is the realistic band.
    gross_margin: float = 0.18

    # Rider cost. Delivery cost for one store-area link is
    #   rider_cost_per_min * delivery_time_min * number_of_orders
    rider_cost_per_min: float = 3.0
    avg_items_per_order: float = 5.0

    # Default service promise (minutes) when an area does not specify its own.
    default_delivery_time_limit: float = 15.0

    # ------------------------------------------------------ solver limits
    # Guard rails. A QAOA statevector simulation costs 2**n complex amplitudes,
    # so an unbounded request would exhaust memory. Reject rather than crash.
    qaoa_max_qubits: int = 20
    qaoa_default_reps: int = 3
    qaoa_default_maxiter: int = 200
    qaoa_default_shots: int = 2048
    classical_time_limit_sec: int = 60

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def assert_database_allowed(self) -> None:
        """Refuse to start on SQLite unless it was explicitly opted into."""
        if self.is_sqlite and not self.allow_sqlite:
            raise RuntimeError(
                "DATABASE_URL points at SQLite but ALLOW_SQLITE is not set. "
                "This project runs on Supabase PostgreSQL; falling back to a "
                "local file would hide a broken connection and serve empty "
                "data. Set a postgresql:// DATABASE_URL in backend/.env, or "
                "set ALLOW_SQLITE=true if you really intend a local test run."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
