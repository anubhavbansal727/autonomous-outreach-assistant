import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { PERMISSIONS } from '@/lib/permissions'
import { Zap, History, Settings, LogOut, Building2, Layers, Users } from 'lucide-react'
import { cn } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
  icon: typeof Zap
  permission?: string  // when set, only shown if the user holds it
}

const navItems: NavItem[] = [
  { to: '/', label: 'Onboarding', icon: Building2 },
  { to: '/generate', label: 'Generate', icon: Zap, permission: PERMISSIONS.OUTREACH_CREATE },
  { to: '/batch', label: 'Batch', icon: Layers, permission: PERMISSIONS.OUTREACH_CREATE },
  { to: '/history', label: 'History', icon: History },
  { to: '/team', label: 'Team', icon: Users, permission: PERMISSIONS.MEMBERS_MANAGE },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => { logout(); navigate('/login') }

  const items = navItems.filter(
    item => !item.permission || user?.permissions?.includes(item.permission),
  )

  return (
    <aside className="w-16 md:w-56 shrink-0 h-full border-r bg-card flex flex-col">
      <div className="p-4 border-b">
        <h1 className="font-bold text-lg text-primary hidden md:block">AI Outreach</h1>
        <Zap className="h-5 w-5 mx-auto text-primary md:hidden" aria-label="AI Outreach" />
        <p className="text-xs text-muted-foreground truncate mt-0.5 hidden md:block">{user?.tenant?.name ?? user?.email}</p>
        {user?.role && (
          <span className="hidden md:inline-block mt-1 text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-accent text-accent-foreground capitalize">{user.role}</span>
        )}
      </div>
      <nav className="flex-1 overflow-y-auto p-3 space-y-1">
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === '/'} title={label}
            className={({ isActive }) => cn('flex items-center justify-center md:justify-start gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
              isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
            )}>
            <Icon className="h-4 w-4 shrink-0" /><span className="hidden md:inline">{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="p-3 border-t">
        <button onClick={handleLogout} title="Logout" className="flex items-center justify-center md:justify-start gap-3 px-3 py-2 w-full rounded-md text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors">
          <LogOut className="h-4 w-4 shrink-0" /><span className="hidden md:inline">Logout</span>
        </button>
      </div>
    </aside>
  )
}
