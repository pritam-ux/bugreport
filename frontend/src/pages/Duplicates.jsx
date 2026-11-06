import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, CopyCheck, RefreshCw, Search } from 'lucide-react'
import { api, useApi } from '../api/client.js'
import Comparison from '../components/Comparison.jsx'
import { Button, Card, EmptyState, Meter, Notice, PageHeader, PriorityBadge, Spinner, StatusBadge, percent } from '../components/ui.jsx'
import { useAuth } from '../context/AuthContext.jsx'

const STRENGTH_STYLE = {
  Strong: 'bg-critical-tint text-critical',
  Possible: 'bg-warn-tint text-warn',
  Weak: 'bg-page text-ink-soft border border-line',
}

function MatchList({ matches, selected, onSelect }) {
  return (
    <ul className="space-y-2">
      {matches.map((match) => {
        const isSelected = selected === match.matched_bug_id
        return (
          <li key={match.matched_bug_id}>
            <button
              type="button"
              onClick={() => onSelect(match.matched_bug_id)}
              aria-current={isSelected}
              className={`w-full rounded-lg border p-3 text-left transition-colors ${isSelected ? 'border-brand bg-brand-tint/60' : 'border-line bg-white hover:border-brand/40'}`}
            >
              <span className="flex items-start justify-between gap-3">
                <span className="line-clamp-2 min-w-0 text-sm font-medium">{match.bug.title}</span>
                <span className="shrink-0 text-lg font-semibold leading-tight tabular-nums">{percent(match.similarity_score)}</span>
              </span>
              <span className="mt-2 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                {match.matched_bug_id}
                <span className={`rounded px-1.5 py-0.5 font-medium ${STRENGTH_STYLE[match.match_strength] || STRENGTH_STYLE.Weak}`}>{match.match_strength} match</span>
                {match.user_confirmed === true && <span className="font-medium text-good">Confirmed duplicate</span>}
                {match.user_confirmed === false && <span className="font-medium text-ink-soft">Marked different</span>}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

function ScoreRow({ label, value, hint, color }) {
  return (
    <div>
      <div className="mb-1 flex justify-between gap-3 text-sm">
        <span className="text-ink-soft">{label}</span>
        <span className="font-semibold tabular-nums">{percent(value)}</span>
      </div>
      <Meter value={value ?? 0} color={color} label={`${label}: ${percent(value)}`} />
      {hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>}
    </div>
  )
}

function MatchDetail({ match, leftHeading, actions }) {
  const { bug } = match
  return (
    <Card title={bug.title} description={`Existing report ${bug.bug_id}`} action={<Link to={`/bugs/${bug.bug_id}`} className="text-sm font-medium text-brand-dark hover:underline">Open report</Link>}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <StatusBadge value={bug.status} />
        <PriorityBadge value={bug.priority} />
        <span className="text-ink-soft">{bug.component}</span>
        <span className="text-ink-soft">{bug.assigned_developer_name ? `Assigned to ${bug.assigned_developer_name}` : 'Unassigned'}</span>
      </div>

      <div className="mt-5 grid gap-5 md:grid-cols-3">
        <ScoreRow label="Similarity (BERT)" value={match.bert_score ?? match.similarity_score} hint="Closeness in meaning" />
        <ScoreRow label="Word overlap (TF-IDF)" value={match.tfidf_score} hint="Baseline, for comparison" color="bg-[#eb6834]" />
        {match.duplicate_probability !== null && match.duplicate_probability !== undefined && (
          <ScoreRow label="Estimated duplicate chance" value={match.duplicate_probability} hint="Learned from labelled examples" color="bg-violet" />
        )}
      </div>

      <div className="mt-5 rounded-lg bg-page p-4 text-sm">
        <p className="font-semibold">{match.match_strength} match. Recommended next step:</p>
        <p className="text-ink-soft">{match.recommended_action}</p>
        <p className="mt-1 text-xs text-ink-muted">A high score doesn't prove two reports are duplicates. A person makes the final call.</p>
      </div>

      <div className="mt-5">
        <Comparison comparison={match.comparison} leftHeading={leftHeading} rightHeading={bug.bug_id} />
      </div>
      {actions && <div className="mt-5 flex flex-wrap gap-2 border-t border-line pt-4">{actions}</div>}
    </Card>
  )
}

function ReviewQueue({ activeId }) {
  const { data, error } = useApi('/bugs', { duplicate_review: 'pending', page_size: 12 })
  return (
    <Card title="Waiting for review" description={data ? `${data.total} reports` : undefined}>
      {error && <Notice tone="error">{error}</Notice>}
      {data && data.items.length === 0 && <p className="text-sm text-ink-muted">All caught up. Every report has been reviewed.</p>}
      <ul className="-my-1 space-y-1">
        {data?.items.map((bug) => (
          <li key={bug.bug_id}>
            <Link
              to={`/duplicates/${bug.bug_id}`}
              className={`block rounded-lg px-2.5 py-2 text-sm hover:bg-page ${bug.bug_id === activeId ? 'bg-brand-tint' : ''}`}
            >
              <span className="line-clamp-2 font-medium">{bug.title}</span>
              <span className="text-xs text-ink-muted">{bug.bug_id}</span>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function SearchPanel({ initial, onResult }) {
  const [text, setText] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const search = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onResult(await api.post('/duplicates/search', { text }))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={search} className="flex flex-col gap-2 sm:flex-row sm:items-start">
      <label htmlFor="duplicate-search" className="sr-only">Describe the bug</label>
      <textarea
        id="duplicate-search"
        rows={2}
        minLength={10}
        required
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="Describe a bug in your own words. Nothing is saved."
        className="min-w-0 flex-1 rounded-lg border border-line bg-white px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
      />
      <Button type="submit" icon={Search} busy={busy}>Find similar reports</Button>
      {error && <div className="sm:basis-full"><Notice tone="error">{error}</Notice></div>}
    </form>
  )
}

function ReviewBanner({ data }) {
  if (data.status === 'Duplicate') {
    return (
      <Notice tone="success" title={`Marked as a duplicate of ${data.duplicate_of}`}>
        <Link to={`/bugs/${data.duplicate_of}`} className="font-medium underline">Open the original report</Link>
      </Notice>
    )
  }
  if (data.duplicate_review === 'unique') return <Notice tone="success" title="Confirmed as a unique report" />
  return null
}

function BugReview({ bugId }) {
  const { user } = useAuth()
  const { data, error, loading, reload, setData } = useApi(`/duplicates/${bugId}`)
  const { data: owner } = useApi(`/bugs/${bugId}`)
  const [selected, setSelected] = useState(null)
  const [busy, setBusy] = useState(null)
  const [actionError, setActionError] = useState(null)

  useEffect(() => setSelected(null), [bugId])

  if (loading && !data) return <Spinner label="Comparing reports" />
  if (error && !data) return <Notice tone="error" onRetry={reload}>{error}</Notice>

  const match = data.matches.find((m) => m.matched_bug_id === selected) || data.matches[0]
  const canReview = user.role !== 'Reporter' || owner?.reporter_id === user.user_id

  const act = async (name, request) => {
    setBusy(name)
    setActionError(null)
    try {
      setData(await request())
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(null)
    }
  }
  const confirm = (body) => act(body.is_duplicate ? 'duplicate' : 'unique', () => api.post('/duplicates/confirm', { bug_id: bugId, ...body }))

  return (
    <div className="space-y-4">
      <Card
        title={`${data.bug_id}: ${data.title}`}
        description="The report being reviewed"
        action={<Button variant="secondary" icon={RefreshCw} busy={busy === 'check'} onClick={() => act('check', () => api.post(`/duplicates/check/${bugId}`))}>Check again</Button>}
      >
        <p className="whitespace-pre-line text-sm text-ink-soft">{data.query}</p>
      </Card>
      <ReviewBanner data={data} />
      {actionError && <Notice tone="error">{actionError}</Notice>}
      {data.matches.length === 0 ? (
        <Card><EmptyState title="No similar reports found">Select Check again to compare with the latest reports.</EmptyState></Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
          <div className="min-w-0"><MatchList matches={data.matches} selected={match.matched_bug_id} onSelect={setSelected} /></div>
          <div className="min-w-0">
            <MatchDetail
              match={match}
              leftHeading={data.bug_id}
              actions={canReview ? (
                <>
                  <Button icon={CopyCheck} busy={busy === 'duplicate'} disabled={data.duplicate_of === match.matched_bug_id} onClick={() => confirm({ is_duplicate: true, matched_bug_id: match.matched_bug_id })}>
                    Mark as duplicate of {match.matched_bug_id}
                  </Button>
                  <Button variant="secondary" icon={CheckCircle2} busy={busy === 'unique'} disabled={data.duplicate_review === 'unique'} onClick={() => confirm({ is_duplicate: false })}>
                    Confirm as unique
                  </Button>
                </>
              ) : <p className="text-sm text-ink-muted">Only the person who submitted this report, developers and administrators can review it.</p>}
            />
          </div>
        </div>
      )}
    </div>
  )
}

function FreeSearch() {
  const [result, setResult] = useState(null)
  const [selected, setSelected] = useState(null)
  const match = result?.matches.find((m) => m.matched_bug_id === selected) || result?.matches[0]
  return (
    <div className="space-y-4">
      <Card title="Search by description">
        <SearchPanel initial="Application crashes when I click the login button." onResult={(data) => { setResult(data); setSelected(null) }} />
      </Card>
      {result && result.matches.length === 0 && <Card><EmptyState title="No reports to compare with yet" /></Card>}
      {match && (
        <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
          <div className="min-w-0"><MatchList matches={result.matches} selected={match.matched_bug_id} onSelect={setSelected} /></div>
          <div className="min-w-0"><MatchDetail match={match} leftHeading="Your description" /></div>
        </div>
      )}
    </div>
  )
}

export default function Duplicates() {
  const { bugId } = useParams()
  const navigate = useNavigate()
  return (
    <>
      <PageHeader
        title="Duplicate detection"
        description="Compare reports by meaning, then decide whether they describe the same issue."
        action={bugId && <Button variant="secondary" icon={Search} onClick={() => navigate('/duplicates')}>Search by description</Button>}
      />
      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0">{bugId ? <BugReview key={bugId} bugId={bugId} /> : <FreeSearch />}</div>
        <div className="min-w-0"><ReviewQueue activeId={bugId} /></div>
      </div>
    </>
  )
}
