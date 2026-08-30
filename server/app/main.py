import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import init_db
from .auth import ensure_default_admin
from .routers import (
    accounts,
    auth_router,
    dashboard,
    groups,
    interest_router,
    loans,
    me,
    operations,
    products,
    transactions,
    webhooks,
)
from .tasks import schedule_jobs

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title="Village Banking Platform",
    description="Community banking ledger with Lipila payments",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    ensure_default_admin()
    backfill_journal()
    schedule_jobs()


def backfill_journal() -> None:
    """Bring any unbooked history into the journal.

    A database that predates double-entry has balances with no entries behind
    them, which would make the control total read as a discrepancy on day one.
    This books them once; afterwards it finds nothing and costs a single query.
    """
    from sqlmodel import Session

    from . import journal
    from .database import engine

    with Session(engine) as session:
        posted = journal.backfill(session)
    if posted:
        logger.info("Booked %s transaction(s) into the journal", posted)


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(accounts.router)
app.include_router(products.router)
app.include_router(transactions.router)
app.include_router(interest_router.router)
app.include_router(dashboard.router)
app.include_router(auth_router.router)
app.include_router(groups.router)
app.include_router(loans.router)
app.include_router(me.router)
app.include_router(operations.router)
app.include_router(webhooks.router)
