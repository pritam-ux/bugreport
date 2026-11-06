import { useState } from 'react'
import { Link } from 'react-router-dom'
import { UserPlus } from 'lucide-react'
import { api, useApi } from '../api/client.js'
import { Button, COMPONENTS, Card, EmptyState, Input, Meter, Modal, Notice, PageHeader, PriorityBadge, Spinner, StatusBadge } from '../components/ui.jsx'
import { useAuth } from '../context/AuthContext.jsx'

function AddDeveloper({ onClose, onSaved }) {
  const [form, setForm] = useState({ name: '', email: '', skills: '', assigned_components: [] })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const toggle = (component) => {
    const chosen = form.assigned_components
    setForm({
      ...form,
      assigned_components: chosen.includes(component) ? chosen.filter((c) => c !== component) : [...chosen, component],
    })
  }
  const save = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onSaved(await api.post('/developers', { ...form, skills: form.skills.split(',').map((s) => s.trim()).filter(Boolean) }))
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }
  return (
    <Modal open onClose={onClose} title="Add a developer">
      <form onSubmit={save} className="space-y-4">
        <Input label="Name" required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <Input label="Email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <Input label="Skills" hint="Separate skills with commas. The recommender matches them against report text." placeholder="react, css, accessibility" value={form.skills} onChange={(e) => setForm({ ...form, skills: e.target.value })} />
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">Components</legend>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5">
            {COMPONENTS.map((component) => (
              <label key={component} className="flex items-center gap-1.5 text-sm">
                <input type="checkbox" checked={form.assigned_components.includes(component)} onChange={() => toggle(component)} />
                {component}
              </label>
            ))}
          </div>
        </fieldset>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" busy={busy}>Add developer</Button>
        </div>
      </form>
    </Modal>
  )
}

function DeveloperDetail({ id, onClose }) {
  const { data, error, loading } = useApi(`/developers/${id}`)
  return (
    <Modal open wide onClose={onClose} title={data ? `${data.name}, ${data.developer_id}` : 'Developer'}>
      {loading && !data && <Spinner />}
      {error && <Notice tone="error">{error}</Notice>}
      {data && (
        <div className="space-y-4 text-sm">
          <p className="text-ink-soft">{data.email}</p>
          <div>
            <h3 className="mb-1 font-semibold">Resolved bugs by component</h3>
            {Object.keys(data.resolved_by_component).length === 0 ? (
              <p className="text-ink-muted">No resolved bugs yet.</p>
            ) : (
              <p className="text-ink-soft">{Object.entries(data.resolved_by_component).sort((a, b) => b[1] - a[1]).map(([name, count]) => `${name}: ${count}`).join(', ')}</p>
            )}
          </div>
          <div>
            <h3 className="mb-1 font-semibold">Active bugs ({data.active_bugs.length})</h3>
            {data.active_bugs.length === 0 && <p className="text-ink-muted">Nothing assigned right now.</p>}
            <ul className="divide-y divide-line">
              {data.active_bugs.map((bug) => (
                <li key={bug.bug_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <Link to={`/bugs/${bug.bug_id}`} className="min-w-0 font-medium hover:text-brand-dark">{bug.bug_id}: {bug.title}</Link>
                  <span className="flex gap-1.5"><StatusBadge value={bug.status} /><PriorityBadge value={bug.priority} /></span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Modal>
  )
}

export default function Developers() {
  const { user } = useAuth()
  const { data, error, loading, reload } = useApi('/developers')
  const [adding, setAdding] = useState(false)
  const [viewing, setViewing] = useState(null)

  return (
    <>
      <PageHeader
        title="Developers"
        description="Expertise and workload here feed the developer recommendations."
        action={user.role === 'Admin' && <Button icon={UserPlus} onClick={() => setAdding(true)}>Add a developer</Button>}
      />
      {error && !data && <Notice tone="error" onRetry={reload}>{error}</Notice>}
      {loading && !data && <Spinner label="Loading developers" />}
      {data && (
        <Card>
          {data.length === 0 ? (
            <EmptyState title="No developers yet">Add a developer so reports can be assigned.</EmptyState>
          ) : (
            <div className="-m-5 overflow-x-auto">
              <table className="w-full min-w-[980px] text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-ink-muted">
                    <th className="px-5 py-3 font-medium">Developer</th>
                    <th className="px-3 py-3 font-medium">Skills</th>
                    <th className="px-3 py-3 font-medium">Components</th>
                    <th className="px-3 py-3 text-right font-medium">Assigned</th>
                    <th className="px-3 py-3 text-right font-medium">Resolved</th>
                    <th className="px-3 py-3 text-right font-medium">Average time</th>
                    <th className="px-5 py-3 font-medium">Current workload</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((developer) => (
                    <tr key={developer.developer_id} className="border-b border-line/70 align-top last:border-0 hover:bg-page">
                      <td className="px-5 py-3">
                        <button type="button" onClick={() => setViewing(developer.developer_id)} className="text-left font-medium hover:text-brand-dark">{developer.name}</button>
                        <p className="text-xs text-ink-muted">{developer.developer_id}</p>
                        <p className="text-xs text-ink-muted">{developer.email}</p>
                      </td>
                      <td className="max-w-[240px] px-3 py-3 text-ink-soft">{developer.skills.join(', ') || 'None listed'}</td>
                      <td className="px-3 py-3 text-ink-soft">{developer.assigned_components.join(', ') || 'None'}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{developer.assigned_bugs}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{developer.resolved_bugs}</td>
                      <td className="whitespace-nowrap px-3 py-3 text-right tabular-nums">{developer.average_resolution_time === null ? 'n/a' : `${developer.average_resolution_time} days`}</td>
                      <td className="min-w-[150px] px-5 py-3">
                        <p className="mb-1 text-xs text-ink-soft">{developer.current_workload} open bugs</p>
                        <Meter value={developer.workload_percent / 100} label={`${developer.current_workload} open bugs`} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
      {adding && <AddDeveloper onClose={() => setAdding(false)} onSaved={() => { setAdding(false); reload() }} />}
      {viewing && <DeveloperDetail id={viewing} onClose={() => setViewing(null)} />}
    </>
  )
}
