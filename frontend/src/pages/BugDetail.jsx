import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ClipboardCheck, CopyCheck, Download, Paperclip, Pencil, Trash2 } from 'lucide-react'
import { api, useApi } from '../api/client.js'
import {
  Button, COMPONENTS, Card, Input, Modal, Notice, PRIORITIES, PriorityBadge, SEVERITIES, STATUSES, Select, SeverityBadge, Spinner,
  StatusBadge, Textarea, formatDate,
} from '../components/ui.jsx'
import { useAuth } from '../context/AuthContext.jsx'

function Section({ title, children, mono }) {
  if (!children) return null
  return (
    <div>
      <h3 className="mb-1 text-sm font-semibold">{title}</h3>
      {mono ? (
        <pre className="overflow-x-auto rounded-lg bg-navy-950 p-3 text-xs leading-relaxed text-navy-300">{children}</pre>
      ) : (
        <p className="whitespace-pre-line break-words text-sm text-ink-soft">{children}</p>
      )}
    </div>
  )
}

function EditModal({ bug, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: bug.title,
    description: bug.description,
    steps_to_reproduce: bug.steps_to_reproduce || '',
    expected_behavior: bug.expected_behavior || '',
    actual_behavior: bug.actual_behavior || '',
    stack_trace: bug.stack_trace || '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value })
  const save = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onSaved(await api.put(`/bugs/${bug.bug_id}`, form))
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }
  return (
    <Modal open wide onClose={onClose} title={`Edit ${bug.bug_id}`}>
      <form onSubmit={save} className="space-y-4">
        <Input label="Title" required minLength={5} maxLength={200} value={form.title} onChange={set('title')} />
        <Textarea label="Description" required minLength={10} rows={4} value={form.description} onChange={set('description')} />
        <Textarea label="Steps to reproduce" rows={3} value={form.steps_to_reproduce} onChange={set('steps_to_reproduce')} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Textarea label="Expected behavior" rows={2} value={form.expected_behavior} onChange={set('expected_behavior')} />
          <Textarea label="Actual behavior" rows={2} value={form.actual_behavior} onChange={set('actual_behavior')} />
        </div>
        <Textarea label="Stack trace or error logs" mono rows={4} value={form.stack_trace} onChange={set('stack_trace')} />
        <p className="text-xs text-ink-muted">Saving recalculates this report's embedding, so future duplicate checks use the new text.</p>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" busy={busy}>Save changes</Button>
        </div>
      </form>
    </Modal>
  )
}

function ManagePanel({ bug, developers, onChange }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const update = async (changes) => {
    setBusy(true)
    setError(null)
    try {
      onChange(await api.put(`/bugs/${bug.bug_id}`, changes))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  const statuses = bug.status === 'Duplicate' ? STATUSES : STATUSES.filter((s) => s !== 'Duplicate')
  return (
    <Card title="Manage">
      <fieldset disabled={busy} className="space-y-3">
        <Select label="Status" options={statuses} value={bug.status} onChange={(e) => update({ status: e.target.value })} />
        <Select
          label="Assigned developer"
          placeholder="Unassigned"
          options={(developers || []).map((d) => ({ value: d.developer_id, label: d.name }))}
          value={bug.assigned_developer || ''}
          onChange={(e) => update({ assigned_developer: e.target.value || null })}
        />
        <Select label="Priority" options={PRIORITIES} value={bug.priority} onChange={(e) => update({ priority: e.target.value })} />
        <Select label="Severity" options={SEVERITIES} value={bug.severity} onChange={(e) => update({ severity: e.target.value })} />
        <Select label="Component" options={COMPONENTS} value={bug.component} onChange={(e) => update({ component: e.target.value })} />
      </fieldset>
      {error && <div className="mt-3"><Notice tone="error">{error}</Notice></div>}
    </Card>
  )
}

function Attachments({ bug, canUpload, onUploaded }) {
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const upload = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const data = new FormData()
      data.append('file', file)
      await api.post(`/bugs/${bug.bug_id}/attachments`, data)
      onUploaded()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  const download = async (attachment) => {
    setError(null)
    try {
      const blob = await api.blob(`/bugs/${bug.bug_id}/attachments/${attachment.attachment_id}`)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = attachment.filename
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    }
  }
  return (
    <Card title="Attachments">
      {!bug.attachments?.length && <p className="text-sm text-ink-muted">No files attached.</p>}
      <ul className="space-y-1">
        {bug.attachments?.map((attachment) => (
          <li key={attachment.attachment_id}>
            <button type="button" onClick={() => download(attachment)} className="flex w-full items-center gap-2 rounded px-1 py-1 text-left text-sm hover:bg-page">
              <Download size={14} className="shrink-0 text-ink-muted" aria-hidden />
              <span className="truncate">{attachment.filename}</span>
              <span className="ml-auto shrink-0 text-xs text-ink-muted">{Math.max(1, Math.round(attachment.size / 1024))} KB</span>
            </button>
          </li>
        ))}
      </ul>
      {canUpload && (
        <label className="mt-3 flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-line px-3 py-3 text-sm font-medium text-ink-soft focus-within:ring-2 focus-within:ring-brand hover:border-brand/50">
          <Paperclip size={15} aria-hidden /> {busy ? 'Uploading' : 'Add a file'}
          <input type="file" accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.log" disabled={busy} className="sr-only" onChange={upload} />
        </label>
      )}
      {error && <div className="mt-2"><Notice tone="error">{error}</Notice></div>}
    </Card>
  )
}

export default function BugDetail() {
  const { bugId } = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()
  const { data: bug, error, loading, reload, setData } = useApi(`/bugs/${bugId}`)
  const { data: developers } = useApi('/developers')
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleteError, setDeleteError] = useState(null)
  const [deleting, setDeleting] = useState(false)

  if (loading && !bug) return <Spinner label="Loading the report" />
  if (error && !bug) return <Notice tone="error" onRetry={reload}>{error}</Notice>

  const isStaff = user.role !== 'Reporter'
  const isOwner = bug.reporter_id === user.user_id
  const environment = bug.environment || {}

  const remove = async () => {
    setDeleting(true)
    try {
      await api.delete(`/bugs/${bug.bug_id}`)
      navigate('/bugs', { replace: true })
    } catch (err) {
      setDeleteError(err.message)
      setDeleting(false)
    }
  }

  return (
    <>
      <Link to="/bugs" className="mb-3 inline-flex items-center gap-1 text-sm font-medium text-ink-soft hover:text-ink">
        <ArrowLeft size={15} aria-hidden /> All bugs
      </Link>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm text-ink-muted">{bug.bug_id}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{bug.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusBadge value={bug.status} />
            <PriorityBadge value={bug.priority} />
            <SeverityBadge value={bug.severity} />
            <span className="text-sm text-ink-soft">{bug.component}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to={`/duplicates/${bug.bug_id}`}><Button variant="secondary" icon={CopyCheck}>Check duplicates</Button></Link>
          <Link to={`/triage/${bug.bug_id}`}><Button variant="secondary" icon={ClipboardCheck}>View triage</Button></Link>
          {(isStaff || isOwner) && <Button variant="secondary" icon={Pencil} onClick={() => setEditing(true)}>Edit</Button>}
          {user.role === 'Admin' && <Button variant="danger" icon={Trash2} onClick={() => setConfirmDelete(true)}>Delete</Button>}
        </div>
      </div>

      {bug.duplicate_of && (
        <div className="mb-4">
          <Notice tone="info" title={`Duplicate of ${bug.duplicate_of}`}>
            <Link to={`/bugs/${bug.duplicate_of}`} className="font-medium underline">Open the original report</Link>
          </Notice>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2">
          <Card>
            <div className="space-y-5">
              <Section title="Description">{bug.description}</Section>
              <Section title="Steps to reproduce">{bug.steps_to_reproduce}</Section>
              <Section title="Expected behavior">{bug.expected_behavior}</Section>
              <Section title="Actual behavior">{bug.actual_behavior}</Section>
              <Section title="Stack trace or error logs" mono>{bug.stack_trace}</Section>
            </div>
          </Card>
        </div>
        <div className="min-w-0 space-y-4">
          {isStaff && <ManagePanel bug={bug} developers={developers} onChange={setData} />}
          <Card title="Details">
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
              {[
                ['Submitted by', bug.reporter_name],
                ['Submitted', formatDate(bug.created_at)],
                ['Resolved', bug.resolved_at ? formatDate(bug.resolved_at) : 'Not yet'],
                ['Assigned to', bug.assigned_developer_name || 'Unassigned'],
                ['Suggested developer', bug.recommended_developer_name || 'None'],
                ['Operating system', environment.os || 'Not given'],
                ['Browser', environment.browser || 'Not given'],
                ['App version', environment.app_version || 'Not given'],
                ['AI predicted', [bug.predicted_component, bug.predicted_priority, bug.predicted_severity].filter(Boolean).join(', ') || 'None'],
              ].map(([term, value]) => (
                <div key={term} className="contents">
                  <dt className="text-ink-muted">{term}</dt>
                  <dd className="min-w-0 break-words text-right">{value}</dd>
                </div>
              ))}
            </dl>
          </Card>
          <Attachments bug={bug} canUpload={isStaff || isOwner} onUploaded={reload} />
        </div>
      </div>

      {editing && (
        <EditModal
          bug={bug}
          onClose={() => setEditing(false)}
          onSaved={(saved) => {
            setData(saved)
            setEditing(false)
          }}
        />
      )}
      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title={`Delete ${bug.bug_id}?`}>
        <p className="text-sm text-ink-soft">
          This permanently removes the report, its attachments and its duplicate matches. Reports marked as duplicates of it will reopen.
        </p>
        {deleteError && <div className="mt-3"><Notice tone="error">{deleteError}</Notice></div>}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setConfirmDelete(false)}>Keep report</Button>
          <Button variant="danger" busy={deleting} onClick={remove}>Delete report</Button>
        </div>
      </Modal>
    </>
  )
}
