import { Navigate, Route, Routes } from 'react-router-dom'
import { IdentityProvider, useIdentity } from './context/IdentityContext'
import { IdentityGate } from './pages/IdentityGate'
import { AppShell } from './components/AppShell'
import { PredictPage } from './pages/PredictPage'
import { DashboardPage } from './pages/DashboardPage'
import { PendingPage } from './pages/PendingPage'

function Gated() {
  const { name } = useIdentity()
  if (!name) return <IdentityGate />

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/predict" element={<PredictPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/pending" element={<PendingPage />} />
        <Route path="*" element={<Navigate to="/predict" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <IdentityProvider>
      <Gated />
    </IdentityProvider>
  )
}
