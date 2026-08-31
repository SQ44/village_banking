"""Who can see what.

Two independent things in this system were both called "admin", and the overlap
hid a real question: whether someone who runs one savings group can read the
books of every other one.

*   **Platform roles** live on `User.role` and say what someone is to the
    installation: a system administrator or operator who runs the service, or an
    ordinary person who belongs to a group.

*   **Group roles** live on `Membership.role` and say what someone is inside one
    particular group — its admin, or one of its members.

A group administrator is the pairing of an ordinary platform role with
`MembershipRole.ADMIN` on a single group. They run their group completely: they
invite members, set the constitution, and see every loan in it. What they cannot
do is reach past its edge. Every group-scoped endpoint answers a platform admin
directly and sends everyone else through a membership lookup, so a group admin
asking about a group they do not belong to gets the same 403 a stranger does.

The distinction is kept here, in one place, because it is a security boundary:
nine copies of `role in {"admin", "operator"}` is nine chances for one of them
to drift.
"""

from __future__ import annotations

from typing import Any

#: Runs the installation. Not scoped to any one group, and the only role that
#: may create groups or read a group it does not belong to.
PLATFORM_ADMIN_ROLES = frozenset({"admin", "operator"})

#: Runs one group. Reaches the admin console, but only ever for the groups this
#: user is actually a member of.
GROUP_ADMIN_ROLE = "group_admin"

#: Belongs to a group, and uses the member console.
MEMBER_ROLE = "member"

#: Roles that land in the admin console rather than the member one.
ADMIN_CONSOLE_ROLES = frozenset(PLATFORM_ADMIN_ROLES | {GROUP_ADMIN_ROLE})


def _role_of(subject: Any) -> str:
    """Accept either a user or a bare role string.

    Call sites grew up passing both, and a helper that quietly returned False
    for the wrong shape would fail open on a security check.
    """
    if isinstance(subject, str):
        return subject
    return getattr(subject, "role", "") or ""


def is_platform_admin(subject: Any) -> bool:
    """True for a system administrator or operator, and for nobody else.

    In particular this is False for a group administrator: their reach is
    decided by membership, never by their role alone.
    """
    return _role_of(subject) in PLATFORM_ADMIN_ROLES


def is_group_admin(subject: Any) -> bool:
    return _role_of(subject) == GROUP_ADMIN_ROLE


def uses_admin_console(subject: Any) -> bool:
    return _role_of(subject) in ADMIN_CONSOLE_ROLES
