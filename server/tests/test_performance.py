"""The overview's figures, and who is allowed to read them.

Two things are pinned here. The first is arithmetic: portfolio at risk is the
measure the dashboard leads with, and getting it wrong would tell a group its
loan book is healthy while members' savings quietly go bad. The second is
reach: a group administrator runs their own group and must not be able to read
anybody else's, which is a property of the endpoint rather than of the screen
that calls it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.auth import create_user
from app.models import (
    Account,
    Group,
    GroupSettings,
    InstallmentStatus,
    Loan,
    LoanInstallment,
    LoanStatus,
    Membership,
    MembershipRole,
    RepaymentFrequency,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.money import money
from app.performance import build_group_performance
from app.schemas import UserCreate


def _loan(session: Session, group: Group, account: Account, *, principal: str, outstanding: str) -> Loan:
    loan = Loan(
        group_id=group.id,
        borrower_account_id=account.id,
        principal=money(principal),
        interest_rate_percent=money("10.00"),
        admin_fee_percent=money("10.00"),
        term_months=3,
        repayment_frequency=RepaymentFrequency.MONTHLY,
        outstanding_principal=money(outstanding),
        outstanding_interest=money("0.00"),
        status=LoanStatus.ACTIVE,
    )
    session.add(loan)
    session.commit()
    session.refresh(loan)
    return loan


def _installment(session: Session, loan: Loan, *, due_days_ago: int, status: InstallmentStatus, paid_at=None):
    session.add(
        LoanInstallment(
            loan_id=loan.id,
            sequence=1,
            due_date=datetime.utcnow() - timedelta(days=due_days_ago),
            principal_due=money("100.00"),
            interest_due=money("10.00"),
            status=status,
            paid_at=paid_at,
        )
    )
    session.commit()


class TestPortfolioAtRisk:
    """A loan is contaminated whole, and measured by balance rather than count."""

    def test_a_loan_with_an_overdue_installment_puts_its_whole_balance_at_risk(
        self, session, group, account
    ):
        # Two loans of equal count, very unequal size. Only the large one is late.
        late = _loan(session, group, account, principal="5000.00", outstanding="4000.00")
        _loan(session, group, account, principal="1000.00", outstanding="1000.00")
        _installment(session, late, due_days_ago=5, status=InstallmentStatus.DUE)

        performance = build_group_performance(session, group_id=group.id)

        # The whole remaining balance is at risk, not the K110 that is overdue.
        assert performance.portfolio.at_risk_amount == money("4000.00")
        assert performance.portfolio.at_risk_loans == 1
        # 4000 of 5000 outstanding.
        assert performance.portfolio.par_percent == pytest.approx(80, abs=0.01)
        # ...but the arrears themselves are only the overdue installment.
        assert performance.portfolio.arrears_amount == money("110.00")

    def test_an_installment_not_yet_due_is_not_arrears(self, session, group, account):
        loan = _loan(session, group, account, principal="1000.00", outstanding="1000.00")
        session.add(
            LoanInstallment(
                loan_id=loan.id,
                sequence=1,
                due_date=datetime.utcnow() + timedelta(days=7),
                principal_due=money("100.00"),
                interest_due=money("10.00"),
                status=InstallmentStatus.DUE,
            )
        )
        session.commit()

        performance = build_group_performance(session, group_id=group.id)

        assert performance.portfolio.at_risk_amount == money("0.00")
        assert performance.portfolio.par_percent == pytest.approx(0, abs=0.01)

    def test_the_thirty_day_benchmark_excludes_a_loan_only_days_late(self, session, group, account):
        loan = _loan(session, group, account, principal="1000.00", outstanding="1000.00")
        _installment(session, loan, due_days_ago=5, status=InstallmentStatus.DUE)

        performance = build_group_performance(session, group_id=group.id)

        # Late by any measure...
        assert performance.portfolio.par_percent == pytest.approx(100, abs=0.01)
        # ...but not yet by the thirty-day one.
        assert performance.portfolio.par_benchmark_percent == pytest.approx(0, abs=0.01)
        assert performance.portfolio.par_benchmark_days == 30

    def test_a_group_with_no_loans_reports_no_ratio_rather_than_zero_percent(self, session, group):
        performance = build_group_performance(session, group_id=group.id)

        # Not 0.00: a group with no portfolio has not earned a clean bill of health.
        assert performance.portfolio.par_percent is None
        assert performance.portfolio.on_time_percent is None


class TestRepaymentDiscipline:
    def test_an_installment_paid_after_its_due_date_counts_against_the_rate(
        self, session, group, account
    ):
        loan = _loan(session, group, account, principal="1000.00", outstanding="500.00")
        due = datetime.utcnow() - timedelta(days=20)
        session.add(
            LoanInstallment(
                loan_id=loan.id, sequence=1, due_date=due, principal_due=money("100.00"),
                interest_due=money("10.00"), status=InstallmentStatus.PAID,
                paid_at=due - timedelta(days=1),
            )
        )
        session.add(
            LoanInstallment(
                loan_id=loan.id, sequence=2, due_date=due, principal_due=money("100.00"),
                interest_due=money("10.00"), status=InstallmentStatus.PAID,
                paid_at=due + timedelta(days=3),
            )
        )
        session.commit()

        performance = build_group_performance(session, group_id=group.id)

        assert performance.portfolio.settled_installments == 2
        assert performance.portfolio.on_time_installments == 1
        assert performance.portfolio.on_time_percent == pytest.approx(50, abs=0.01)


class TestCycleMovement:
    def test_only_completed_money_counts_as_growth(self, session, group, account):
        now = datetime.utcnow()
        for amount, status in [
            ("500.00", TransactionStatus.COMPLETED),
            ("900.00", TransactionStatus.PENDING),
            ("300.00", TransactionStatus.FAILED),
        ]:
            session.add(
                Transaction(
                    account_id=account.id,
                    amount=money(amount),
                    type=TransactionType.DEPOSIT,
                    status=status,
                    created_at=now - timedelta(days=2),
                )
            )
        session.commit()

        performance = build_group_performance(session, group_id=group.id)

        # A prompt sitting unanswered on a handset is not savings.
        assert performance.cycle.deposits == money("500.00")
        assert performance.cycle.net_savings == money("500.00")

    def test_the_previous_cycle_is_reported_alongside_the_current_one(self, session, group, account):
        now = datetime.utcnow()
        session.add(
            Transaction(
                account_id=account.id, amount=money("400.00"), type=TransactionType.DEPOSIT,
                status=TransactionStatus.COMPLETED, created_at=now - timedelta(days=3),
            )
        )
        session.add(
            Transaction(
                account_id=account.id, amount=money("100.00"), type=TransactionType.DEPOSIT,
                status=TransactionStatus.COMPLETED, created_at=now - timedelta(days=40),
            )
        )
        session.commit()

        performance = build_group_performance(session, group_id=group.id)

        assert performance.cycle.net_savings == money("400.00")
        assert performance.cycle.previous_net_savings == money("100.00")

    def test_participation_counts_distinct_members_not_deposits(self, session, group, account):
        now = datetime.utcnow()
        for _ in range(3):
            session.add(
                Transaction(
                    account_id=account.id, amount=money("100.00"), type=TransactionType.DEPOSIT,
                    status=TransactionStatus.COMPLETED, created_at=now - timedelta(days=1),
                )
            )
        session.commit()

        performance = build_group_performance(session, group_id=group.id)

        # Three deposits, one member.
        assert performance.cycle.contributing_members == 1
        assert performance.cycle.member_count == 1
        assert performance.cycle.participation_percent == pytest.approx(100, abs=0.01)


class TestWhoMayReadIt:
    """A group administrator runs one group and can see exactly that one."""

    @pytest.fixture(name="other_group")
    def other_group_fixture(self, session, admin) -> Group:
        other = Group(name="Kabwata Savers", terms="")
        session.add(other)
        session.commit()
        session.refresh(other)
        session.add(GroupSettings(group_id=other.id))
        session.commit()
        return other

    @pytest.fixture(name="group_admin_auth")
    def group_admin_auth_fixture(self, session, client, group) -> dict[str, str]:
        user = create_user(
            session,
            UserCreate(
                email="chair@example.com", full_name="Chair",
                role="group_admin", password="chair-pass",
            ),
        )
        session.add(
            Membership(
                group_id=group.id, user_id=user.id, role=MembershipRole.ADMIN,
                accepted_terms_at=datetime.utcnow(),
            )
        )
        session.commit()
        response = client.post(
            "/auth/login", data={"username": "chair@example.com", "password": "chair-pass"}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_a_group_admin_reads_their_own_group(self, client, group_admin_auth, group):
        response = client.get(f"/dashboard/performance?group_id={group.id}", headers=group_admin_auth)
        assert response.status_code == 200, response.text
        assert response.json()["group_id"] == group.id

    def test_a_group_admin_is_refused_another_group(self, client, group_admin_auth, other_group):
        response = client.get(
            f"/dashboard/performance?group_id={other_group.id}", headers=group_admin_auth
        )
        assert response.status_code == 403, response.text

    def test_naming_no_group_falls_back_to_their_own(self, client, group_admin_auth, group):
        response = client.get("/dashboard/performance", headers=group_admin_auth)
        assert response.status_code == 200, response.text
        assert response.json()["group_id"] == group.id

    def test_the_summary_endpoint_is_scoped_the_same_way(self, client, group_admin_auth, other_group):
        response = client.get(f"/dashboard/summary?group_id={other_group.id}", headers=group_admin_auth)
        assert response.status_code == 403, response.text

    def test_a_system_administrator_reads_any_group(self, client, admin_auth, other_group):
        response = client.get(
            f"/dashboard/performance?group_id={other_group.id}", headers=admin_auth
        )
        assert response.status_code == 200, response.text
        assert response.json()["group_id"] == other_group.id


class TestPromotingAGroupAdmin:
    """Handing somebody the running of a group, and taking it back."""

    def test_promotion_grants_the_group_and_nothing_wider(
        self, session, client, admin_auth, account, group, member_user
    ):
        response = client.post(
            f"/groups/{group.id}/members/{account.id}/role",
            json={"role": "admin"},
            headers=admin_auth,
        )
        assert response.status_code == 200, response.text
        assert response.json()["role"] == "admin"

        session.refresh(member_user)
        # Their platform role moves so they land in the admin console...
        assert member_user.role == "group_admin"
        # ...but that role is not a platform administrator.
        from app.roles import is_platform_admin

        assert not is_platform_admin(member_user)

    def test_a_promoted_member_cannot_read_another_group(
        self, session, client, admin_auth, account, group
    ):
        other = Group(name="Kabwata Savers", terms="")
        session.add(other)
        session.commit()
        session.refresh(other)
        session.add(GroupSettings(group_id=other.id))
        session.commit()

        client.post(
            f"/groups/{group.id}/members/{account.id}/role",
            json={"role": "admin"},
            headers=admin_auth,
        )
        token = client.post(
            "/auth/login", data={"username": "member@example.com", "password": "member-pass"}
        ).json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        assert client.get(f"/dashboard/performance?group_id={group.id}", headers=auth).status_code == 200
        assert client.get(f"/dashboard/performance?group_id={other.id}", headers=auth).status_code == 403
        # The group list they are offered is their own group only.
        listed = client.get("/groups", headers=auth).json()
        assert [g["id"] for g in listed] == [group.id]

    def test_the_last_administrator_cannot_be_demoted(
        self, session, client, admin_auth, account, group
    ):
        # Make the member the group's only addressable administrator, then strip
        # the seeded one, so the member is genuinely the last one left.
        client.post(
            f"/groups/{group.id}/members/{account.id}/role",
            json={"role": "admin"},
            headers=admin_auth,
        )
        seeded = session.exec(
            select(Membership).where(
                Membership.group_id == group.id,
                Membership.account_id.is_(None),
                Membership.role == MembershipRole.ADMIN,
            )
        ).first()
        seeded.role = MembershipRole.MEMBER
        session.add(seeded)
        session.commit()

        response = client.post(
            f"/groups/{group.id}/members/{account.id}/role",
            json={"role": "member"},
            headers=admin_auth,
        )

        # A group nobody can administer is stuck until a system admin steps in.
        assert response.status_code == 400, response.text
        assert "at least one administrator" in response.json()["detail"]

    def test_demotion_returns_them_to_the_member_console(
        self, session, client, admin_auth, account, group, member_user
    ):
        client.post(
            f"/groups/{group.id}/members/{account.id}/role",
            json={"role": "admin"},
            headers=admin_auth,
        )
        response = client.post(
            f"/groups/{group.id}/members/{account.id}/role",
            json={"role": "member"},
            headers=admin_auth,
        )
        assert response.status_code == 200, response.text
        session.refresh(member_user)
        assert member_user.role == "member"

    def test_an_ordinary_member_cannot_promote_themselves(
        self, client, member_auth, account, group
    ):
        response = client.post(
            f"/groups/{group.id}/members/{account.id}/role",
            json={"role": "admin"},
            headers=member_auth,
        )
        assert response.status_code == 403, response.text
