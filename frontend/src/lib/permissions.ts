/**
 * permissions.ts — mirror of the backend RBAC permission keys.
 *
 * The SERVER is authoritative: every gated endpoint re-checks permissions. These
 * constants and `can()` exist ONLY to show/hide UI (buttons, nav, pages). Never
 * rely on them for security — a hidden button is a convenience, not a control.
 *
 * The string values must stay in sync with app/auth/permissions.py.
 */

export const PERMISSIONS = {
  TENANT_MANAGE: 'tenant.manage',
  MEMBERS_VIEW: 'members.view',
  MEMBERS_MANAGE: 'members.manage',
  PROFILE_VIEW: 'profile.view',
  PROFILE_EDIT: 'profile.edit',
  OUTREACH_CREATE: 'outreach.create',
  OUTREACH_SEND: 'outreach.send',
  OUTREACH_VIEW_OWN: 'outreach.view.own',
  OUTREACH_VIEW_ALL: 'outreach.view.all',
  AUDIT_VIEW: 'audit.view',
} as const

export type Permission = (typeof PERMISSIONS)[keyof typeof PERMISSIONS]

/** True if the resolved permission list grants `permission`. */
export function can(permissions: string[] | undefined, permission: Permission): boolean {
  return !!permissions?.includes(permission)
}
