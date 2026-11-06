import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertTriangle, Check } from 'lucide-react'
import { api, useApi } from '../api/client.js'
import {
  Button, COMPONENTS, Card, EmptyState, Meter, Notice, PRIORITIES, PageHeader, SEVERITIES, Select, Spinner, percent, formatDate,
} from '../components/ui.jsx'
import { useAuth } from '../context/AuthContext.jsx'

const LOW_CONFIDENCE = 0.5
const BREAKDOWN_LABELS = {
  expertise: 'Skills and component ownership',
  history: 'Past fixes in this component',
  similar_work: 'Similar bugs fixed before',
  availability: 'Current availability',
}

function Prediction({ label, prediction }) {
  if (!prediction) {
    return (
      <div>
        <p className="text-sm text-ink-soft">{label}</p>
        <p className="text-sm text-ink-muted">No prediction. The model isn't trained.</p>
      </div>
    )
  }
  const low = prediction.confidence < LOW_CONFIDENCE
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm text-ink-soft">{label}</p>
        <p className="text-sm tabular-nums text-ink-muted">{percent(prediction.confidence)} confidence</p>
      </div>
      <p className="text-lg font-semibold leading-snug">{prediction.label}</p>
      <div className="mt-1"><Meter value={prediction.confidence} color={low ? 'bg-[#d9a400]' : 'bg-brand'} label={`Confidence ${percent(prediction.confidence)}`} /></div>
      {low && (
        <p className="mt-1.5 flex items-center gap-1 text-xs font-medium text-warn">
          <AlertTriangle size={13} aria-hidden /> Low confidence. Check this one yourself.
        </p>
      )}
      {prediction.alternatives?.length > 0 && (
        <p className="mt-1 text-xs text-ink-muted">
          Next most likely: {prediction.alternatives.map((a) => `${a.label} (${percent(a.confidence)})`).join(', ')}
        </p>
      )}
      {prediction.top_terms?.length > 0 && (
        <p className="mt-0.5 text-xs text-ink-muted">Words that influenced this: {prediction.top_terms.join(', ')}</p>
      )}
    </div>
  )
}

export function PredictionPanel({ predictions }) {
  return (
    <div className="space-y-5">
      <Prediction label="Component" prediction={predictions.component} />
      <Prediction label="Priority" prediction={predictions.priority} />
      <Prediction label="Severity" prediction={predictions.severity} />
    </div>
  )
}

export function RecommendedDevelopers({ recommendations, onChoose, chosen }) {
  if (!recommendations.length) return <p className="text-sm text-ink-muted">No developers to suggest yet.</p>
  return (
    <ol className="grid gap-3 lg:grid-cols-3">
      {recommendations.map((person, index) => (
        <li key={person.developer_id} className={`rounded-lg border p-4 ${chosen === person.developer_id ? 'border-brand bg-brand-tint/40' : 'border-line'}`}>
          <div className="flex items-baseline justify-between gap-2">
            <p className="font-semibold">{person.name}</p>
            <p className="text-sm font-semibold tabular-nums">{percent(person.score)}</p>
          </div>
          <p className="text-xs text-ink-muted">{index === 0 ? 'Best fit' : `Option ${index + 1}`}, {person.developer_id}</p>
          <p className="mt-2 text-sm text-ink-soft">{person.reason}</p>
          <dl className="mt-3 space-y-1.5">
            {Object.entries(BREAKDOWN_LABELS).map(([key, label]) => (
              <div key={key}>
                <dt className="flex justify-between text-xs text-ink-muted">
                  <span>{label}</span><span className="tabular-nums">{percent(person.breakdown[key])}</span>
                </dt>
                <dd><Meter value={person.breakdown[key]} label={`${label}: ${percent(person.breakdown[key])}`} /></dd>
              </div>
            ))}
          </dl>
          {onChoose && (
            <Button variant="secondary" className="mt-3 w-full" icon={chosen === person.developer_id ? Check : undefined} onClick={() => onChoose(person.developer_id)}>
              {chosen === person.developer_id ? 'Selected' : `Assign to ${person.name.split(' ')[0]}`}
            </Button>
          )}
        </li>
      ))}
    </ol>
  )
}

function DecisionForm({ triage, developers, onSaved }) {
  const best = triage.predictions.recommended_developers?.[0]?.developer_id
  const pending = triage.triage_status === 'pending'
  const [form, setForm] = useState({
    component: (pending && triage.predictions.component?.label) || triage.current.component,
    priority: (pending && triage.predictions.priority?.label) || triage.current.priority,
    severity: triage.current.severity,
    assigned_developer: triage.current.assigned_developer || (pending && best) || '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value })

  const save = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onSaved(await api.post(`/triage/${triage.bug_id}/decision`, { ...form, assigned_developer: form.assigned_developer || null }))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  const unchanged =
    form.component === triage.predictions.component?.label &&
    form.priority === triage.predictions.priority?.label &&
    form.severity === triage.predictions.severity?.label &&
    form.assigned_developer === best

  return (
    <div className="space-y-4">
      <form onSubmit={save} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Select label="Component" options={COMPONENTS} value={form.component} onChange={set('component')} />
          <Select label="Priority" options={PRIORITIES} value={form.priority} onChange={set('priority')} />
          <Select label="Severity" options={SEVERITIES} value={form.severity} onChange={set('severity')} />
          <Select
            label="Developer"
            placeholder="Leave unassigned"
            options={developers.map((d) => ({ value: d.developer_id, label: d.name }))}
            value={form.assigned_developer}
            onChange={set('assigned_developer')}
          />
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" busy={busy}>{unchanged ? 'Approve AI suggestions' : 'Save my changes'}</Button>
      </form>
      <RecommendedDevelopers
        recommendations={triage.predictions.recommended_developers || []}
        chosen={form.assigned_developer}
        onChoose={(id) => setForm({ ...form, assigned_developer: id })}
      />
    </div>
  )
}

function TriageDetail({ bugId }) {
  const { user } = useAuth()
  const { data, error, loading, reload, setData } = useApi(`/triage/${bugId}`)
  const { data: developers } = useApi('/developers')
  if (loading && !data) return <Spinner label="Loading predictions" />
  if (error && !data) return <Notice tone="error" onRetry={reload}>{error}</Notice>
  const isAdmin = user.role === 'Admin'
  const done = data.triage_status === 'approved' || data.triage_status === 'modified'
  const changed = data.triage_decision?.changed_fields || []
  return (
    <div className="space-y-4">
      <Card
        title={`${data.bug_id}: ${data.title}`}
        description={`Submitted ${formatDate(data.created_at)} by ${data.reporter_name}`}
        action={<Link to={`/bugs/${data.bug_id}`} className="text-sm font-medium text-brand-dark hover:underline">Open report</Link>}
      >
        <p className="whitespace-pre-line text-sm text-ink-soft">{data.description}</p>
        {(data.reported.component || data.reported.severity) && (
          <p className="mt-2 text-xs text-ink-muted">
            The reporter chose: {[data.reported.component, data.reported.severity].filter(Boolean).join(', ')}.
          </p>
        )}
      </Card>
      {done && (
        <Notice tone="success" title={data.triage_status === 'approved' ? 'AI suggestions approved' : 'Triage saved with changes'}>
          {changed.length > 0 && `Changed: ${changed.join(', ').replace('assigned_developer', 'developer')}. `}
          Assigned to {data.current.assigned_developer_name || 'nobody yet'}.
        </Notice>
      )}
      <Card title="AI predictions" description="Predictions are suggestions, and they are only applied after approval.">
        <div className="grid gap-6 md:grid-cols-3">
          <Prediction label="Component" prediction={data.predictions.component} />
          <Prediction label="Priority" prediction={data.predictions.priority} />
          <Prediction label="Severity" prediction={data.predictions.severity} />
        </div>
      </Card>
      {isAdmin && developers ? (
        <Card title={done ? 'Change this triage' : 'Approve or edit'}>
          <DecisionForm key={data.bug_id} triage={data} developers={developers} onSaved={setData} />
        </Card>
      ) : (
        <Card title="Suggested developers" description="Administrators approve or change these suggestions.">
          <RecommendedDevelopers recommendations={data.predictions.recommended_developers || []} />
        </Card>
      )}
    </div>
  )
}

export default function Triage() {
  const { bugId } = useParams()
  const { data, error, reload } = useApi('/bugs', { triage_status: 'pending', page_size: 50, sort: 'priority' })
  return (
    <>
      <PageHeader title="AI triage" description="Review the predicted component, priority, severity and developer for new reports." />
      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <Card title="Waiting for triage" description={data ? `${data.total} reports` : undefined} className="self-start">
          {error && <Notice tone="error" onRetry={reload}>{error}</Notice>}
          {data && data.items.length === 0 && <p className="text-sm text-ink-muted">All caught up. No reports are waiting.</p>}
          <ul className="-my-1 max-h-[70vh] space-y-1 overflow-y-auto">
            {data?.items.map((bug) => (
              <li key={bug.bug_id}>
                <Link to={`/triage/${bug.bug_id}`} className={`block rounded-lg px-2.5 py-2 text-sm hover:bg-page ${bug.bug_id === bugId ? 'bg-brand-tint' : ''}`}>
                  <span className="line-clamp-2 font-medium">{bug.title}</span>
                  <span className="text-xs text-ink-muted">{bug.bug_id}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
        <div className="min-w-0">
          {bugId ? <TriageDetail key={bugId} bugId={bugId} /> : (
            <Card><EmptyState title="Select a report">Choose a report from the list to review its predictions.</EmptyState></Card>
          )}
        </div>
      </div>
    </>
  )
}
