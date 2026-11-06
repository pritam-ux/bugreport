import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, ChevronDown, Paperclip, X } from 'lucide-react'
import { api } from '../api/client.js'
import { PredictionPanel, RecommendedDevelopers } from './Triage.jsx'
import {
  Button, COMPONENTS, Card, Input, Notice, PageHeader, SEVERITIES, Select, StatusBadge, Textarea, percent,
} from '../components/ui.jsx'

const EMPTY = {
  title: '', description: '', steps_to_reproduce: '', expected_behavior: '', actual_behavior: '',
  stack_trace: '', component: '', severity: '', os: '', browser: '', app_version: '',
}
const MAX_FILE_MB = 4
const ACCEPT = '.png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.log'

function PipelineTrace({ processing }) {
  const steps = [
    { title: 'Cleaned and combined the text', body: <p className="break-words text-ink-soft">{processing.clean_text}</p> },
    {
      title: `TF-IDF terms (${processing.token_count} after stemming and removing stop words)`,
      body: (
        <div className="flex flex-wrap gap-1">
          {processing.tokens_preview.map((token, i) => (
            <span key={`${token}-${i}`} className="rounded bg-page px-1.5 py-0.5 text-xs text-ink-soft">{token}</span>
          ))}
        </div>
      ),
    },
    {
      title: processing.embedding_dimensions
        ? `BERT embedding (${processing.embedding_dimensions} dimensions)`
        : 'BERT embedding skipped: the model is unavailable',
      body: processing.embedding_preview && (
        <p className="font-mono text-xs break-words text-ink-soft">[{processing.embedding_preview.join(', ')}, ...]</p>
      ),
    },
    { title: `Compared with ${processing.candidates_compared} existing reports using cosine similarity`, body: null },
    { title: 'Predicted component, priority and severity, then ranked developers', body: null },
    { title: 'Saved the report and predictions to MongoDB', body: null },
  ]
  return (
    <details className="group rounded-xl border border-line bg-white">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4">
        <span>
          <span className="block text-[15px] font-semibold">How this report was processed</span>
          <span className="text-sm text-ink-muted">{processing.semantic_engine}, finished in {processing.elapsed_ms} ms</span>
        </span>
        <ChevronDown size={18} className="shrink-0 text-ink-muted transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <ol className="space-y-4 border-t border-line p-5 text-sm">
        {steps.map((step, i) => (
          <li key={step.title} className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-tint text-xs font-semibold text-brand-dark">{i + 1}</span>
            <div className="min-w-0 flex-1 pt-0.5">
              <p className="font-medium">{step.title}</p>
              {step.body && <div className="mt-1.5">{step.body}</div>}
            </div>
          </li>
        ))}
      </ol>
    </details>
  )
}

function Results({ result, uploadError, onAnother }) {
  const { bug, duplicates, processing } = result
  const details = bug.prediction_details || {}
  const strong = duplicates.filter((match) => match.match_strength !== 'Weak')
  return (
    <>
      <PageHeader
        title={`Saved as ${bug.bug_id}`}
        description={bug.title}
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={onAnother}>Submit another</Button>
            <Link to={`/bugs/${bug.bug_id}`}><Button>Open report</Button></Link>
          </div>
        }
      />
      <div className="space-y-4">
        {uploadError && <Notice tone="warning" title="The report saved, but its attachment did not upload.">{uploadError} Try again from the report page.</Notice>}
        <Notice tone={strong.length ? 'warning' : 'success'} title={strong.length ? `${strong.length} existing reports may describe this issue` : 'No close matches found'}>
          {strong.length
            ? 'These are similarity estimates. Compare them and decide whether this report is a duplicate.'
            : 'The closest reports look different. You can still review them below.'}
        </Notice>

        <div className="grid gap-4 xl:grid-cols-5">
          <Card
            title="Closest existing reports"
            description="Ranked by similarity in meaning"
            className="xl:col-span-3"
            action={<Link to={`/duplicates/${bug.bug_id}`}><Button>Review duplicates</Button></Link>}
          >
            {duplicates.length === 0 ? (
              <p className="text-sm text-ink-muted">There are no other reports to compare with yet.</p>
            ) : (
              <ul className="-my-3 divide-y divide-line">
                {duplicates.map((match) => (
                  <li key={match.matched_bug_id} className="flex items-start justify-between gap-4 py-3">
                    <div className="min-w-0">
                      <Link to={`/bugs/${match.matched_bug_id}`} className="font-medium hover:text-brand-dark">{match.bug.title}</Link>
                      <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                        {match.matched_bug_id} <StatusBadge value={match.bug.status} /> {match.match_strength} match
                      </p>
                    </div>
                    <p className="shrink-0 text-right text-lg font-semibold tabular-nums">{percent(match.similarity_score)}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <div className="space-y-4 xl:col-span-2">
            <Card title="AI suggestions" description={`Pending administrator review.`}>
              <PredictionPanel predictions={details} />
            </Card>
          </div>
        </div>
        <Card title="Suggested developers">
          <RecommendedDevelopers recommendations={details.recommended_developers || []} />
        </Card>
        <PipelineTrace processing={processing} />
      </div>
    </>
  )
}

export default function SubmitBug() {
  const [form, setForm] = useState(EMPTY)
  const [file, setFile] = useState(null)
  const [fileError, setFileError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [uploadError, setUploadError] = useState(null)

  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value })

  const chooseFile = (event) => {
    const chosen = event.target.files?.[0]
    event.target.value = ''
    if (!chosen) return
    if (chosen.size > MAX_FILE_MB * 1024 * 1024) {
      setFileError(`Choose a file of ${MAX_FILE_MB} MB or less.`)
      return
    }
    setFileError(null)
    setFile(chosen)
  }

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setUploadError(null)
    try {
      const { os, browser, app_version: appVersion, component, severity, ...text } = form
      const response = await api.post('/bugs', {
        ...text,
        component: component || null,
        severity: severity || null,
        environment: { os, browser, app_version: appVersion },
      })
      if (file) {
        const data = new FormData()
        data.append('file', file)
        try {
          await api.post(`/bugs/${response.bug.bug_id}/attachments`, data)
        } catch (err) {
          setUploadError(err.message)
        }
      }
      setResult(response)
      window.scrollTo({ top: 0 })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (result) {
    return (
      <Results
        result={result}
        uploadError={uploadError}
        onAnother={() => {
          setResult(null)
          setForm(EMPTY)
          setFile(null)
        }}
      />
    )
  }

  return (
    <>
      <PageHeader title="Submit a bug" description="Clear details lead to better duplicate matches and predictions." />
      <form onSubmit={submit} className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <Card title="What happened">
            <div className="space-y-4">
              <Input label="Title" required minLength={5} maxLength={200} placeholder="Login page crashes after entering valid credentials" value={form.title} onChange={set('title')} />
              <Textarea label="Description" required minLength={10} maxLength={10000} rows={4} value={form.description} onChange={set('description')} />
              <Textarea label="Steps to reproduce" rows={3} maxLength={10000} hint="Put each step on its own line." value={form.steps_to_reproduce} onChange={set('steps_to_reproduce')} />
              <div className="grid gap-4 md:grid-cols-2">
                <Textarea label="Expected behavior" rows={2} maxLength={5000} value={form.expected_behavior} onChange={set('expected_behavior')} />
                <Textarea label="Actual behavior" rows={2} maxLength={5000} value={form.actual_behavior} onChange={set('actual_behavior')} />
              </div>
              <Textarea label="Stack trace or error logs" mono rows={4} maxLength={20000} value={form.stack_trace} onChange={set('stack_trace')} />
            </div>
          </Card>
        </div>
        <div className="space-y-4">
          <Card title="Classification" description="Leave blank to use the AI suggestion.">
            <div className="space-y-4">
              <Select label="Affected component" options={COMPONENTS} placeholder="Not sure" value={form.component} onChange={set('component')} />
              <Select label="Severity" options={SEVERITIES} placeholder="Not sure" value={form.severity} onChange={set('severity')} />
            </div>
          </Card>
          <Card title="Environment">
            <div className="space-y-4">
              <Input label="Operating system" placeholder="Windows 11" maxLength={100} value={form.os} onChange={set('os')} />
              <Input label="Browser" placeholder="Chrome 141" maxLength={100} value={form.browser} onChange={set('browser')} />
              <Input label="Application version" placeholder="3.4.1" maxLength={50} value={form.app_version} onChange={set('app_version')} />
            </div>
          </Card>
          <Card title="Screenshot or attachment">
            {file ? (
              <p className="flex items-center justify-between gap-2 rounded-lg bg-page px-3 py-2 text-sm">
                <span className="flex min-w-0 items-center gap-2"><CheckCircle2 size={16} className="shrink-0 text-good" aria-hidden /><span className="truncate">{file.name}</span></span>
                <button type="button" onClick={() => setFile(null)} aria-label={`Remove ${file.name}`} className="rounded p-0.5 hover:bg-line"><X size={16} aria-hidden /></button>
              </p>
            ) : (
              <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-line px-3 py-5 text-sm font-medium text-ink-soft focus-within:ring-2 focus-within:ring-brand hover:border-brand/50 hover:text-brand-dark">
                <Paperclip size={16} aria-hidden /> Choose a file
                <input type="file" accept={ACCEPT} className="sr-only" onChange={chooseFile} />
              </label>
            )}
            <p className="mt-2 text-xs text-ink-muted">Images, PDF, TXT or LOG, up to {MAX_FILE_MB} MB.</p>
            {fileError && <p role="alert" className="mt-1 text-xs text-critical">{fileError}</p>}
          </Card>
          {error && <Notice tone="error">{error}</Notice>}
          <Button type="submit" busy={busy} className="w-full">{busy ? 'Analyzing the report' : 'Submit bug'}</Button>
        </div>
      </form>
    </>
  )
}
