import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Search, X } from 'lucide-react'
import { useApi } from '../api/client.js'
import {
  Button, COMPONENTS, Card, EmptyState, Notice, PRIORITIES, PageHeader, PriorityBadge, SEVERITIES, STATUSES, SelectControl,
  SeverityBadge, Spinner, StatusBadge, formatDate,
} from '../components/ui.jsx'

const SORTS = [
  { value: 'date_desc', label: 'Newest first' },
  { value: 'date_asc', label: 'Oldest first' },
  { value: 'priority', label: 'Highest priority first' },
]
const PAGE_SIZE = 20

export default function Bugs() {
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState(params.get('search') || '')
  const { data: developers } = useApi('/developers')

  const filters = {
    search: params.get('search') || '',
    status: params.get('status') || '',
    priority: params.get('priority') || '',
    severity: params.get('severity') || '',
    component: params.get('component') || '',
    developer: params.get('developer') || '',
    sort: params.get('sort') || 'date_desc',
    page: Number(params.get('page')) || 1,
    page_size: PAGE_SIZE,
  }
  const { data, error, loading, reload } = useApi('/bugs', filters)

  const update = (changes) => {
    const next = new URLSearchParams(params)
    Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)))
    if (!('page' in changes)) next.delete('page')
    setParams(next, { replace: true })
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      if (search !== filters.search) update({ search })
    }, 300)
    return () => clearTimeout(timer)
    // Only the typed text should restart the wait.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  const filterControls = [
    { key: 'status', label: 'Any status', options: STATUSES },
    { key: 'priority', label: 'Any priority', options: PRIORITIES },
    { key: 'severity', label: 'Any severity', options: SEVERITIES },
    { key: 'component', label: 'Any component', options: COMPONENTS },
    { key: 'developer', label: 'Any developer', options: (developers || []).map((d) => ({ value: d.developer_id, label: d.name })) },
  ]
  const active = filterControls.some((f) => filters[f.key]) || filters.search
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <>
      <PageHeader title="All bugs" description={data ? `${data.total} reports match` : undefined} action={<Link to="/submit"><Button>Submit a bug</Button></Link>} />
      <div className="mb-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        <div className="relative sm:col-span-2 lg:col-span-4 xl:col-span-1">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" aria-hidden />
          <input
            type="search"
            aria-label="Search by bug ID or title"
            placeholder="Bug ID or title"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="w-full rounded-lg border border-line bg-white py-2 pl-9 pr-3 text-sm focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
          />
        </div>
        {filterControls.map((control) => (
          <SelectControl
            key={control.key}
            aria-label={`Filter by ${control.key}`}
            options={control.options}
            placeholder={control.label}
            value={filters[control.key]}
            onChange={(event) => update({ [control.key]: event.target.value })}
          />
        ))}
        <SelectControl aria-label="Sort" options={SORTS} value={filters.sort} onChange={(event) => update({ sort: event.target.value })} />
      </div>
      {active && (
        <div className="mb-3">
          <Button
            variant="ghost"
            icon={X}
            className="min-h-8 px-2 py-1"
            onClick={() => {
              setSearch('')
              setParams({}, { replace: true })
            }}
          >
            Clear filters
          </Button>
        </div>
      )}

      {error && <Notice tone="error" onRetry={reload}>{error}</Notice>}
      {!data && loading && <Spinner label="Loading bugs" />}
      {data && (
        <Card className={`transition-opacity ${loading ? 'opacity-60' : ''}`}>
          {data.items.length === 0 ? (
            <EmptyState title="No bugs match these filters">Change or clear the filters to see more reports.</EmptyState>
          ) : (
            <div className="-m-5 overflow-x-auto">
              <table className="w-full min-w-[920px] text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-ink-muted">
                    <th className="px-5 py-3 font-medium">Bug</th>
                    <th className="px-3 py-3 font-medium">Status</th>
                    <th className="px-3 py-3 font-medium">Priority</th>
                    <th className="px-3 py-3 font-medium">Severity</th>
                    <th className="px-3 py-3 font-medium">Component</th>
                    <th className="px-3 py-3 font-medium">Assigned to</th>
                    <th className="px-5 py-3 font-medium">Submitted</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((bug) => (
                    <tr key={bug.bug_id} className="border-b border-line/70 last:border-0 hover:bg-page">
                      <td className="max-w-sm px-5 py-3">
                        <Link to={`/bugs/${bug.bug_id}`} className="block truncate font-medium hover:text-brand-dark">{bug.title}</Link>
                        <span className="text-xs text-ink-muted">{bug.bug_id}</span>
                      </td>
                      <td className="px-3 py-3"><StatusBadge value={bug.status} /></td>
                      <td className="px-3 py-3"><PriorityBadge value={bug.priority} /></td>
                      <td className="px-3 py-3"><SeverityBadge value={bug.severity} /></td>
                      <td className="px-3 py-3 text-ink-soft">{bug.component}</td>
                      <td className="px-3 py-3 text-ink-soft">{bug.assigned_developer_name || 'Unassigned'}</td>
                      <td className="whitespace-nowrap px-5 py-3 text-ink-soft">{formatDate(bug.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
      {data && data.total > PAGE_SIZE && (
        <nav aria-label="Pages" className="mt-3 flex items-center justify-between gap-3">
          <Button variant="secondary" icon={ChevronLeft} disabled={filters.page <= 1} onClick={() => update({ page: String(filters.page - 1) })}>Previous</Button>
          <span className="text-sm text-ink-soft">Page {filters.page} of {totalPages}</span>
          <Button variant="secondary" disabled={filters.page >= totalPages} onClick={() => update({ page: String(filters.page + 1) })}>
            Next <ChevronRight size={16} aria-hidden />
          </Button>
        </nav>
      )}
    </>
  )
}
