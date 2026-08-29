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
    products,
    transactions,
    webhooks,
)
from .tasks import schedule_jobs

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
    schedule_jobs()


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
app.include_router(webhooks.router)
