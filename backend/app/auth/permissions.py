"""auth/permissions.py — the single source of truth for RBAC.

In plain English:
- A TENANT is a company workspace. Every member of a tenant has exactly one
  ROLE: owner, admin, member, or viewer.
- A PERMISSION is a fine-grained capability (e.g. "send outreach", "manage
  members"). Roles don't grant access directly — they map to a fixed SET of
  permissions, defined once in ``ROLE_PERMISSIONS`` below.
- Endpoints check permissions, never roles, via require_permission() in
  app/auth/dependencies.py. To change who-can-do-what, edit the matrix here and
  nothing else — that is the whole point of keeping it in one place.

This is authoritative on the SERVER. The frontend receives the resolved
permission list (from /auth/me) only to show/hide buttons; it never enforces.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """The fixed set of roles a membership can hold (v3 — no custom roles)."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Permission(str, Enum):
    """Fine-grained capabilities. Endpoints gate on these, not on roles."""

    # Tenant-level administration (rename, sending domain, delete tenant).
    TENANT_MANAGE = "tenant.manage"
    # See the member roster.
    MEMBERS_VIEW = "members.view"
    # Create / suspend / change roles of members.
    MEMBERS_MANAGE = "members.manage"
    # Read the shared product profiles.
    PROFILE_VIEW = "profile.view"
    # Ingest / save / update / activate product profiles.
    PROFILE_EDIT = "profile.edit"
    # Generate, batch, retry outreach.
    OUTREACH_CREATE = "outreach.create"
    # Approve & send outreach.
    OUTREACH_SEND = "outreach.send"
    # See one's own outreach jobs / history.
    OUTREACH_VIEW_OWN = "outreach.view.own"
    # See ALL members' outreach in the tenant (admin oversight, read-only).
    OUTREACH_VIEW_ALL = "outreach.view.all"
    # Read the tenant audit log.
    AUDIT_VIEW = "audit.view"


# ---------------------------------------------------------------------------
# Role → permission matrix (mirror of the table in prd_mini_crm_ai_crew_v3.md)
# ---------------------------------------------------------------------------

_VIEWER_PERMS: frozenset[Permission] = frozenset(
    {
        Permission.MEMBERS_VIEW,
        Permission.PROFILE_VIEW,
        Permission.OUTREACH_VIEW_OWN,
    }
)

# Members can do everything a viewer can, plus create and send their own outreach.
_MEMBER_PERMS: frozenset[Permission] = _VIEWER_PERMS | {
    Permission.OUTREACH_CREATE,
    Permission.OUTREACH_SEND,
}

# Admins add member management, profile editing, audit and cross-member view.
_ADMIN_PERMS: frozenset[Permission] = _MEMBER_PERMS | {
    Permission.MEMBERS_MANAGE,
    Permission.PROFILE_EDIT,
    Permission.OUTREACH_VIEW_ALL,
    Permission.AUDIT_VIEW,
}

# Owners have every permission, including tenant-level administration.
_OWNER_PERMS: frozenset[Permission] = _ADMIN_PERMS | {
    Permission.TENANT_MANAGE,
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: _OWNER_PERMS,
    Role.ADMIN: _ADMIN_PERMS,
    Role.MEMBER: _MEMBER_PERMS,
    Role.VIEWER: _VIEWER_PERMS,
}


def permissions_for(role: Role | str) -> list[str]:
    """Return the sorted permission-string list granted to a role.

    Accepts either a Role or its raw string value (as stored on a Membership).
    Unknown roles get no permissions.
    """
    try:
        key = Role(role)
    except ValueError:
        return []
    return sorted(p.value for p in ROLE_PERMISSIONS[key])


def has_permission(role: Role | str, permission: Permission | str) -> bool:
    """True if ``role`` grants ``permission``."""
    try:
        key = Role(role)
        perm = Permission(permission)
    except ValueError:
        return False
    return perm in ROLE_PERMISSIONS[key]
