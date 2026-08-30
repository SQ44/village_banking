from typing import Generator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, echo=False)

def _sqlite_columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info('{table}')")).fetchall()
    return {row[1] for row in rows}


def _sqlite_table_exists(conn, table: str) -> bool:
    row = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name LIMIT 1"),
        {"name": table},
    ).fetchone()
    return row is not None


def _migrate_sqlite() -> None:
    """Best-effort SQLite migrations for legacy schemas (no Alembic yet)."""
    with engine.begin() as conn:
        if _sqlite_table_exists(conn, "account"):
            cols = _sqlite_columns(conn, "account")
            if "group_id" not in cols:
                conn.execute(text("ALTER TABLE account ADD COLUMN group_id INTEGER"))
            if "user_id" not in cols:
                conn.execute(text("ALTER TABLE account ADD COLUMN user_id INTEGER"))
            if "last_withdrawal_at" not in cols:
                conn.execute(text("ALTER TABLE account ADD COLUMN last_withdrawal_at DATETIME"))

        # Group constitution / settings migrations.
        if _sqlite_table_exists(conn, "groupsettings"):
            cols = _sqlite_columns(conn, "groupsettings")
            if "liquidity_max_outstanding_percent" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE groupsettings ADD COLUMN liquidity_max_outstanding_percent FLOAT NOT NULL DEFAULT 80"
                    )
                )
            if "min_term_months" not in cols:
                conn.execute(text("ALTER TABLE groupsettings ADD COLUMN min_term_months INTEGER NOT NULL DEFAULT 1"))
            if "max_term_months" not in cols:
                conn.execute(text("ALTER TABLE groupsettings ADD COLUMN max_term_months INTEGER NOT NULL DEFAULT 12"))
            if "max_active_loans_per_member" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE groupsettings ADD COLUMN max_active_loans_per_member INTEGER NOT NULL DEFAULT 1"
                    )
                )
            if "cooldown_days_after_settlement" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE groupsettings ADD COLUMN cooldown_days_after_settlement INTEGER NOT NULL DEFAULT 0"
                    )
                )
            if "constitution_locked_at" not in cols:
                conn.execute(text("ALTER TABLE groupsettings ADD COLUMN constitution_locked_at DATETIME"))

        # Lipila payment linkage on existing ledgers.
        if _sqlite_table_exists(conn, "transaction"):
            cols = _sqlite_columns(conn, "transaction")
            for column, ddl in (
                ("provider", "VARCHAR"),
                ("provider_reference", "VARCHAR"),
                ("provider_channel", "VARCHAR"),
                ("provider_status", "VARCHAR"),
                ("provider_identifier", "VARCHAR"),
                ("last_provider_sync_at", "DATETIME"),
            ):
                if column not in cols:
                    conn.execute(text(f'ALTER TABLE "transaction" ADD COLUMN {column} {ddl}'))
            # SQLite cannot add a UNIQUE column in place, so the constraint the
            # model declares is created separately for pre-existing databases.
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_transaction_provider_reference "
                    'ON "transaction" (provider_reference)'
                )
            )
            if "provider_fee" not in cols:
                conn.execute(
                    text('ALTER TABLE "transaction" ADD COLUMN provider_fee NUMERIC(12, 2) NOT NULL DEFAULT 0')
                )

        # The idempotency table is useless without its unique index — that index
        # is the claim that stops a retry starting a second payment — so it is
        # asserted here as well as declared on the model, for the same reason as
        # the one above: SQLite will not add a UNIQUE column in place.
        if _sqlite_table_exists(conn, "idempotencyrecord"):
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_idempotencyrecord_scope "
                    "ON idempotencyrecord (scope)"
                )
            )


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    if settings.database_url.startswith("sqlite"):
        _migrate_sqlite()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
