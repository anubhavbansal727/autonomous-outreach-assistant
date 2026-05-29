import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { Zap, History, Settings, LogOut, Building2 } from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/', label: 'Onboarding', icon: Building2 },
  { to: '/generate', label: 'Generate', icon: Zap },
  { to: '/history', label: 'History', icon: History },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <aside className="w-56 min-h-screen border-r bg-card flex flex-col">
      <div className="p-4 border-b">
        <h1 className="font-bold text-lg text-primary">AI Outreach</h1>
        <p className="text-xs text-muted-foreground truncate mt-0.5">{user?.email}</p>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === '/'}
            className={({ isActive }) => cn('flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
              isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
            )}>
            <Icon className="h-4 w-4" />{label}
          </NavLink>
        ))}
      </nav>
      <div className="p-3 border-t">
        <button onClick={handleLogout} className="flex items-center gap-3 px-3 py-2 w-full rounded-md text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors">
          <LogOut className="h-4 w-4" />Logout
        </button>
      </div>
    </aside>
  )
}
