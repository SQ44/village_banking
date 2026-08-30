from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Optional

from sqlmodel import Session, select
from sqlalchemy import func

from .group_finance import net_contributions_by_account
from .money import ZERO, money, percent_of, rate as as_rate
from .loan_service import create_loan_internal
from .models import GroupSettings, Loan, LoanRequest, LoanRequestStatus, LoanStatus

AutoDecision = Literal["approve", "reject", "queue"]


def _positive_contributions_total(session: Session, *, group_id: int) -> Decimal:
    contributions = net_contributions_by_account(session, group_id=group_id)
    running = ZERO
    for value in contributions.values():
        running += max(money(value), ZERO)
    return running


def _borrower_positive_contribution(session: Session, *, group_id: int, borrower_account_id: int) -> Decimal:
    contributions = net_contributions_by_account(session, group_id=group_id)
    return max(money(contributions.get(int(borrower_account_id), 0)), ZERO)


def _outstanding_principal_total(session: Session, *, group_id: int) -> Decimal:
    total = session.exec(
        select(func.coalesce(func.sum(Loan.outstanding_principal), 0.0)).where(
            Loan.group_id == group_id,
            Loan.status == LoanStatus.ACTIVE,
        )
    ).one()
    return money(total or 0)


def _active_loans_for_borrower(session: Session, *, group_id: int, borrower_account_id: int) -> int:
    total = session.exec(
        select(func.count(Loan.id)).where(
            Loan.group_id == group_id,
            Loan.borrower_account_id == borrower_account_id,
            Loan.status == LoanStatus.ACTIVE,
        )
    ).one()
    return int(total or 0)


def _last_closed_at(session: Session, *, group_id: int, borrower_account_id: int) -> Optional[datetime]:
    closed = session.exec(
        select(func.max(Loan.closed_at)).where(
            Loan.group_id == group_id,
            Loan.borrower_account_id == borrower_account_id,
            Loan.status == LoanStatus.CLOSED,
        )
    ).one()
    return closed


def evaluate_loan_request(
    *,
    session: Session,
    settings: GroupSettings,
    borrower_account_id: int,
    principal: Decimal,
    term_months: int,
    now: datetime,
) -> tuple[AutoDecision, int, str, list[dict[str, Any]]]:
    scorecard: list[dict[str, Any]] = []

    if settings.constitution_locked_at is None:
        return (
            "reject",
            term_months,
            "Constitution is not locked yet for this cycle.",
            [{"rule": "constitution_locked", "pass": False, "detail": "Lock constitution to enable auto lending"}],
        )

    min_term = int(settings.min_term_months or 1)
    max_term = int(settings.max_term_months or 12)
    clamped_term = max(min_term, min(int(term_months), max_term))
    scorecard.append(
        {
            "rule": "term_range",
            "pass": clamped_term == int(term_months),
            "detail": f"Using term {clamped_term} month(s) (allowed {min_term}-{max_term})",
        }
    )

    borrower_contribution = _borrower_positive_contribution(session, group_id=settings.group_id, borrower_account_id=borrower_account_id)
    max_loan_by_multiplier: Decimal | None = None
    if settings.enforce_loan_limit:
        max_loan_by_multiplier = money(borrower_contribution * Decimal(settings.loan_limit_multiplier))
        scorecard.append(
            {
                "rule": "loan_limit_multiplier",
                "pass": principal <= max_loan_by_multiplier or max_loan_by_multiplier <= ZERO,
                "detail": f"Requested {principal:.2f}, max {max_loan_by_multiplier:.2f} (contribution {borrower_contribution:.2f} x {Decimal(settings.loan_limit_multiplier):.2f})",
            }
        )
        if principal > max_loan_by_multiplier and max_loan_by_multiplier > ZERO:
            return ("reject", clamped_term, f"Requested amount exceeds max allowed ({max_loan_by_multiplier:.2f}).", scorecard)
    else:
        scorecard.append({"rule": "loan_limit_multiplier", "pass": True, "detail": "Loan limit disabled"})

    active_loans = _active_loans_for_borrower(session, group_id=settings.group_id, borrower_account_id=borrower_account_id)
    max_active = int(settings.max_active_loans_per_member or 1)
    scorecard.append(
        {
            "rule": "max_active_loans",
            "pass": active_loans < max_active,
            "detail": f"Active loans {active_loans} / max {max_active}",
        }
    )
    if active_loans >= max_active:
        return ("reject", clamped_term, "You already have an active loan.", scorecard)

    cooldown_days = int(settings.cooldown_days_after_settlement or 0)
    if cooldown_days > 0:
        last_closed = _last_closed_at(session, group_id=settings.group_id, borrower_account_id=borrower_account_id)
        if last_closed is None:
            scorecard.append({"rule": "cooldown", "pass": True, "detail": "No prior closed loan"})
        else:
            eligible_at = last_closed + timedelta(days=cooldown_days)
            passed = now >= eligible_at
            scorecard.append(
                {
                    "rule": "cooldown",
                    "pass": passed,
                    "detail": f"Last settled {last_closed.isoformat()} (eligible after {eligible_at.date().isoformat()})",
                }
            )
            if not passed:
                return ("reject", clamped_term, f"Cooldown period active until {eligible_at.date().isoformat()}.", scorecard)
    else:
        scorecard.append({"rule": "cooldown", "pass": True, "detail": "No cooldown"})

    pool_total = _positive_contributions_total(session, group_id=settings.group_id)
    outstanding = _outstanding_principal_total(session, group_id=settings.group_id)
    cap_percent = as_rate(settings.liquidity_max_outstanding_percent or 80)
    allowed = percent_of(pool_total, cap_percent)
    after = outstanding + money(principal)
    # Exact: no epsilon, because both sides are whole ngwee.
    within = after <= allowed
    scorecard.append(
        {
            "rule": "liquidity_cap",
            "pass": within,
            "detail": f"Outstanding {outstanding:.2f} + requested {principal:.2f} <= {allowed:.2f} ({cap_percent:.1f}% of pool {pool_total:.2f})",
        }
    )
    if pool_total <= ZERO:
        return ("reject", clamped_term, "Pool has no contributions yet.", scorecard)
    if not within:
        return ("queue", clamped_term, "Queued: liquidity cap would be exceeded. Will auto-approve when capacity is available.", scorecard)

    return ("approve", clamped_term, "Approved automatically by group constitution.", scorecard)


def auto_decide_and_apply(
    *,
    session: Session,
    request: LoanRequest,
    settings: GroupSettings,
    now: Optional[datetime] = None,
) -> LoanRequest:
    now = now or datetime.utcnow()

    # Idempotency: don't re-approve an already-approved request.
    if request.status == LoanRequestStatus.APPROVED and (request.custom_fields or {}).get("approved_loan_id"):
        return request
    if request.status in {LoanRequestStatus.REJECTED, LoanRequestStatus.CANCELED}:
        return request

    decision, term_months, reason, scorecard = evaluate_loan_request(
        session=session,
        settings=settings,
        borrower_account_id=request.borrower_account_id,
        principal=money(request.principal),
        term_months=int(request.term_months),
        now=now,
    )

    # NOTE: SQLAlchemy JSON columns do not reliably detect in-place mutations unless configured as mutable.
    # Always build a fresh dict and assign it back.
    new_custom_fields = dict(request.custom_fields or {})
    new_custom_fields["scorecard"] = scorecard
    new_custom_fields["auto_decision"] = True
    request.decision_reason = reason
    request.decided_at = now
    request.decided_by_user_id = None
    request.term_months = int(term_months)

    if decision == "reject":
        request.custom_fields = new_custom_fields
        request.status = LoanRequestStatus.REJECTED
        session.add(request)
        session.commit()
        session.refresh(request)
        return request

    if decision == "queue":
        request.custom_fields = new_custom_fields
        request.status = LoanRequestStatus.QUEUED
        session.add(request)
        session.commit()
        session.refresh(request)
        return request

    loan = create_loan_internal(
        session=session,
        group_id=request.group_id,
        borrower_account_id=request.borrower_account_id,
        principal=money(request.principal),
        term_months=int(request.term_months),
        repayment_frequency=request.repayment_frequency,
        interest_rate_percent=request.interest_rate_percent,
        description=request.description or f"Auto-approved loan request {request.id}",
    )
    new_custom_fields["approved_loan_id"] = loan.id
    request.custom_fields = new_custom_fields
    request.status = LoanRequestStatus.APPROVED
    request.interest_rate_percent = as_rate(loan.interest_rate_percent)
    session.add(request)
    session.commit()
    session.refresh(request)
    return request


def process_queued_requests(session: Session, *, group_id: int, limit: int = 50) -> int:
    settings = session.get(GroupSettings, group_id)
    if not settings or settings.constitution_locked_at is None:
        return 0

    queued = session.exec(
        select(LoanRequest)
        .where(LoanRequest.group_id == group_id, LoanRequest.status.in_([LoanRequestStatus.QUEUED, LoanRequestStatus.REQUESTED]))
        .order_by(LoanRequest.created_at.asc())
        .limit(limit)
    ).all()

    processed = 0
    for req in queued:
        before = req.status
        auto_decide_and_apply(session=session, request=req, settings=settings)
        session.refresh(req)
        if req.status != before:
            processed += 1
        # Stop early if still queued due to liquidity; FIFO fairness.
        if req.status == LoanRequestStatus.QUEUED:
            break
    return processed
