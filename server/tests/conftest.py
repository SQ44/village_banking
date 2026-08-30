"""Test fixtures: an in-memory app with a real database and a fake Lipila.

Two things are faked and nothing else. The database is SQLite in memory, so
each test starts from an empty schema built from the same models production
uses. Lipila is replaced by `FakeLipila`, because the point of most of these
tests is what this app does with a given provider answer, and a real HTTP call
would test Lipila instead.

Everything else — the routers, the ledger, the idempotency table, the audit
trail — is the production code path.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Iterator, Optional

import pytest

# Settings are read at import time, so the environment has to be arranged before
# anything under `app` is imported.
os.environ.setdefault("database_url", "sqlite://")
os.environ.setdefault("auth_secret_key", "test-secret-key")
os.environ.setdefault("default_admin_email", "")
os.environ.setdefault("default_admin_password", "")
os.environ.setdefault("lipila_api_key", "test-key")
os.environ.setdefault("lipila_callback_base_url", "http://testserver")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app import database  # noqa: E402
from app.auth import create_user, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Account,
    Group,
    GroupSettings,
    Membership,
    MembershipRole,
    User,
)
from app.schemas import UserCreate  # noqa: E402


@pytest.fixture(name="engine")
def engine_fixture():
    """One in-memory database shared by every connection in a single test.

    StaticPool keeps SQLite's in-memory database alive across the connections
    the app opens; without it each connection would get its own empty database.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="session")
def session_fixture(engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(engine, session) -> Iterator[TestClient]:
    """The real app, wired to the test database.

    The session is overridden rather than replaced per-request so that a test
    can inspect the same session the endpoint wrote through, without having to
    expire and reload everything.
    """

    def get_session_override():
        yield session

    app.dependency_overrides[database.get_session] = get_session_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ----------------------------------------------------------------------
# People and groups
# ----------------------------------------------------------------------


@pytest.fixture(name="admin")
def admin_fixture(session) -> User:
    return create_user(
        session,
        UserCreate(email="admin@example.com", full_name="Admin", role="admin", password="admin-pass"),
    )


@pytest.fixture(name="member_user")
def member_user_fixture(session) -> User:
    return create_user(
        session,
        UserCreate(email="member@example.com", full_name="Member", role="member", password="member-pass"),
    )


def _token(client: TestClient, email: str, password: str) -> str:
    response = client.post("/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(name="admin_auth")
def admin_auth_fixture(client, admin) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, 'admin@example.com', 'admin-pass')}"}


@pytest.fixture(name="member_auth")
def member_auth_fixture(client, member_user) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, 'member@example.com', 'member-pass')}"}


@pytest.fixture(name="group")
def group_fixture(session, admin) -> Group:
    group = Group(name="Chilenje Savers", terms="Contribute monthly.")
    session.add(group)
    session.commit()
    session.refresh(group)

    session.add(GroupSettings(group_id=group.id, min_monthly_contribution=0))
    session.add(
        Membership(
            group_id=group.id,
            user_id=admin.id,
            role=MembershipRole.ADMIN,
            accepted_terms_at=datetime.utcnow(),
        )
    )
    session.commit()
    return group


@pytest.fixture(name="account")
def account_fixture(session, group, member_user) -> Account:
    """A member with a group account, accepted terms and a phone number."""
    account = Account(
        name="Mutale",
        email="member@example.com",
        group_id=group.id,
        group_name=group.name,
        user_id=member_user.id,
        balance=0,
        custom_fields={"phone": "0977123456"},
    )
    session.add(account)
    session.commit()
    session.refresh(account)

    session.add(
        Membership(
            group_id=group.id,
            user_id=member_user.id,
            account_id=account.id,
            role=MembershipRole.MEMBER,
            accepted_terms_at=datetime.utcnow(),
        )
    )
    session.commit()
    return account


# ----------------------------------------------------------------------
# A stand-in for Lipila
# ----------------------------------------------------------------------


class FakeLipila:
    """Records every collection asked for, and answers however a test wants.

    `calls` is the point of it: the double-charge tests assert on how many times
    a payment was actually requested, which is the thing that costs a member
    real money.
    """

    def __init__(self, status: str = "pending", payload: Optional[dict[str, Any]] = None):
        self.status = status
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    async def start_collection(self, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        self.calls.append(kwargs)
        reference = kwargs["transaction"].provider_reference
        payload = self.payload if self.payload is not None else {
            "status": self.status,
            "referenceId": reference,
            "identifier": f"LIP-{len(self.calls)}",
        }
        return self.status, payload

    async def start_payout(self, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        self.calls.append(kwargs)
        reference = kwargs["transaction"].provider_reference
        payload = self.payload if self.payload is not None else {
            "status": self.status,
            "referenceId": reference,
        }
        return self.status, payload


@pytest.fixture(name="fake_lipila")
def fake_lipila_fixture(monkeypatch) -> FakeLipila:
    """Patch the provider calls, leaving all the orchestration around them real."""
    fake = FakeLipila()

    from app.lipila import service as lipila_service

    monkeypatch.setattr(lipila_service, "start_collection", fake.start_collection)
    monkeypatch.setattr(lipila_service, "start_payout", fake.start_payout)
    return fake
