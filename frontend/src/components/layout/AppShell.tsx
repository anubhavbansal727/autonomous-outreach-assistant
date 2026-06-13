import { Outlet, Navigate } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { useAuth } from '@/contexts/AuthContext'

export function AppShell() {
  const { accessToken, user } = useAuth()
  if (!accessToken) return <Navigate to="/login" replace />
  // Admin-created members must set their own password before using the app.
  if (user?.must_change_password) return <Navigate to="/change-password" replace />
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 min-w-0 overflow-y-auto p-4 sm:p-8">
        <Outlet />
      </main>
    </div>
  )
}
