import { useState } from 'react'
import { useApi } from '../api/client.js'
import { GroupedRates, RateLines, SERIES, SimpleBars, TrendChart } from '../components/charts.jsx'
import { Card, Notice, PageHeader, Spinner, formatDate, percent } from '../components/ui.jsx'

const TABS = [
  ['duplicates', 'Duplicate detection'],
  ['classification', 'AI classification'],
  ['bugs', 'Bug trends'],
  ['developers', 'Developer performance'],
]

function Stat({ label, value, note }) {
  return (
    <div className="rounded-xl border border-line bg-white p-4">
      <p className="text-sm text-ink-soft">{label}</p>
      <p className="mt-1 text-[26px] font-semibold leading-tight tracking-tight">{value ?? 'n/a'}</p>
      {note && <p className="mt-0.5 text-xs text-ink-muted">{note}</p>}
    </div>
  )
}

function DatasetNote({ dataset, trainedAt }) {
  if (!dataset) {
    return <Notice tone="warning" title="No training results yet.">Run python -m scripts.train in the backend folder, then restart the API.</Notice>
  }
  return (
    <Notice tone="info" title={`Measured on ${dataset.reports} labelled reports, trained ${formatDate(trainedAt)}`}>
      {dataset.synthetic
        ? 'This is the bundled sample dataset, so expect different results on real bug reports. Retrain on your own history for numbers you can rely on.'
        : `Dataset: ${dataset.file}.`}
    </Notice>
  )
}

function DuplicateTab() {
  const { data, error, loading, reload } = useApi('/analytics/duplicates')
  if (loading && !data) return <Spinner label="Loading duplicate statistics" />
  if (error && !data) return <Notice tone="error" onRetry={reload}>{error}</Notice>
  const { bert, tfidf } = data.evaluation || {}
  const best = bert || tfidf
  const engines = [
    ...(bert ? [{ key: 'bert', name: 'BERT', color: SERIES.first }] : []),
    { key: 'tfidf', name: 'TF-IDF baseline', color: SERIES.second },
  ]
  const metricRows = best && [
    ['Recall@1', 'recall_at_1'], ['Recall@5', 'recall_at_5'], ['MRR', 'mrr'],
    ['Precision', 'precision'], ['Recall', 'recall'], ['F1', 'f1'],
  ].map(([name, key]) => ({ name, bert: bert?.[key], tfidf: tfidf?.[key] }))
  const live = data.live_reviews

  return (
    <div className="space-y-4">
      <DatasetNote dataset={data.dataset} trainedAt={data.trained_at} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Precision" value={percent(best?.precision)} note="Flagged matches that were right" />
        <Stat label="Recall" value={percent(best?.recall)} note="True duplicates that were flagged" />
        <Stat label="Found in top 5" value={percent(best?.recall_at_5)} note={`Over ${best?.queries ?? 0} duplicate reports`} />
        <Stat label="Duplicates linked" value={data.stored.duplicates_linked} note={`${data.stored.awaiting_review} reports waiting for review`} />
      </div>
      {best && (
        <div className="grid gap-4 xl:grid-cols-2">
          <GroupedRates
            title="BERT against the TF-IDF baseline"
            description="Precision and recall are scored on bug groups not used to choose the threshold."
            data={metricRows}
            series={engines}
          />
          <RateLines
            title="Precision and recall by score threshold"
            description={`BERT similarity. Best F1 near a threshold of ${best.threshold}.`}
            data={best.curve}
            xKey="threshold"
            xLabel="Threshold"
            series={[
              { key: 'precision', name: 'Precision', color: SERIES.first },
              { key: 'recall', name: 'Recall', color: SERIES.second },
            ]}
          />
        </div>
      )}
      <Card title="Decisions from your team" description="Real reviews only. Sample data is excluded.">
        {live.reviewed === 0 ? (
          <p className="text-sm text-ink-muted">No reviews yet. Precision from real decisions appears here after your team reviews duplicate matches.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-[auto_1fr]">
            <div>
              <p className="text-[26px] font-semibold leading-tight">{percent(live.observed_precision)}</p>
              <p className="text-sm text-ink-muted">{live.confirmed} of {live.reviewed} reviewed matches confirmed</p>
            </div>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-line text-left text-ink-muted"><th className="py-1 font-medium">Match strength</th><th className="py-1 text-right font-medium">Reviewed</th><th className="py-1 text-right font-medium">Confirmed</th></tr></thead>
              <tbody className="tabular-nums">
                {live.by_strength.map((row) => (
                  <tr key={row.name} className="border-b border-line/60"><td className="py-1">{row.name}</td><td className="py-1 text-right">{row.reviewed}</td><td className="py-1 text-right">{row.confirmed}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

function ConfusionMatrix({ metrics }) {
  const max = Math.max(...metrics.confusion_matrix.flat(), 1)
  // One-hue ramp. The numbers are printed too, so nothing depends on reading color.
  const cell = (value) => {
    const strength = value / max
    return { background: `rgba(42, 120, 214, ${value ? 0.08 + strength * 0.85 : 0})`, color: strength > 0.55 ? '#fff' : '#141c3a' }
  }
  return (
    <div className="overflow-x-auto">
      <table className="text-xs tabular-nums">
        <caption className="mb-2 text-left text-sm font-medium">Actual label in rows, predicted label in columns</caption>
        <thead>
          <tr>
            <th aria-hidden />
            {metrics.classes.map((label) => <th key={label} scope="col" className="min-w-16 px-1 pb-1 font-medium text-ink-muted">{label}</th>)}
          </tr>
        </thead>
        <tbody>
          {metrics.confusion_matrix.map((row, i) => (
            <tr key={metrics.classes[i]}>
              <th scope="row" className="whitespace-nowrap py-px pr-2 text-right font-medium text-ink-muted">{metrics.classes[i]}</th>
              {row.map((value, j) => (
                <td key={j} className="border-2 border-white p-2 text-center" style={cell(value)}>{value}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const FEATURE_LABELS = { tfidf: 'TF-IDF', bert: 'BERT', combined: 'BERT and TF-IDF' }

function ClassifierCard({ name, metrics }) {
  const lift = metrics.accuracy - metrics.baseline_accuracy
  return (
    <Card title={name} description={`Using ${FEATURE_LABELS[metrics.selected_features]} features, ${metrics.samples} samples, 5-fold cross-validation`}>
      <div className="grid gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
        <div className="space-y-3">
          <div>
            <p className="text-sm text-ink-soft">Accuracy</p>
            <p className="text-[26px] font-semibold leading-tight">{percent(metrics.accuracy)}</p>
            <p className="text-xs text-ink-muted">Always guessing the commonest label scores {percent(metrics.baseline_accuracy)}</p>
          </div>
          <div>
            <p className="text-sm text-ink-soft">Macro F1</p>
            <p className="text-[26px] font-semibold leading-tight">{percent(metrics.macro_f1)}</p>
          </div>
          {lift < 0.2 && (
            <Notice tone="warning">This is only modestly better than guessing, so review these predictions closely.</Notice>
          )}
        </div>
        <div className="min-w-0 space-y-4">
          <ConfusionMatrix metrics={metrics} />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[380px] text-sm">
              <thead><tr className="border-b border-line text-left text-ink-muted"><th className="py-1 font-medium">Label</th><th className="py-1 text-right font-medium">Precision</th><th className="py-1 text-right font-medium">Recall</th><th className="py-1 text-right font-medium">F1</th><th className="py-1 text-right font-medium">Samples</th></tr></thead>
              <tbody className="tabular-nums">
                {metrics.per_class.map((row) => (
                  <tr key={row.label} className="border-b border-line/60">
                    <td className="py-1">{row.label}</td>
                    <td className="py-1 text-right">{percent(row.precision)}</td>
                    <td className="py-1 text-right">{percent(row.recall)}</td>
                    <td className="py-1 text-right">{percent(row.f1)}</td>
                    <td className="py-1 text-right">{row.support}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Card>
  )
}

function ClassificationTab() {
  const { data, error, loading, reload } = useApi('/analytics/triage')
  if (loading && !data) return <Spinner label="Loading classifier results" />
  if (error && !data) return <Notice tone="error" onRetry={reload}>{error}</Notice>
  const live = data.live_decisions
  return (
    <div className="space-y-4">
      <DatasetNote dataset={data.dataset} trainedAt={data.trained_at} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Stat label="Waiting for triage" value={data.pending} />
        <Stat label="Triage decisions" value={live.reviewed} note="Real decisions, sample data excluded" />
        <Stat label="Approved unchanged" value={percent(live.acceptance_rate)} note={live.changed_fields.length ? `Most edited: ${live.changed_fields[0].name.replace('assigned_developer', 'developer')}` : 'Share of decisions'} />
      </div>
      {data.classifiers && Object.entries(data.classifiers).map(([key, metrics]) => (
        <ClassifierCard key={key} name={`${key[0].toUpperCase()}${key.slice(1)} model`} metrics={metrics} />
      ))}
    </div>
  )
}

function BugsTab() {
  const { data, error, loading, reload } = useApi('/analytics/dashboard')
  if (loading && !data) return <Spinner label="Loading bug trends" />
  if (error && !data) return <Notice tone="error" onRetry={reload}>{error}</Notice>
  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <TrendChart title="Weekly bug trend" description="Last 12 weeks" data={data.weekly_trend} />
        <TrendChart title="Monthly bug trend" description="Last 6 months" data={data.monthly_trend} />
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <SimpleBars title="Priority distribution" description="Excludes duplicates" data={data.by_priority} />
        <SimpleBars title="Severity distribution" description="Excludes duplicates" data={data.by_severity} />
        <SimpleBars title="Status distribution" description="All reports" data={data.by_status} className="md:col-span-2 xl:col-span-1" />
      </div>
      <SimpleBars title="Bugs by component" description="Excludes duplicates" data={data.by_component} vertical />
      <div className="grid gap-4 xl:grid-cols-2">
        <SimpleBars title="Time to resolve" description={`${data.resolution.resolved_total} resolved bugs. Median ${data.resolution.median_days ?? 'n/a'} days.`} data={data.resolution.distribution} />
        <SimpleBars
          title="Average days to resolve, by priority"
          data={data.resolution.by_priority.map((row) => ({ ...row, count: row.average_days }))}
          name="Average days"
          format={(v) => `${v} days`}
        />
      </div>
    </div>
  )
}

function DevelopersTab() {
  const { data, error, loading, reload } = useApi('/analytics/dashboard')
  if (loading && !data) return <Spinner label="Loading developer performance" />
  if (error && !data) return <Notice tone="error" onRetry={reload}>{error}</Notice>
  const people = [...data.developer_workload]
  const byResolved = [...people].sort((a, b) => b.resolved - a.resolved)
  const bySpeed = people.filter((p) => p.average_days !== null).sort((a, b) => a.average_days - b.average_days)
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <SimpleBars title="Bugs resolved" data={byResolved} dataKey="resolved" name="Resolved" vertical />
      <SimpleBars title="Open bugs" data={people} dataKey="open" name="Open" vertical />
      <SimpleBars
        title="Average days to resolve"
        description="Lower is faster. Compare with care, since some components are harder than others."
        data={bySpeed}
        dataKey="average_days"
        name="Average days"
        format={(v) => `${v} days`}
        vertical
        className="lg:col-span-2"
      />
    </div>
  )
}

export default function Analytics() {
  const [tab, setTab] = useState('duplicates')
  const panels = { duplicates: DuplicateTab, classification: ClassificationTab, bugs: BugsTab, developers: DevelopersTab }
  const Panel = panels[tab]
  return (
    <>
      <PageHeader title="AI analytics" description="How well the models perform, and how the team's bug work is going." />
      <div role="tablist" aria-label="Analytics sections" className="mb-4 flex gap-1 overflow-x-auto border-b border-line">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors ${tab === key ? 'border-brand text-ink' : 'border-transparent text-ink-soft hover:text-ink'}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel"><Panel /></div>
    </>
  )
}
