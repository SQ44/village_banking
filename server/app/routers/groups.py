from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from .. import audit, idempotency, journal
from ..money import ZERO, money, percent_of
from ..auth import create_user, get_current_active_user
from ..config import get_settings
from ..database import get_session
from ..group_finance import net_contributions_by_account
from ..lipila import service as lipila
from ..models import Account, Group, GroupSettings, Membership, MembershipRole, PaymentChannel, Transaction, TransactionStatus, TransactionType, User
from ..roles import GROUP_ADMIN_ROLE, MEMBER_ROLE, is_platform_admin
from ..schemas import (
    AcceptTermsRequest,
    AccountRead,
    GroupContributionItem,
    GroupCreate,
    GroupRead,
    GroupSettingsRead,
    GroupSettingsUpdate,
    GroupWithSettings,
    ContributionMethod,
    MemberContributionRequest,
    MemberInvite,
    MemberInviteResponse,
    MemberPayment,
    MemberRoleUpdate,
    MembershipRead,
    UserCreate,
)

router = APIRouter(prefix="/groups", tags=["Groups"])

# Scope names for the idempotency records these endpoints write.
ADD_MEMBER_ENDPOINT = "POST /groups/{group_id}/members"
COLLECT_ENDPOINT = "POST /groups/{group_id}/members/{account_id}/collect"


def _is_platform_admin(user: User) -> bool:
    return is_platform_admin(user)


def _require_platform_admin(user: User) -> None:
    if not _is_platform_admin(user):
        raise HTTPException(status_code=403, detail="Admins only")


def _get_membership(session: Session, *, group_id: int, user_id: int) -> Membership | None:
    statement = select(Membership).where(
        Membership.group_id == group_id,
        Membership.user_id == user_id,
        Membership.is_active.is_(True),
    )
    return session.exec(statement).first()


def _require_group_admin(session: Session, *, group_id: int, user: User) -> Membership:
    membership = _get_membership(session, group_id=group_id, user_id=user.id)
    if not membership or membership.role != MembershipRole.ADMIN:
        raise HTTPException(status_code=403, detail="Group admins only")
    return membership


def _settings_read(settings: GroupSettings) -> GroupSettingsRead:
    return GroupSettingsRead(**settings.model_dump())


def _group_with_settings(group: Group, settings: GroupSettings) -> GroupWithSettings:
    return GroupWithSettings(
        id=group.id,
        name=group.name,
        terms=group.terms,
        created_at=group.created_at,
        updated_at=group.updated_at,
        settings=_settings_read(settings),
    )


@router.get("", response_model=List[GroupRead])
def list_groups(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> List[Group]:
    if _is_platform_admin(current_user):
        return session.exec(select(Group).order_by(Group.created_at.desc())).all()
    statement = (
        select(Group)
        .join(Membership, Membership.group_id == Group.id)
        .where(Membership.user_id == current_user.id, Membership.is_active.is_(True))
        .order_by(Group.created_at.desc())
    )
    return session.exec(statement).all()


@router.post("", response_model=GroupWithSettings, status_code=201)
def create_group(
    payload: GroupCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> GroupWithSettings:
    _require_platform_admin(current_user)
    group = Group(name=payload.name, terms=payload.terms, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    session.add(group)
    session.commit()
    session.refresh(group)

    settings = GroupSettings(group_id=group.id)
    session.add(settings)

    membership = Membership(
        group_id=group.id,
        user_id=current_user.id,
        role=MembershipRole.ADMIN,
        accepted_terms_at=datetime.utcnow(),
    )
    session.add(membership)
    session.commit()
    session.refresh(settings)
    return _group_with_settings(group, settings)


@router.get("/{group_id}", response_model=GroupWithSettings)
def get_group(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> GroupWithSettings:
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if not _is_platform_admin(current_user) and not _get_membership(session, group_id=group_id, user_id=current_user.id):
        raise HTTPException(status_code=403, detail="Not a group member")
    settings = session.get(GroupSettings, group_id)
    if not settings:
        settings = GroupSettings(group_id=group_id)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return _group_with_settings(group, settings)


@router.patch("/{group_id}/settings", response_model=GroupSettingsRead)
def update_group_settings(
    group_id: int,
    payload: GroupSettingsUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> GroupSettingsRead:
    if not _is_platform_admin(current_user):
        _require_group_admin(session, group_id=group_id, user=current_user)
    settings = session.get(GroupSettings, group_id)
    if not settings:
        settings = GroupSettings(group_id=group_id)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    updates = payload.model_dump(exclude_unset=True)
    if settings.constitution_locked_at is not None:
        mutable = {"custom_fields"}
        forbidden = set(updates.keys()) - mutable
        if forbidden:
            raise HTTPException(status_code=400, detail="Constitution is locked for this cycle")
    if "custom_fields" in updates and updates["custom_fields"] is not None:
        # Avoid in-place JSON mutations (may not be detected by SQLAlchemy).
        settings.custom_fields = {**dict(settings.custom_fields or {}), **dict(updates.pop("custom_fields") or {})}
    for key, value in updates.items():
        setattr(settings, key, value)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return _settings_read(settings)


@router.get("/{group_id}/members", response_model=List[MembershipRead])
def list_group_members(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> List[Membership]:
    if not _is_platform_admin(current_user):
        _require_group_admin(session, group_id=group_id, user=current_user)
    statement = select(Membership).where(Membership.group_id == group_id).order_by(Membership.joined_at.desc())
    return session.exec(statement).all()


@router.post("/{group_id}/members/{account_id}/role", response_model=MembershipRead)
def set_member_role(
    group_id: int,
    account_id: int,
    payload: MemberRoleUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> Membership:
    """Promote a member to run this group, or hand the role back.

    A group administrator is an ordinary platform user carrying
    `MembershipRole.ADMIN` here, so promoting somebody grants them this group
    and nothing else: every group-scoped endpoint still puts them through a
    membership lookup. Their platform role moves in step, because that is what
    decides which console they land in when they sign in.

    Demoting the last administrator is refused. A group with nobody able to
    approve a loan or collect a contribution is stuck in a way only a system
    administrator could undo.
    """
    if not _is_platform_admin(current_user):
        _require_group_admin(session, group_id=group_id, user=current_user)

    membership = session.exec(
        select(Membership).where(
            Membership.group_id == group_id,
            Membership.account_id == account_id,
            Membership.is_active.is_(True),
        )
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Not a member of this group")

    target = session.get(User, membership.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Member account has no user")

    if payload.role == membership.role:
        return membership

    if payload.role == MembershipRole.MEMBER:
        remaining = session.exec(
            select(func.count(Membership.id)).where(
                Membership.group_id == group_id,
                Membership.role == MembershipRole.ADMIN,
                Membership.is_active.is_(True),
                Membership.id != membership.id,
            )
        ).one()
        if not remaining:
            raise HTTPException(status_code=400, detail="A group must keep at least one administrator")

    before = {"membership_role": membership.role.value, "user_role": target.role}
    membership.role = payload.role

    # A system administrator keeps their platform role: demoting them inside one
    # group must not cost them the installation.
    if not is_platform_admin(target):
        target.role = GROUP_ADMIN_ROLE if payload.role == MembershipRole.ADMIN else MEMBER_ROLE
        session.add(target)

    session.add(membership)
    audit.record(
        session,
        actor=current_user,
        action="member.role_changed",
        entity_type="membership",
        entity_id=str(membership.id),
        before=before,
        after={"membership_role": membership.role.value, "user_role": target.role},
    )
    session.commit()
    session.refresh(membership)
    return membership


@router.get("/{group_id}/accounts", response_model=List[AccountRead])
def list_group_accounts(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> List[Account]:
    if not _is_platform_admin(current_user):
        _require_group_admin(session, group_id=group_id, user=current_user)
    statement = select(Account).where(Account.group_id == group_id).order_by(Account.created_at.desc())
    return session.exec(statement).all()


def _record_cash_contribution(
    session: Session,
    account: Account,
    *,
    amount: float,
    reason: str,
    actor: User,
    description: str,
) -> MemberPayment:
    """Bank a contribution handed over in person.

    No provider confirms this one — an admin is attesting that the money was
    received. That is a balance moving on somebody's word, so it is written to
    the audit log with who said it and why, and the reason is required.
    """
    if money(amount) <= ZERO:
        raise HTTPException(status_code=400, detail="Contribution amount must be greater than zero")
    if not (reason or "").strip():
        raise HTTPException(status_code=400, detail="A reason is required to record a cash contribution")

    transaction = Transaction(
        account_id=account.id,
        amount=amount,
        type=TransactionType.DEPOSIT,
        status=TransactionStatus.COMPLETED,
        description=description,
        custom_fields={"months_covered": 1, "currency": "ZMW", "settled_in": "cash"},
        created_at=datetime.utcnow(),
    )
    before = {"balance": str(money(account.balance))}
    account.balance = money(account.balance) + money(amount)
    account.updated_at = datetime.utcnow()
    # Paid is paid, however it arrived.
    remaining = dict(account.custom_fields or {})
    remaining.pop("initial_contribution_due", None)
    account.custom_fields = remaining

    session.add(transaction)
    session.add(account)
    # Flushed for the transaction's id, not committed: the audit entry has to
    # land in the same database transaction as the balance it explains, or a
    # crash between two commits leaves money moved with nobody named for it.
    session.flush()

    audit.record(
        session,
        actor=actor,
        action="cash_contribution_recorded",
        entity_type="account",
        entity_id=account.id,
        before=before,
        after={"balance": str(money(account.balance)), "transaction_id": transaction.id},
        reason=reason.strip(),
    )
    session.commit()
    session.refresh(transaction)

    return MemberPayment(
        transaction_id=transaction.id,
        amount=transaction.amount,
        status=transaction.status,
        provider_status=None,
        provider_reference=None,
    )


async def _start_contribution_collection(
    session: Session,
    account: Account,
    *,
    amount: float,
    phone_number: str | None,
    channel: PaymentChannel,
    description: str,
) -> MemberPayment:
    """Ask Lipila to collect a contribution from a member.

    The deposit is written pending and the balance left alone. It moves only
    when the member approves the prompt on their handset and Lipila confirms —
    the same rule every other collection follows.
    """
    settings = get_settings()
    if not settings.lipila_configured:
        raise HTTPException(status_code=503, detail="Lipila is not configured")
    if money(amount) <= ZERO:
        raise HTTPException(status_code=400, detail="Contribution amount must be greater than zero")

    raw_phone = phone_number or (account.custom_fields or {}).get("phone")
    try:
        account_number = lipila.normalize_phone_for_channel(channel, raw_phone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # An admin pressing "Send prompt" twice, or a member and an admin both
    # collecting the same contribution, are separate requests that would each
    # put a prompt on the same handset for the same money. The one already
    # waiting is handed back instead.
    live = lipila.find_live_collection(
        session,
        account_id=account.id,
        amount=amount,
        transaction_type=TransactionType.DEPOSIT,
    )
    if live is not None:
        return MemberPayment(
            transaction_id=live.id,
            amount=live.amount,
            status=live.status,
            provider_status=live.provider_status,
            provider_reference=live.provider_reference,
            card_redirect_url=lipila.find_card_redirect_url((live.custom_fields or {}).get("lipila_response")),
            already_pending=True,
        )

    transaction = Transaction(
        account_id=account.id,
        amount=amount,
        type=TransactionType.DEPOSIT,
        status=TransactionStatus.PENDING,
        description=description,
        custom_fields={"months_covered": 1, "currency": "ZMW"},
        created_at=datetime.utcnow(),
        provider=lipila.PROVIDER_NAME,
        provider_reference=lipila.new_reference(),
        provider_channel=channel,
        provider_status="created",
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)

    reference_data = f"Account {account.id}" + (f" / Group {account.group_id}" if account.group_id else "")
    try:
        provider_status, provider_payload = await lipila.start_collection(
            settings=settings,
            transaction=transaction,
            account=account,
            channel=channel,
            account_number=account_number,
            email=account.email,
            currency="ZMW",
            reference_data=reference_data,
        )
    except lipila.LipilaNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    lipila.apply_provider_status(
        session, transaction, provider_status, provider_payload, source="provider_response"
    )
    session.refresh(transaction)

    return MemberPayment(
        transaction_id=transaction.id,
        amount=transaction.amount,
        status=transaction.status,
        provider_status=transaction.provider_status,
        provider_reference=transaction.provider_reference,
        card_redirect_url=lipila.find_card_redirect_url(provider_payload),
    )


@router.post("/{group_id}/members", response_model=MemberInviteResponse, status_code=201)
async def add_group_member(
    group_id: int,
    payload: MemberInvite,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
    idempotency_key: Optional[str] = Header(default=None, alias=idempotency.IDEMPOTENCY_HEADER),
) -> MemberInviteResponse:
    """Add a member, optionally collecting their initial contribution now.

    Carries an `Idempotency-Key` because the request can both create a user and
    move money: a blind retry would otherwise fail on the duplicate email having
    already sent a payment prompt.
    """
    claim = idempotency.claim(
        session,
        key=idempotency_key,
        endpoint=ADD_MEMBER_ENDPOINT,
        user_id=current_user.id,
        payload={"group_id": group_id, **payload.model_dump(mode="json")},
    )
    if claim.replay is not None:
        return MemberInviteResponse(**claim.replay)

    try:
        result = await _add_group_member(group_id, payload, session, current_user)
    except Exception:
        idempotency.release(session, claim)
        raise

    idempotency.store(session, claim, result, status_code=201)
    return result


async def _add_group_member(
    group_id: int,
    payload: MemberInvite,
    session: Session,
    current_user: User,
) -> MemberInviteResponse:
    if not _is_platform_admin(current_user):
        _require_group_admin(session, group_id=group_id, user=current_user)

    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    existing = session.exec(select(User).where(User.email == payload.email.lower())).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    amount = payload.min_initial_deposit or 0

    # Reject an unusable number before creating anything, so a typo does not
    # leave a half-made member behind.
    method = payload.initial_contribution_method
    settle_now = method in {ContributionMethod.LIPILA, ContributionMethod.CASH}
    if settle_now:
        if amount <= 0:
            raise HTTPException(status_code=400, detail="An initial contribution amount is required to settle it")
        if method == ContributionMethod.LIPILA:
            try:
                lipila.normalize_zambian_phone(payload.phone_number)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        elif not (payload.cash_reason or "").strip():
            raise HTTPException(status_code=400, detail="A reason is required to record a cash contribution")

    user = create_user(
        session,
        UserCreate(
            email=payload.email,
            full_name=payload.full_name,
            role="member",
            password=payload.password,
        ),
    )

    custom_fields = dict(payload.custom_fields or {})
    if payload.phone_number:
        custom_fields["phone"] = payload.phone_number
    # What the member agreed to put in. Kept whether or not it is collected now,
    # so a deferred contribution is still owed rather than forgotten.
    if amount > 0 and not settle_now:
        # Stringified for the JSON column; `money()` reads it back exactly.
        custom_fields["initial_contribution_due"] = str(money(amount))

    account = Account(
        name=payload.name,
        email=payload.email,
        group_id=group_id,
        group_name=group.name,
        user_id=user.id,
        balance=0,
        custom_fields=custom_fields,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(account)
    session.commit()
    session.refresh(account)

    membership = Membership(group_id=group_id, user_id=user.id, account_id=account.id, role=MembershipRole.MEMBER)
    session.add(membership)
    session.commit()
    session.refresh(membership)

    payment = None
    if method == ContributionMethod.LIPILA:
        payment = await _start_contribution_collection(
            session,
            account,
            amount=amount,
            phone_number=payload.phone_number,
            channel=PaymentChannel.MOBILE_MONEY,
            description="Initial contribution",
        )
    elif method == ContributionMethod.CASH:
        payment = _record_cash_contribution(
            session,
            account,
            amount=amount,
            reason=payload.cash_reason or "",
            actor=current_user,
            description="Initial contribution (cash)",
        )
        session.refresh(account)

    return MemberInviteResponse(
        membership=MembershipRead.model_validate(membership, from_attributes=True),
        payment=payment,
        initial_contribution_due=custom_fields.get("initial_contribution_due"),
    )


@router.post("/{group_id}/members/{account_id}/collect", response_model=MemberPayment, status_code=201)
async def collect_member_contribution(
    group_id: int,
    account_id: int,
    payload: MemberContributionRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
    idempotency_key: Optional[str] = Header(default=None, alias=idempotency.IDEMPOTENCY_HEADER),
) -> MemberPayment:
    """Collect from a member who deferred at sign-up and is now ready to pay.

    Guarded twice over: an `Idempotency-Key` catches the same request arriving
    again after a lost reply, and `find_live_collection` catches a second press
    of the button, which is a different request asking for the same money.
    """
    claim = idempotency.claim(
        session,
        key=idempotency_key,
        endpoint=COLLECT_ENDPOINT,
        user_id=current_user.id,
        payload={"group_id": group_id, "account_id": account_id, **payload.model_dump(mode="json")},
    )
    if claim.replay is not None:
        return MemberPayment(**claim.replay)

    try:
        result = await _collect_member_contribution(group_id, account_id, payload, session, current_user)
    except Exception:
        idempotency.release(session, claim)
        raise

    idempotency.store(session, claim, result, status_code=201)
    return result


async def _collect_member_contribution(
    group_id: int,
    account_id: int,
    payload: MemberContributionRequest,
    session: Session,
    current_user: User,
) -> MemberPayment:
    account = session.get(Account, account_id)
    if not account or account.group_id != group_id:
        raise HTTPException(status_code=404, detail="Member not found in this group")

    # A member may pay their own way in; anyone else has to be running the group.
    if account.user_id != current_user.id and not _is_platform_admin(current_user):
        _require_group_admin(session, group_id=group_id, user=current_user)

    due = (account.custom_fields or {}).get("initial_contribution_due")
    amount = payload.amount if payload.amount is not None else due
    if amount is None:
        raise HTTPException(status_code=400, detail="No amount given and none is outstanding")

    description = "Initial contribution" if due else "Contribution"

    # Cash handed over at a meeting. Only whoever runs the group may attest to
    # it — a member must not be able to credit their own balance by saying so.
    if payload.method == ContributionMethod.CASH:
        if account.user_id == current_user.id and not _is_platform_admin(current_user):
            _require_group_admin(session, group_id=group_id, user=current_user)
        return _record_cash_contribution(
            session,
            account,
            amount=money(amount),
            reason=payload.cash_reason or "",
            actor=current_user,
            description=f"{description} (cash)",
        )

    payment = await _start_contribution_collection(
        session,
        account,
        amount=money(amount),
        phone_number=payload.phone_number,
        channel=payload.channel,
        description=description,
    )

    # The debt is settled by the payment landing, not by asking for it, so the
    # marker stays until the webhook confirms.
    if payload.phone_number:
        account.custom_fields = {**(account.custom_fields or {}), "phone": payload.phone_number}
        session.add(account)
        session.commit()

    return payment


@router.post("/{group_id}/accept-terms", response_model=MembershipRead)
def accept_terms(
    group_id: int,
    payload: AcceptTermsRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> Membership:
    membership = _get_membership(session, group_id=group_id, user_id=current_user.id)
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")
    if payload.accepted:
        membership.accepted_terms_at = datetime.utcnow()
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return membership


@router.post("/{group_id}/constitution/lock", response_model=GroupSettingsRead)
def lock_constitution(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> GroupSettingsRead:
    if not _is_platform_admin(current_user):
        _require_group_admin(session, group_id=group_id, user=current_user)
    settings = session.get(GroupSettings, group_id)
    if not settings:
        settings = GroupSettings(group_id=group_id)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    if settings.constitution_locked_at is None:
        settings.constitution_locked_at = datetime.utcnow()
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return _settings_read(settings)


@router.get("/{group_id}/contributions", response_model=list[GroupContributionItem])
def group_contributions(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> list[GroupContributionItem]:
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    membership = _get_membership(session, group_id=group_id, user_id=current_user.id)
    if not membership and not _is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="Not a group member")
    if membership and membership.accepted_terms_at is None and not _is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="Accept group terms first")

    contributions = net_contributions_by_account(session, group_id=group_id)
    positive = {account_id: max(money(total), ZERO) for account_id, total in contributions.items()}
    group_total = sum(positive.values())

    accounts = session.exec(select(Account.id, Account.name).where(Account.group_id == group_id)).all()
    names = {int(aid): name for aid, name in accounts}

    items: list[GroupContributionItem] = []
    for account_id, net in contributions.items():
        weight = max(money(net), ZERO)
        share = (weight / group_total * 100) if group_total > ZERO else ZERO
        items.append(
            GroupContributionItem(
                account_id=int(account_id),
                member_name=names.get(int(account_id), f"Account {account_id}"),
                net_contribution=money(net),
                share_percent=share,
            )
        )

    items.sort(key=lambda item: item.net_contribution, reverse=True)
    return items
