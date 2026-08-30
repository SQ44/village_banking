"""The restatement script, against a database that really is dirty.

The application reads a legacy float column back as a clean Decimal, so it
behaves correctly with or without this script. What the script fixes is what is
*written down* — and a ledger whose stored figures differ from the ones it
reports is not one anybody can sign off. These tests build a database holding
the exact values float arithmetic produces, then check the restatement.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlmodel import Session, select

from app.models import Account, Transaction, TransactionStatus, TransactionType


def _write_raw(engine, table: str, column: str, row_id: int, raw: float) -> None:
    """Put a float straight into the column, as the old code would have."""
    with engine.begin() as conn:
        conn.execute(
            text(f'UPDATE "{table}" SET {column} = :v WHERE id = :i'), {"v": raw, "i": row_id}
        )


def _read_raw(engine, table: str, column: str, row_id: int):
    with engine.begin() as conn:
        return conn.execute(
            text(f'SELECT {column} FROM "{table}" WHERE id = :i'), {"i": row_id}
        ).scalar()


@pytest.fixture(name="dirty_account")
def dirty_account_fixture(session, account, engine) -> Account:
    """An account holding the value a float `+=` loop actually produces."""
    amounts = [350.10, 350.10, 275.35, 420.55, 199.99, 350.10] * 4
    drifted = 0.0
    for amount in amounts:
        drifted += amount
    assert drifted != 7784.76, "the fixture must actually be dirty"
    _write_raw(engine, "account", "balance", account.id, drifted)
    return account


class TestRestatement:
    def test_a_drifted_balance_is_stored_imprecisely(self, dirty_account, engine):
        """Establishes the premise the rest of the file rests on."""
        assert _read_raw(engine, "account", "balance", dirty_account.id) == 7784.760000000002

    def test_the_application_already_reads_it_cleanly(self, session, dirty_account):
        """Which is why this migration is about the record, not the behaviour."""
        session.expire_all()
        reloaded = session.get(Account, dirty_account.id)
        assert reloaded.balance == Decimal("7784.76")

    def test_restating_writes_the_exact_figure(self, dirty_account, engine, monkeypatch):
        from scripts import migrate_money_to_decimal as migration

        monkeypatch.setattr(migration, "engine", engine)
        changed = migration.restate(dry_run=False)

        assert changed == 1
        assert _read_raw(engine, "account", "balance", dirty_account.id) in (
            "7784.76",
            7784.76,
        )

    def test_a_dry_run_writes_nothing(self, dirty_account, engine, monkeypatch):
        from scripts import migrate_money_to_decimal as migration

        monkeypatch.setattr(migration, "engine", engine)
        changed = migration.restate(dry_run=True)

        assert changed == 1
        assert _read_raw(engine, "account", "balance", dirty_account.id) == 7784.760000000002

    def test_running_it_twice_changes_nothing_the_second_time(self, dirty_account, engine, monkeypatch):
        """Safe to re-run, which is what makes it deployable."""
        from scripts import migrate_money_to_decimal as migration

        monkeypatch.setattr(migration, "engine", engine)
        assert migration.restate(dry_run=False) == 1
        assert migration.restate(dry_run=False) == 0

    def test_a_clean_database_needs_no_restating(self, session, account, engine, monkeypatch):
        from scripts import migrate_money_to_decimal as migration

        account.balance = Decimal("500.00")
        session.add(account)
        session.commit()

        monkeypatch.setattr(migration, "engine", engine)
        assert migration.restate(dry_run=False) == 0

    def test_it_rounds_half_up_like_everything_else(self, session, account, engine, monkeypatch):
        """A legacy half-ngwee is restated on the same rule the app now uses."""
        from scripts import migrate_money_to_decimal as migration

        _write_raw(engine, "account", "balance", account.id, 2.675)
        monkeypatch.setattr(migration, "engine", engine)
        migration.restate(dry_run=False)

        session.expire_all()
        assert session.get(Account, account.id).balance == Decimal("2.68")

    def test_transactions_are_restated_too(self, session, account, engine, monkeypatch):
        from scripts import migrate_money_to_decimal as migration

        transaction = Transaction(
            account_id=account.id,
            amount=Decimal("10.00"),
            type=TransactionType.DEPOSIT,
            status=TransactionStatus.COMPLETED,
        )
        session.add(transaction)
        session.commit()
        session.refresh(transaction)

        _write_raw(engine, "transaction", "amount", transaction.id, 10.000000000000002)
        monkeypatch.setattr(migration, "engine", engine)
        assert migration.restate(dry_run=False) == 1

        session.expire_all()
        assert session.get(Transaction, transaction.id).amount == Decimal("10.00")
