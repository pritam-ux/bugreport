import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import Analytics from './pages/Analytics.jsx'
import BugDetail from './pages/BugDetail.jsx'
import Bugs from './pages/Bugs.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Developers from './pages/Developers.jsx'
import Duplicates from './pages/Duplicates.jsx'
import SubmitBug from './pages/SubmitBug.jsx'
import Triage from './pages/Triage.jsx'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
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
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
