import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import Session, select

from .config import get_settings
from .database import engine
from .interest import apply_interest
from .lipila import service as lipila
from .models import Account, InterestAccrual, SavingsProduct, Transaction, TransactionStatus
from .notifications import send_email

logger = logging.getLogger(__name__)
settings = get_settings()
scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)

# A payment younger than this is still plausibly waiting on the member to
# approve it on their handset, so polling it would only add noise.
PAYMENT_RECOVERY_MIN_AGE = timedelta(minutes=2)
PAYMENT_RECOVERY_BATCH = 50


def schedule_jobs() -> None:
    if scheduler.running:
        return
    scheduler.add_job(run_scheduled_interest, "cron", hour=1, minute=0)
    scheduler.add_job(generate_weekly_statements, "cron", day_of_week="fri", hour=6, minute=0)
    if settings.lipila_configured:
        scheduler.add_job(reconcile_pending_payments, "interval", minutes=2)
    scheduler.start()
    logger.info("Background scheduler started with interest + statement jobs")


async def reconcile_pending_payments() -> None:
    """Catch payments whose webhook never arrived.

    Lipila is the authority on whether money moved. A webhook can be lost to a
    network blip or a restart, so anything left pending past a short grace
    period is asked about directly rather than sitting unresolved forever.
    """
    cutoff = datetime.utcnow() - PAYMENT_RECOVERY_MIN_AGE
    with Session(engine) as session:
        stale = session.exec(
            select(Transaction)
            .where(Transaction.provider == lipila.PROVIDER_NAME)
            .where(Transaction.status == TransactionStatus.PENDING)
            .where(Transaction.created_at <= cutoff)
            .order_by(Transaction.created_at.asc())
            .limit(PAYMENT_RECOVERY_BATCH)
        ).all()
        for transaction in stale:
            try:
                outcome = await lipila.refresh_transaction_status(session, transaction, settings)
            except Exception:
                logger.exception("Failed to refresh Lipila transaction %s", transaction.id)
                continue
            logger.info("Reconciled transaction %s -> %s", transaction.id, outcome)


def run_scheduled_interest() -> None:
    logger.info("Running scheduled interest accrual job")
    now = datetime.utcnow()
    with Session(engine) as session:
        accounts = session.exec(select(Account)).all()
        for account in accounts:
            product = account.product
            if not product and account.product_id:
                product = session.get(SavingsProduct, account.product_id)
            if not product:
                continue
            last_accrual = session.exec(
                select(InterestAccrual)
                .where(InterestAccrual.account_id == account.id)
                .order_by(InterestAccrual.period_end.desc())
            ).first()
            period_start = last_accrual.period_end if last_accrual else account.created_at
            days_since = (now - period_start).days
            if days_since < product.compounding_days:
                continue
            accrual = apply_interest(
                session,
                account,
                annual_rate=product.interest_rate,
                period_start=period_start,
                period_end=now,
            )
            logger.info("Applied %s interest to account %s", accrual.amount, account.id)


def generate_weekly_statements() -> None:
    logger.info("Generating weekly statement summaries")
    window_start = datetime.utcnow() - timedelta(days=7)
    with Session(engine) as session:
        accounts = session.exec(select(Account)).all()
        for account in accounts:
            transactions = session.exec(
                select(Transaction)
                .where(Transaction.account_id == account.id)
                .where(Transaction.created_at >= window_start)
                .order_by(Transaction.created_at.asc())
            ).all()
            if not transactions:
                continue
            total = sum(tx.amount for tx in transactions)
            subject = f"Weekly statement · {account.name} · ending {datetime.utcnow().date().isoformat()}"
            custom_fields = account.custom_fields or {}
            recipient_hint = account.email or custom_fields.get("statement_email")
            recipients = [recipient_hint] if recipient_hint else []
            body_lines = [
                f"Hello {account.name},",
                "",
                "Here is your weekly activity summary:",
                f"- Window start: {window_start.date().isoformat()}",
                f"- Transactions captured: {len(transactions)}",
                f"- Net amount: K {total:.2f}",
                "",
                "Detailed ledger:",
            ]
            for tx in transactions:
                tx_type = tx.type.value if hasattr(tx.type, "value") else tx.type
                tx_status = tx.status.value if hasattr(tx.status, "value") else tx.status
                body_lines.append(
                    f"• {tx.created_at.strftime('%Y-%m-%d %H:%M')} | {tx_type} | {tx_status} | K {tx.amount:.2f} | {tx.description or '-'}"
                )
            body_lines.append("")
            body_lines.append("Cheers,")
            body_lines.append("Village Banking Bot")
            sent = send_email(subject, "\n".join(body_lines), recipients)
            if not sent:
                logger.warning(
                    "Statement prepared for account %s (%s transactions, total %.2f) but email not sent",
                    account.id,
                    len(transactions),
                    total,
                )
