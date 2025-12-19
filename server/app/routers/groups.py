from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import create_user, get_current_active_user
from ..database import get_session
from ..group_finance import net_contributions_by_account
from ..models import Account, Group, GroupSettings, Membership, MembershipRole, Transaction, TransactionStatus, TransactionType, User
from ..schemas import (
    AcceptTermsRequest,
    AccountRead,
    GroupContributionItem,
    GroupCreate,
    GroupRead,
    GroupSettingsRead,
    GroupSettingsUpdate,
    GroupWithSettings,
    MemberInvite,
    MembershipRead,
    UserCreate,
)

router = APIRouter(prefix="/groups", tags=["Groups"])


def _is_platform_admin(user: User) -> bool:
    return user.role in {"admin", "operator"}


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


@router.post("/{group_id}/members", response_model=MembershipRead, status_code=201)
def add_group_member(
    group_id: int,
    payload: MemberInvite,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
) -> Membership:
    if not _is_platform_admin(current_user):
        _require_group_admin(session, group_id=group_id, user=current_user)

    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    existing = session.exec(select(User).where(User.email == payload.email.lower())).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    user = create_user(
        session,
        UserCreate(
            email=payload.email,
            full_name=payload.full_name,
            role="member",
            password=payload.password,
        ),
    )

    account = Account(
        name=payload.name,
        email=payload.email,
        group_id=group_id,
        group_name=group.name,
        user_id=user.id,
        balance=0,
        custom_fields=payload.custom_fields,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(account)
    session.commit()
    session.refresh(account)

    if payload.min_initial_deposit and payload.min_initial_deposit > 0:
        tx = Transaction(
            account_id=account.id,
            amount=payload.min_initial_deposit,
            type=TransactionType.DEPOSIT,
            status=TransactionStatus.COMPLETED,
            description="Initial contribution",
            custom_fields={"months_covered": 1},
            created_at=datetime.utcnow(),
        )
        account.balance += payload.min_initial_deposit
        account.updated_at = datetime.utcnow()
        session.add(tx)
        session.add(account)
        session.commit()
        session.refresh(account)

    membership = Membership(group_id=group_id, user_id=user.id, account_id=account.id, role=MembershipRole.MEMBER)
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return membership


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
    positive = {account_id: max(float(total), 0.0) for account_id, total in contributions.items()}
    group_total = sum(positive.values())

    accounts = session.exec(select(Account.id, Account.name).where(Account.group_id == group_id)).all()
    names = {int(aid): name for aid, name in accounts}

    items: list[GroupContributionItem] = []
    for account_id, net in contributions.items():
        weight = max(float(net), 0.0)
        share = round((weight / group_total) * 100.0, 2) if group_total > 0 else 0.0
        items.append(
            GroupContributionItem(
                account_id=int(account_id),
                member_name=names.get(int(account_id), f"Account {account_id}"),
                net_contribution=round(float(net), 2),
                share_percent=share,
            )
        )

    items.sort(key=lambda item: item.net_contribution, reverse=True)
    return items
