import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { Table2, BarChart3 } from 'lucide-react'

// Validated categorical slots, in fixed order: an entity keeps its color across charts.
export const SERIES = { first: '#2a78d6', second: '#eb6834' }
const GRID = '#e8ebf3'
const AXIS = { fontSize: 12, fill: '#6b7391' }

function ChartTooltip({ active, payload, label, format = (v) => v }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-line bg-white px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-semibold text-ink">{label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} className="flex items-center gap-2 text-ink-soft">
          <span className="h-2 w-2 rounded-full" style={{ background: entry.color }} aria-hidden />
          {entry.name}: <span className="font-semibold text-ink">{entry.value === null ? 'n/a' : format(entry.value)}</span>
        </p>
      ))}
    </div>
  )
}

const LegendText = (value) => <span className="text-xs text-ink-soft">{value}</span>

/** A chart with a table view of the same numbers, so nothing depends on color or hover. */
export function ChartCard({ title, description, columns, rows, height = 260, children, className = '' }) {
  const [asTable, setAsTable] = useState(false)
  const label = asTable ? 'Show chart' : 'Show table'
  return (
    <section className={`rounded-xl border border-line bg-white p-5 ${className}`}>
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
          {description && <p className="mt-0.5 text-sm text-ink-muted">{description}</p>}
        </div>
        <button
          type="button"
          onClick={() => setAsTable(!asTable)}
          aria-label={`${label}: ${title}`}
          title={label}
          className="shrink-0 rounded-md p-1.5 text-ink-muted hover:bg-page hover:text-ink"
        >
          {asTable ? <BarChart3 size={16} aria-hidden /> : <Table2 size={16} aria-hidden />}
        </button>
      </header>
      {asTable ? (
        <div className="overflow-auto" style={{ maxHeight: height }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-ink-muted">
                {columns.map((c) => <th key={c.key} className="py-1.5 pr-3 font-medium">{c.label}</th>)}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-line/60">
                  {columns.map((c) => <td key={c.key} className="py-1.5 pr-3">{row[c.key] ?? 'n/a'}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer>
        </div>
      )}
    </section>
  )
}

export function SimpleBars({ title, description, data, dataKey = 'count', name = 'Bugs', vertical = false, height, format, domain, className }) {
  const rows = data || []
  const chartHeight = height || (vertical ? Math.max(180, rows.length * 34 + 30) : 240)
  const value = (v) => (format ? format(v) : v)
  return (
    <ChartCard
      title={title}
      description={description}
      height={chartHeight}
      className={className}
      columns={[{ key: 'name', label: 'Name' }, { key: dataKey, label: name }]}
      rows={rows.map((r) => ({ ...r, [dataKey]: r[dataKey] === null ? null : value(r[dataKey]) }))}
    >
      {vertical ? (
        <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }} barCategoryGap="30%">
          <CartesianGrid horizontal={false} stroke={GRID} />
          <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} domain={domain} />
          <YAxis type="category" dataKey="name" width={112} tick={AXIS} axisLine={false} tickLine={false} />
          <Tooltip content={<ChartTooltip format={format} />} cursor={{ fill: '#f5f6fb' }} />
          <Bar isAnimationActive={false} dataKey={dataKey} name={name} fill={SERIES.first} radius={[0, 4, 4, 0]} maxBarSize={16} />
        </BarChart>
      ) : (
        <BarChart data={rows} margin={{ left: -16, right: 8, top: 8, bottom: 0 }} barCategoryGap="35%">
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="name" tick={AXIS} axisLine={{ stroke: '#c9cfdf' }} tickLine={false} interval={0} />
          <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} domain={domain} />
          <Tooltip content={<ChartTooltip format={format} />} cursor={{ fill: '#f5f6fb' }} />
          <Bar isAnimationActive={false} dataKey={dataKey} name={name} fill={SERIES.first} radius={[4, 4, 0, 0]} maxBarSize={36} />
        </BarChart>
      )}
    </ChartCard>
  )
}

export function TrendChart({ title, description, data, height = 260, className }) {
  return (
    <ChartCard
      title={title}
      description={description}
      height={height}
      className={className}
      columns={[
        { key: 'period', label: 'Period' }, { key: 'submitted', label: 'Submitted' }, { key: 'resolved', label: 'Resolved' },
      ]}
      rows={data}
    >
      <LineChart data={data} margin={{ left: -16, right: 12, top: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="period" tick={AXIS} axisLine={{ stroke: '#c9cfdf' }} tickLine={false} minTickGap={24} />
        <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} cursor={{ stroke: '#c9cfdf' }} />
        <Legend iconType="plainline" formatter={LegendText} itemSorter={null} />
        <Line isAnimationActive={false} type="monotone" dataKey="submitted" name="Submitted" stroke={SERIES.first} strokeWidth={2} dot={false} activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }} />
        <Line isAnimationActive={false} type="monotone" dataKey="resolved" name="Resolved" stroke={SERIES.second} strokeWidth={2} dot={false} activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }} />
      </LineChart>
    </ChartCard>
  )
}

/** Two measures on one 0-100% scale. Used for precision and recall, and BERT against TF-IDF. */
export function RateLines({ title, description, data, xKey, xLabel, series, height = 260 }) {
  const pct = (v) => `${Math.round(v * 100)}%`
  return (
    <ChartCard
      title={title}
      description={description}
      height={height}
      columns={[{ key: xKey, label: xLabel }, ...series.map((s) => ({ key: s.key, label: s.name }))]}
      rows={data.map((row) => ({
        [xKey]: row[xKey],
        ...Object.fromEntries(series.map((s) => [s.key, pct(row[s.key])])),
      }))}
    >
      <LineChart data={data} margin={{ left: -8, right: 12, top: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey={xKey} tick={AXIS} axisLine={{ stroke: '#c9cfdf' }} tickLine={false} minTickGap={20} />
        <YAxis tick={AXIS} axisLine={false} tickLine={false} domain={[0, 1]} tickFormatter={pct} />
        <Tooltip content={<ChartTooltip format={pct} />} labelFormatter={(v) => v} cursor={{ stroke: '#c9cfdf' }} />
        <Legend iconType="plainline" formatter={LegendText} itemSorter={null} />
        {series.map((s) => (
          <Line isAnimationActive={false} key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} dot={false} activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }} />
        ))}
      </LineChart>
    </ChartCard>
  )
}

export function GroupedRates({ title, description, data, series, height = 260 }) {
  const pct = (v) => `${Math.round(v * 100)}%`
  return (
    <ChartCard
      title={title}
      description={description}
      height={height}
      columns={[{ key: 'name', label: 'Metric' }, ...series.map((s) => ({ key: s.key, label: s.name }))]}
      rows={data.map((row) => ({ name: row.name, ...Object.fromEntries(series.map((s) => [s.key, pct(row[s.key])])) }))}
    >
      <BarChart data={data} margin={{ left: -8, right: 8, top: 8, bottom: 0 }} barGap={2} barCategoryGap="28%">
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="name" tick={AXIS} axisLine={{ stroke: '#c9cfdf' }} tickLine={false} interval={0} />
        <YAxis tick={AXIS} axisLine={false} tickLine={false} domain={[0, 1]} tickFormatter={pct} />
        <Tooltip content={<ChartTooltip format={pct} />} cursor={{ fill: '#f5f6fb' }} />
        <Legend iconType="square" formatter={LegendText} itemSorter={null} />
        {series.map((s) => (
          <Bar isAnimationActive={false} key={s.key} dataKey={s.key} name={s.name} fill={s.color} radius={[4, 4, 0, 0]} maxBarSize={22} />
        ))}
      </BarChart>
    </ChartCard>
  )
}
