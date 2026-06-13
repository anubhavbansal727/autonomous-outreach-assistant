import { useAuth } from '@/contexts/AuthContext'
import type { Permission } from '@/lib/permissions'

/**
 * Route-level UI guard. Renders children only if the user holds `permission`,
 * otherwise a friendly message. This is convenience only — the server enforces
 * the real check on every request.
 */
export function RequirePermission({ permission, children }: { permission: Permission; children: React.ReactNode }) {
  const { can } = useAuth()
  if (!can(permission)) {
    return (
      <div className="max-w-xl">
        <p className="text-muted-foreground">You don't have permission to view this page. Ask a workspace admin for access.</p>
      </div>
    )
  }
  return <>{children}</>
}
