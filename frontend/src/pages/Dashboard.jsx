import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../api/client.js'
import { SimpleBars, TrendChart } from '../components/charts.jsx'
import { Button, Card, EmptyState, Notice, PageHeader, PriorityBadge, Spinner, StatusBadge, formatDate } from '../components/ui.jsx'
import { useAuth } from '../context/AuthContext.jsx'

function Stat({ label, value, note, to }) {
  const body = (
    <>
      <p className="text-sm text-ink-soft">{label}</p>
      <p className="mt-1 text-[28px] font-semibold leading-tight tracking-tight">{value ?? 'n/a'}</p>
      {note && <p className="mt-0.5 text-xs text-ink-muted">{note}</p>}
    </>
  )
  const classes = 'block rounded-xl border border-line bg-white p-4'
  return to ? <Link to={to} className={`${classes} transition-colors hover:border-brand/50`}>{body}</Link> : <div className={classes}>{body}</div>
}

function RecentBugs({ bugs }) {
  return (
    <div className="-mx-5 -mb-5 overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead>
          <tr className="border-y border-line text-left text-ink-muted">
            <th className="px-5 py-2 font-medium">Bug</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="px-3 py-2 font-medium">Priority</th>
            <th className="px-3 py-2 font-medium">Assigned to</th>
            <th className="px-5 py-2 font-medium">Submitted</th>
          </tr>
        </thead>
        <tbody>
          {bugs.map((bug) => (
            <tr key={bug.bug_id} className="border-b border-line/70 last:border-0 hover:bg-page">
              <td className="max-w-md px-5 py-2.5">
                <Link to={`/bugs/${bug.bug_id}`} className="block truncate font-medium hover:text-brand-dark">{bug.title}</Link>
                <span className="text-xs text-ink-muted">{bug.bug_id}</span>
              </td>
              <td className="px-3 py-2.5"><StatusBadge value={bug.status} /></td>
              <td className="px-3 py-2.5"><PriorityBadge value={bug.priority} /></td>
              <td className="px-3 py-2.5 text-ink-soft">{bug.assigned_developer_name || 'Unassigned'}</td>
              <td className="whitespace-nowrap px-5 py-2.5 text-ink-soft">{formatDate(bug.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const { data, error, loading, reload } = useApi('/analytics/dashboard')
  const [range, setRange] = useState('weekly')

  if (loading && !data) return <Spinner label="Loading the dashboard" />
  if (error && !data) return <Notice tone="error" onRetry={reload}>{error}</Notice>

  const { totals } = data
  if (!totals.total) {
    return (
      <Card>
        <EmptyState title="No bug reports yet" action={<Link to="/submit"><Button>Submit a bug</Button></Link>}>
          Submit the first report, or load the sample data with python -m scripts.seed.
        </EmptyState>
      </Card>
    )
  }

  return (
    <>
      <PageHeader
        title={`Hello, ${user.name.split(' ')[0]}`}
        description={totals.pending_triage ? `${totals.pending_triage} new reports are waiting for triage.` : 'Every report has been triaged.'}
        action={<Link to="/submit"><Button>Submit a bug</Button></Link>}
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Total bugs" value={totals.total} to="/bugs" />
        <Stat label="Open" value={totals.open} note="New, open or in progress" />
        <Stat label="Resolved" value={totals.resolved} note="Resolved or closed" />
        <Stat label="Duplicates found" value={totals.duplicates} note="Linked to an original report" to="/duplicates" />
        <Stat label="High priority" value={totals.high_priority} note="Open, high or critical" />
        <Stat
          label="Average time to resolve"
          value={totals.average_resolution_days === null ? null : `${totals.average_resolution_days} days`}
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <div className="mb-2 flex justify-end gap-1" role="group" aria-label="Trend period">
            {[['weekly', 'Weekly'], ['monthly', 'Monthly']].map(([key, label]) => (
              <button
                key={key}
                type="button"
                aria-pressed={range === key}
                onClick={() => setRange(key)}
                className={`rounded-md px-3 py-1 text-sm font-medium ${range === key ? 'bg-navy-900 text-white' : 'text-ink-soft hover:bg-white'}`}
              >
                {label}
              </button>
            ))}
          </div>
          <TrendChart
            title="Bugs submitted and resolved"
            description={range === 'weekly' ? 'Last 12 weeks' : 'Last 6 months'}
            data={range === 'weekly' ? data.weekly_trend : data.monthly_trend}
            height={270}
          />
        </div>
        <div className="xl:pt-[38px]">
          <SimpleBars title="Bugs by priority" description="Excludes duplicates" data={data.by_priority} height={270} />
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <SimpleBars title="Bugs by component" description="Excludes duplicates" data={data.by_component} vertical />
        <SimpleBars
          title="Developer workload"
          description="Open bugs assigned to each developer"
          data={data.developer_workload}
          dataKey="open"
          name="Open bugs"
          vertical
        />
      </div>

      <Card title="Recent reports" className="mt-4" action={<Link to="/bugs" className="text-sm font-medium text-brand-dark hover:underline">See all bugs</Link>}>
        <RecentBugs bugs={data.recent} />
      </Card>
    </>
  )
}
