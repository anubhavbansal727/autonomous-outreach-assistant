import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '@/contexts/AuthContext'
import { AppShell } from '@/components/layout/AppShell'
import { RequirePermission } from '@/components/RequirePermission'
import { PERMISSIONS } from '@/lib/permissions'
import { LoginPage } from '@/pages/LoginPage'
import { RegisterPage } from '@/pages/RegisterPage'
import { ChangePasswordPage } from '@/pages/ChangePasswordPage'
import { OnboardingPage } from '@/pages/OnboardingPage'
import { GeneratePage } from '@/pages/GeneratePage'
import { BatchPage } from '@/pages/BatchPage'
import { ResultPage } from '@/pages/ResultPage'
import { HistoryPage } from '@/pages/HistoryPage'
import { TeamPage } from '@/pages/TeamPage'
import { SettingsPage } from '@/pages/SettingsPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/change-password" element={<ChangePasswordPage />} />
            <Route element={<AppShell />}>
              <Route path="/" element={<OnboardingPage />} />
              <Route path="/generate" element={<RequirePermission permission={PERMISSIONS.OUTREACH_CREATE}><GeneratePage /></RequirePermission>} />
              <Route path="/batch" element={<RequirePermission permission={PERMISSIONS.OUTREACH_CREATE}><BatchPage /></RequirePermission>} />
              <Route path="/result/:jobId" element={<ResultPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/team" element={<RequirePermission permission={PERMISSIONS.MEMBERS_MANAGE}><TeamPage /></RequirePermission>} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
