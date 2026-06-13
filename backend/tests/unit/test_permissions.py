"""Unit tests for the RBAC permission matrix and require_permission gating."""
from __future__ import annotations

import pytest

from app.auth.permissions import (
    Permission,
    Role,
    ROLE_PERMISSIONS,
    has_permission,
    permissions_for,
)


class TestRolePermissionMatrix:
    def test_every_role_has_an_entry(self):
        assert set(ROLE_PERMISSIONS.keys()) == set(Role)

    def test_owner_has_all_permissions(self):
        assert ROLE_PERMISSIONS[Role.OWNER] == frozenset(Permission)

    def test_permissions_are_strictly_nested_owner_to_viewer(self):
        # Each lower role's permissions are a subset of the next role up.
        assert ROLE_PERMISSIONS[Role.VIEWER] <= ROLE_PERMISSIONS[Role.MEMBER]
        assert ROLE_PERMISSIONS[Role.MEMBER] <= ROLE_PERMISSIONS[Role.ADMIN]
        assert ROLE_PERMISSIONS[Role.ADMIN] <= ROLE_PERMISSIONS[Role.OWNER]

    def test_only_owner_can_manage_tenant(self):
        for role in Role:
            assert has_permission(role, Permission.TENANT_MANAGE) == (role == Role.OWNER)

    def test_member_management_is_admin_and_owner_only(self):
        assert has_permission(Role.OWNER, Permission.MEMBERS_MANAGE)
        assert has_permission(Role.ADMIN, Permission.MEMBERS_MANAGE)
        assert not has_permission(Role.MEMBER, Permission.MEMBERS_MANAGE)
        assert not has_permission(Role.VIEWER, Permission.MEMBERS_MANAGE)

    def test_viewer_cannot_create_or_send_outreach(self):
        assert not has_permission(Role.VIEWER, Permission.OUTREACH_CREATE)
        assert not has_permission(Role.VIEWER, Permission.OUTREACH_SEND)

    def test_member_cannot_view_all_outreach(self):
        assert not has_permission(Role.MEMBER, Permission.OUTREACH_VIEW_ALL)
        assert has_permission(Role.ADMIN, Permission.OUTREACH_VIEW_ALL)

    def test_profile_edit_requires_admin_or_owner(self):
        assert has_permission(Role.ADMIN, Permission.PROFILE_EDIT)
        assert not has_permission(Role.MEMBER, Permission.PROFILE_EDIT)
        # everyone can at least view the shared profile
        for role in Role:
            assert has_permission(role, Permission.PROFILE_VIEW)


class TestHelpers:
    def test_permissions_for_accepts_raw_string(self):
        assert permissions_for("owner") == permissions_for(Role.OWNER)

    def test_permissions_for_returns_sorted_strings(self):
        perms = permissions_for(Role.ADMIN)
        assert perms == sorted(perms)
        assert all(isinstance(p, str) for p in perms)

    def test_unknown_role_yields_no_permissions(self):
        assert permissions_for("superuser") == []
        assert has_permission("superuser", Permission.PROFILE_VIEW) is False

    def test_unknown_permission_is_false(self):
        assert has_permission(Role.OWNER, "galaxy.destroy") is False


class TestRequirePermission:
    """The require_permission factory gates on the caller's resolved permissions."""

    def _ctx(self, role):
        from app.auth.dependencies import RequestContext

        return RequestContext(
            user=object(),
            tenant_id="t",
            role=role,
            permissions=permissions_for(role),
        )

    @pytest.mark.asyncio
    async def test_allows_when_permission_granted(self):
        from app.auth.dependencies import require_permission

        checker = require_permission(Permission.MEMBERS_MANAGE)
        ctx = self._ctx("admin")
        assert await checker(ctx=ctx) is ctx

    @pytest.mark.asyncio
    async def test_403_when_permission_missing(self):
        from fastapi import HTTPException

        from app.auth.dependencies import require_permission

        checker = require_permission(Permission.MEMBERS_MANAGE)
        with pytest.raises(HTTPException) as exc_info:
            await checker(ctx=self._ctx("member"))
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "PERMISSION_DENIED"
        assert exc_info.value.detail["required_permission"] == "members.manage"
