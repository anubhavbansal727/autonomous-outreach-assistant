import { Outlet, Navigate } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { useAuth } from '@/contexts/AuthContext'

export function AppShell() {
  const { accessToken } = useAuth()
  if (!accessToken) return <Navigate to="/login" replace />
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 min-w-0 overflow-y-auto p-4 sm:p-8">
        <Outlet />
      </main>
    </div>
  )
}
