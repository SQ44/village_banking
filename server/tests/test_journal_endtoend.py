"""The journal as seen from outside: real requests, real settlement, real books.

`test_journal.py` proves the postings are right when called directly. These
prove they actually happen — that the wiring into the settlement paths holds,
and that an admin can read the answer back out. A correct posting function that
nothing calls would pass the other file and still leave the books empty.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import select

from app import journal
from app.models import Account, JournalEntry, Transaction, TransactionStatus, TransactionType
from app.money import money


def _settle(client, session, account, amount, *, fee=None, reference="VB-E2E"):
    """Put a settled Lipila deposit through the real settlement path."""
    from app.lipila import service as lipila

    transaction = Transaction(
        account_id=account.id,
        amount=money(amount),
        type=TransactionType.DEPOSIT,
        status=TransactionStatus.PENDING,
        description="Contribution",
        custom_fields={"currency": "ZMW"},
        created_at=datetime.utcnow(),
        provider="lipila",
        provider_reference=reference,
        provider_status="pending",
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)

    payload = {"referenceId": reference, "status": "success", "amount": str(money(amount))}
    if fee is not None:
        payload["fee"] = str(money(fee))
    lipila.apply_provider_status(session, transaction, "succeeded", payload, source="webhook")
    session.commit()
    return transaction


class TestSettlementWritesTheBooks:
    def test_a_settled_collection_is_booked_and_balances(self, client, session, account):
        _settle(client, session, account, "100.00", fee="2.50", reference="VB-W1")

        entries = session.exec(select(JournalEntry)).all()
        assert len(entries) == 1, "settlement must book exactly one entry"
        assert journal.books_are_balanced(session)

        balances = journal.trial_balance(session)
        assert balances[journal.MEMBER_SAVINGS] == money("100.00")
        assert balances[journal.LIPILA_SETTLEMENT] == money("97.50")
        assert balances[journal.PROVIDER_FEES] == money("2.50")

    def test_the_group_holds_less_than_it_owes_once_fees_are_real(self, session, account):
        """The whole point of recording fees: these two numbers now differ."""
        _settle(None, session, account, "100.00", fee="2.50", reference="VB-W2")
        balances = journal.trial_balance(session)
        assert balances[journal.LIPILA_SETTLEMENT] < balances[journal.MEMBER_SAVINGS]

    def test_control_total_holds_after_real_settlement(self, session, account):
        _settle(None, session, account, "250.00", fee="5.00", reference="VB-W3")
        session.refresh(account)
        assert money(account.balance) == money("250.00")
        assert journal.control_total_matches(session) is True

    def test_a_redelivered_webhook_books_nothing_further(self, session, account):
        from app.lipila import service as lipila

        transaction = _settle(None, session, account, "80.00", reference="VB-W4")
        payload = {"referenceId": "VB-W4", "status": "success", "amount": "80.00"}
        lipila.apply_provider_status(session, transaction, "succeeded", payload, source="webhook")
        session.commit()

        assert len(session.exec(select(JournalEntry)).all()) == 1
        assert journal.trial_balance(session)[journal.MEMBER_SAVINGS] == money("80.00")


class TestBackfill:
    def test_history_without_entries_is_booked_once(self, session, account):
        """An existing database must not read as a discrepancy on first run."""
        for i, amount in enumerate(["10.00", "20.00"]):
            session.add(
                Transaction(
                    account_id=account.id,
                    amount=money(amount),
                    type=TransactionType.DEPOSIT,
                    status=TransactionStatus.COMPLETED,
                    created_at=datetime.utcnow(),
                    provider="lipila",
                    provider_reference=f"VB-OLD{i}",
                )
            )
        account.balance = money("30.00")
        session.add(account)
        session.commit()

        assert journal.control_total_matches(session) is False  # Nothing booked yet.
        assert journal.backfill(session) == 2
        assert journal.control_total_matches(session) is True
        assert journal.backfill(session) == 0  # Idempotent.


class TestOperationsEndpoints:
    """What an admin actually opens to answer the question."""

    def test_trial_balance_reports_where_the_money_is(self, client, session, account, admin_auth):
        _settle(None, session, account, "100.00", fee="2.50", reference="VB-EP1")

        response = client.get("/operations/trial-balance", headers=admin_auth)
        assert response.status_code == 200, response.text
        body = response.json()

        accounts = {row["account_code"]: row["balance"] for row in body["accounts"]}
        assert money(accounts[journal.MEMBER_SAVINGS]) == money("100.00")
        assert money(accounts[journal.LIPILA_SETTLEMENT]) == money("97.50")
        assert money(accounts[journal.PROVIDER_FEES]) == money("2.50")
        assert body["balanced"] is True
        assert body["control_total_matches"] is True

    def test_trial_balance_is_admin_only(self, client, session, account, member_auth):
        response = client.get("/operations/trial-balance", headers=member_auth)
        assert response.status_code == 403

    def test_journal_lists_entries_with_both_sides(self, client, session, account, admin_auth):
        _settle(None, session, account, "60.00", fee="1.00", reference="VB-EP2")

        response = client.get("/operations/journal", headers=admin_auth)
        assert response.status_code == 200, response.text
        entries = response.json()
        assert len(entries) == 1
        codes = {line["account_code"] for line in entries[0]["lines"]}
        assert codes == {journal.MEMBER_SAVINGS, journal.LIPILA_SETTLEMENT, journal.PROVIDER_FEES}

    def test_member_statement_shows_a_running_balance(self, client, session, account, admin_auth):
        _settle(None, session, account, "100.00", reference="VB-EP3")
        _settle(None, session, account, "50.00", reference="VB-EP4")

        response = client.get(f"/accounts/{account.id}/statement", headers=admin_auth)
        assert response.status_code == 200, response.text
        lines = response.json()
        assert [money(line["running_balance"]) for line in lines] == [money("100.00"), money("150.00")]

    def test_a_member_may_read_their_own_statement(self, client, session, account, member_auth):
        _settle(None, session, account, "40.00", reference="VB-EP5")
        response = client.get(f"/accounts/{account.id}/statement", headers=member_auth)
        assert response.status_code == 200, response.text
        assert money(response.json()[-1]["running_balance"]) == money("40.00")

    def test_a_member_may_not_read_someone_else_s(self, client, session, group, member_auth):
        other = Account(name="Someone Else", group_id=group.id, balance=money("0.00"), custom_fields={})
        session.add(other)
        session.commit()
        session.refresh(other)

        response = client.get(f"/accounts/{other.id}/statement", headers=member_auth)
        assert response.status_code == 403


class TestAttentionSurfacesDrift:
    """The books disagreeing with the balances has to reach a person."""

    def test_clean_books_report_no_drift(self, client, session, account, admin_auth):
        _settle(None, session, account, "100.00", reference="VB-AT1")
        body = client.get("/operations/attention", headers=admin_auth).json()
        assert body["books_balanced"] is True
        assert body["control_total_matches"] is True

    def test_a_balance_moved_behind_the_books_is_reported(self, client, session, account, admin_auth):
        """A hand on the pot that leaves no entry — invisible before double-entry."""
        _settle(None, session, account, "100.00", reference="VB-AT2")
        account.balance = money("900.00")
        session.add(account)
        session.commit()

        body = client.get("/operations/attention", headers=admin_auth).json()
        assert body["control_total_matches"] is False
