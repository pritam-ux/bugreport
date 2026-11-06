import { useEffect, useId, useRef } from 'react'
import {
  AlertOctagon, AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, Circle, CircleDot, Copy, Info,
  Loader2, Minus, PlayCircle, X, XCircle,
} from 'lucide-react'

export const COMPONENTS = ['Authentication', 'API', 'Backend', 'Database', 'Frontend', 'Infrastructure', 'UI']
export const PRIORITIES = ['Critical', 'High', 'Medium', 'Low']
export const SEVERITIES = ['Critical', 'Major', 'Minor', 'Trivial']
export const STATUSES = ['New', 'Open', 'In Progress', 'Resolved', 'Closed', 'Duplicate']

export function formatDate(value) {
  if (!value) return 'Not set'
  return new Date(value).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export const percent = (value, digits = 0) => (value === null || value === undefined ? 'n/a' : `${(value * 100).toFixed(digits)}%`)

export function Button({ variant = 'primary', busy = false, icon: Icon, children, className = '', ...props }) {
  const styles = {
    primary: 'brand-gradient text-white hover:brightness-110',
    secondary: 'bg-white text-ink border border-line hover:bg-page',
    danger: 'bg-white text-critical border border-critical/40 hover:bg-critical-tint',
    ghost: 'text-ink-soft hover:bg-brand-tint hover:text-brand-dark',
  }
  return (
    <button
      type="button"
      {...props}
      disabled={busy || props.disabled}
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-55 ${styles[variant]} ${className}`}
    >
      {busy ? <Loader2 size={16} className="animate-spin" aria-hidden /> : Icon && <Icon size={16} aria-hidden />}
      {children}
    </button>
  )
}

export function Card({ title, action, description, children, className = '' }) {
  return (
    <section className={`rounded-xl border border-line bg-white ${className}`}>
      {(title || action) && (
        <header className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
          <div className="min-w-0">
            {title && <h2 className="text-[15px] font-semibold text-ink">{title}</h2>}
            {description && <p className="mt-0.5 text-sm text-ink-muted">{description}</p>}
          </div>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

export function PageHeader({ title, description, action }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-[70ch] text-ink-soft">{description}</p>}
      </div>
      {action}
    </div>
  )
}

const inputClass =
  'w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 disabled:bg-page'

export function Field({ label, hint, required, children }) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-ink">
        {label}
        {required && <span className="text-critical"> *</span>}
      </label>
      {children(id)}
      {hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>}
    </div>
  )
}

export const Input = ({ label, hint, required, ...props }) => (
  <Field label={label} hint={hint} required={required}>
    {(id) => <input id={id} required={required} className={inputClass} {...props} />}
  </Field>
)

export const Textarea = ({ label, hint, required, mono, ...props }) => (
  <Field label={label} hint={hint} required={required}>
    {(id) => <textarea id={id} required={required} className={`${inputClass} ${mono ? 'font-mono text-xs' : ''}`} {...props} />}
  </Field>
)

export const Select = ({ label, hint, required, options, placeholder, ...props }) => (
  <Field label={label} hint={hint} required={required}>
    {(id) => <SelectControl id={id} options={options} placeholder={placeholder} required={required} {...props} />}
  </Field>
)

export function SelectControl({ options, placeholder, className = '', ...props }) {
  return (
    <select className={`${inputClass} ${className}`} {...props}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((option) => {
        const value = typeof option === 'string' ? option : option.value
        const label = typeof option === 'string' ? option : option.label
        return <option key={value} value={value}>{label}</option>
      })}
    </select>
  )
}

export const Spinner = ({ label = 'Loading' }) => (
  <div role="status" className="flex items-center justify-center gap-2 py-12 text-ink-muted">
    <Loader2 size={18} className="animate-spin" aria-hidden />
    <span className="text-sm">{label}</span>
  </div>
)

export function Notice({ tone = 'info', title, children, onRetry }) {
  const tones = {
    info: ['bg-brand-tint border-brand/25', Info, 'text-brand-dark'],
    error: ['bg-critical-tint border-critical/30', XCircle, 'text-critical'],
    warning: ['bg-warn-tint border-warn/30', AlertTriangle, 'text-warn'],
    success: ['bg-good-tint border-good/30', CheckCircle2, 'text-good'],
  }
  const [box, Icon, color] = tones[tone]
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`flex items-start gap-3 rounded-lg border px-4 py-3 text-sm ${box}`}>
      <Icon size={18} className={`mt-0.5 shrink-0 ${color}`} aria-hidden />
      <div className="min-w-0 flex-1 text-ink">
        {title && <p className="font-semibold">{title}</p>}
        {children}
      </div>
      {onRetry && <Button variant="secondary" className="min-h-8 px-3 py-1" onClick={onRetry}>Try again</Button>}
    </div>
  )
}

export const EmptyState = ({ title, children, action }) => (
  <div className="px-4 py-10 text-center">
    <p className="font-semibold text-ink">{title}</p>
    {children && <p className="mx-auto mt-1 max-w-[50ch] text-sm text-ink-muted">{children}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
)

const PRIORITY_STYLE = {
  Critical: ['bg-critical-tint text-critical', AlertOctagon],
  High: ['bg-serious-tint text-serious', ArrowUp],
  Medium: ['bg-warn-tint text-warn', Minus],
  Low: ['bg-page text-ink-soft border border-line', ArrowDown],
}
const SEVERITY_STYLE = {
  Critical: ['bg-critical-tint text-critical', AlertOctagon],
  Major: ['bg-serious-tint text-serious', AlertTriangle],
  Minor: ['bg-warn-tint text-warn', Info],
  Trivial: ['bg-page text-ink-soft border border-line', Minus],
}
const STATUS_STYLE = {
  New: ['bg-violet-tint text-violet', Circle],
  Open: ['bg-brand-tint text-brand-dark', CircleDot],
  'In Progress': ['bg-warn-tint text-warn', PlayCircle],
  Resolved: ['bg-good-tint text-good', CheckCircle2],
  Closed: ['bg-page text-ink-soft border border-line', CheckCircle2],
  Duplicate: ['bg-page text-ink-soft border border-line', Copy],
}

function Pill({ style, children }) {
  const [classes, Icon] = style || ['bg-page text-ink-soft', Circle]
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ${classes}`}>
      <Icon size={12} aria-hidden />
      {children}
    </span>
  )
}

export const PriorityBadge = ({ value }) => <Pill style={PRIORITY_STYLE[value]}>{value}</Pill>
export const SeverityBadge = ({ value }) => <Pill style={SEVERITY_STYLE[value]}>{value}</Pill>
export const StatusBadge = ({ value }) => <Pill style={STATUS_STYLE[value]}>{value}</Pill>

export function Modal({ open, onClose, title, children, wide = false }) {
  const ref = useRef(null)
  useEffect(() => {
    const dialog = ref.current
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby="modal-title"
      className={`m-auto w-[calc(100%-2rem)] rounded-xl border border-line bg-white p-0 text-ink ${wide ? 'max-w-3xl' : 'max-w-lg'}`}
    >
      {open && (
        <>
          <header className="flex items-center justify-between border-b border-line px-5 py-3">
            <h2 id="modal-title" className="font-semibold">{title}</h2>
            <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 text-ink-muted hover:bg-page hover:text-ink">
              <X size={18} aria-hidden />
            </button>
          </header>
          <div className="max-h-[75vh] overflow-y-auto p-5">{children}</div>
        </>
      )}
    </dialog>
  )
}

/** Share of a total, drawn as a thin track. The number is always shown beside it. */
export function Meter({ value, color = 'bg-brand', label }) {
  const width = Math.max(0, Math.min(100, value * 100))
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-line" role="img" aria-label={label || `${Math.round(width)}%`}>
      <div className={`h-full rounded-full ${color}`} style={{ width: `${width}%` }} />
    </div>
  )
}
