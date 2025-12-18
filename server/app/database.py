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
        if not _sqlite_table_exists(conn, "account"):
            return
        cols = _sqlite_columns(conn, "account")
        if "group_id" not in cols:
            conn.execute(text("ALTER TABLE account ADD COLUMN group_id INTEGER"))
        if "user_id" not in cols:
            conn.execute(text("ALTER TABLE account ADD COLUMN user_id INTEGER"))
        if "last_withdrawal_at" not in cols:
            conn.execute(text("ALTER TABLE account ADD COLUMN last_withdrawal_at DATETIME"))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    if settings.database_url.startswith("sqlite"):
        _migrate_sqlite()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
