import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api/client.js'
import { Logo } from '../components/Layout.jsx'
import { Button, Input, Notice } from '../components/ui.jsx'
import { useAuth } from '../context/AuthContext.jsx'

function AuthShell({ title, description, children, footer }) {
  return (
    <div className="grid min-h-full lg:grid-cols-[1.05fr_1fr]">
      <aside className="sidebar-surface hidden flex-col justify-between p-12 text-white lg:flex">
        <Logo />
        <div className="max-w-md">
          <p className="text-[34px] font-semibold leading-[1.15] tracking-tight">
            Different words.
            <br />
            Same bug.
          </p>
          <div className="mt-8 space-y-2 text-[15px]">
            <p className="rounded-lg bg-white/10 px-4 py-3">Application crashes when I click the login button.</p>
            <div className="ml-6 h-5 w-px bg-[#7f9bff]" aria-hidden />
            <p className="rounded-lg bg-white/10 px-4 py-3">System stops working after pressing the sign-in button.</p>
          </div>
          <p className="mt-6 text-navy-300">
            BugSense compares reports by meaning, suggests who should fix each one, and leaves the final call to your team.
          </p>
        </div>
        <p className="text-sm text-navy-300">Bug triage and duplicate detection</p>
      </aside>
      <main className="flex items-center justify-center bg-white px-4 py-10 sm:px-8">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden"><Logo light={false} /></div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {description && <p className="mt-1 text-ink-soft">{description}</p>}
          <div className="mt-6">{children}</div>
          {footer && <div className="mt-6 text-sm text-ink-soft">{footer}</div>}
        </div>
      </main>
    </div>
  )
}

const LinkText = ({ to, children }) => (
  <Link to={to} className="font-medium text-brand-dark underline-offset-2 hover:underline">{children}</Link>
)

function useSubmit(action) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, submit }
}

export function Login() {
  const { login } = useAuth()
  const [form, setForm] = useState({ email: '', password: '' })
  const { busy, error, submit } = useSubmit(() => login(form.email, form.password))
  return (
    <AuthShell
      title="Sign in"
      description="Pick up where your team left off."
      footer={<>New here? <LinkText to="/register">Create an account</LinkText></>}
    >
      <form onSubmit={submit} className="space-y-4">
        {error && <Notice tone="error">{error}</Notice>}
        <Input label="Email" type="email" autoComplete="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <Input label="Password" type="password" autoComplete="current-password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <div className="text-right text-sm"><LinkText to="/forgot-password">Forgot your password?</LinkText></div>
        <Button type="submit" busy={busy} className="w-full">Sign in</Button>
      </form>
    </AuthShell>
  )
}

export function Register() {
  const { register } = useAuth()
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const { busy, error, submit } = useSubmit(() => register(form))
  return (
    <AuthShell
      title="Create an account"
      description="New accounts can submit and follow bug reports. An administrator can grant more access."
      footer={<>Already have an account? <LinkText to="/login">Sign in</LinkText></>}
    >
      <form onSubmit={submit} className="space-y-4">
        {error && <Notice tone="error">{error}</Notice>}
        <Input label="Name" autoComplete="name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <Input label="Email" type="email" autoComplete="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <Input label="Password" type="password" autoComplete="new-password" required minLength={10} hint="At least 10 characters, with a letter and a number." value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <Button type="submit" busy={busy} className="w-full">Create account</Button>
      </form>
    </AuthShell>
  )
}

export function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [result, setResult] = useState(null)
  const { busy, error, submit } = useSubmit(async () => setResult(await api.post('/auth/forgot-password', { email })))
  return (
    <AuthShell
      title="Reset your password"
      description="Enter your account email to get a reset link."
      footer={<LinkText to="/login">Back to sign in</LinkText>}
    >
      {result ? (
        <div className="space-y-4">
          <Notice tone="success">{result.message}</Notice>
          {result.development_reset_token && (
            <Notice tone="warning" title="Development mode: email isn't set up">
              Use this link instead of an email.{' '}
              <LinkText to={`/reset-password?token=${encodeURIComponent(result.development_reset_token)}`}>Open reset page</LinkText>
            </Notice>
          )}
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          {error && <Notice tone="error">{error}</Notice>}
          <Input label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Button type="submit" busy={busy} className="w-full">Send reset link</Button>
        </form>
      )}
    </AuthShell>
  )
}

export function ResetPassword() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [done, setDone] = useState(false)
  const token = params.get('token') || ''
  const { busy, error, submit } = useSubmit(async () => {
    await api.post('/auth/reset-password', { token, password })
    setDone(true)
  })
  return (
    <AuthShell title="Choose a new password" description="This signs you out of your other sessions.">
      {done ? (
        <div className="space-y-4">
          <Notice tone="success">Password updated.</Notice>
          <Button className="w-full" onClick={() => navigate('/login')}>Go to sign in</Button>
        </div>
      ) : !token ? (
        <Notice tone="error">
          This page needs a reset link. <LinkText to="/forgot-password">Request a new one</LinkText>
        </Notice>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          {error && <Notice tone="error">{error}</Notice>}
          <Input label="New password" type="password" autoComplete="new-password" required minLength={10} hint="At least 10 characters, with a letter and a number." value={password} onChange={(e) => setPassword(e.target.value)} />
          <Button type="submit" busy={busy} className="w-full">Update password</Button>
        </form>
      )}
    </AuthShell>
  )
}
