import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import { EmptyState, Spinner } from './components/ui.jsx'
import { useAuth } from './context/AuthContext.jsx'
import Analytics from './pages/Analytics.jsx'
import { ForgotPassword, Login, Register, ResetPassword } from './pages/Auth.jsx'
import BugDetail from './pages/BugDetail.jsx'
import Bugs from './pages/Bugs.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Developers from './pages/Developers.jsx'
import Duplicates from './pages/Duplicates.jsx'
import SubmitBug from './pages/SubmitBug.jsx'
import Triage from './pages/Triage.jsx'
import UsersPage from './pages/Users.jsx'

function Protected({ roles, children }) {
  const { user, checking } = useAuth()
  const location = useLocation()
  if (checking) return <Spinner label="Checking your session" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (roles && !roles.includes(user.role)) {
    return <EmptyState title="You don't have access to this page">Ask an administrator if you need it.</EmptyState>
  }
  return children
}

function GuestOnly({ children }) {
  const { user, checking } = useAuth()
  const location = useLocation()
  if (checking) return <Spinner label="Checking your session" />
  if (user) return <Navigate to={location.state?.from || '/'} replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
      <Route path="/register" element={<GuestOnly><Register /></GuestOnly>} />
      <Route path="/forgot-password" element={<GuestOnly><ForgotPassword /></GuestOnly>} />
      <Route path="/reset-password" element={<GuestOnly><ResetPassword /></GuestOnly>} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route index element={<Dashboard />} />
        <Route path="submit" element={<SubmitBug />} />
        <Route path="bugs" element={<Bugs />} />
        <Route path="bugs/:bugId" element={<BugDetail />} />
        <Route path="duplicates" element={<Duplicates />} />
        <Route path="duplicates/:bugId" element={<Duplicates />} />
        <Route path="triage" element={<Triage />} />
        <Route path="triage/:bugId" element={<Triage />} />
        <Route path="developers" element={<Developers />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="users" element={<Protected roles={['Admin']}><UsersPage /></Protected>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
