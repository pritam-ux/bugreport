import { useMemo, useState } from 'react'

const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function withKeywords(text, pattern) {
  if (!pattern) return text
  return text.split(pattern).map((part, i) =>
    i % 2 === 1 ? <mark key={i} className="keyword">{part}</mark> : part,
  )
}

function Sentences({ heading, sentences, side, active, setActive, pattern }) {
  return (
    <div className="min-w-0 flex-1">
      <h4 className="mb-2 text-sm font-semibold text-ink">{heading}</h4>
      <p className="break-words text-sm leading-7 text-ink">
        {sentences.map((sentence, index) => {
          const linked = sentence.match !== null
          const isActive = active && (
            (active.side === side && active.index === index) ||
            (active.side !== side && active.partner === index) ||
            (active.side !== side && sentence.match === active.index)
          )
          if (!linked) {
            return <span key={index} className="sentence">{withKeywords(sentence.text, pattern)} </span>
          }
          const describe = () => setActive({ side, index, partner: sentence.match })
          return (
            <span key={index}>
              <span
                tabIndex={0}
                title={`Meaning similarity ${Math.round(sentence.score * 100)}%`}
                onMouseEnter={describe}
                onMouseLeave={() => setActive(null)}
                onFocus={describe}
                onBlur={() => setActive(null)}
                className={`sentence sentence-linked ${isActive ? 'sentence-active' : ''}`}
              >
                {withKeywords(sentence.text, pattern)}
              </span>{' '}
            </span>
          )
        })}
      </p>
    </div>
  )
}

/** Two reports side by side. Sentences with the same meaning are tinted and linked on hover or focus. */
export default function Comparison({ comparison, leftHeading = 'This report', rightHeading }) {
  const [active, setActive] = useState(null)
  const keywords = comparison.shared_keywords
  const pattern = useMemo(() => {
    if (!keywords.length) return null
    const words = [...keywords].sort((a, b) => b.length - a.length).map(escapeRegExp).join('|')
    return new RegExp(`\\b(${words})\\b`, 'gi')
  }, [keywords])
  const linkedCount = comparison.source_sentences.filter((s) => s.match !== null).length

  return (
    <div>
      <div className="flex flex-col gap-5 md:flex-row md:gap-6">
        <Sentences heading={leftHeading} sentences={comparison.source_sentences} side="source" active={active} setActive={setActive} pattern={pattern} />
        <div className="hidden w-px bg-line md:block" aria-hidden />
        <Sentences heading={rightHeading} sentences={comparison.target_sentences} side="target" active={active} setActive={setActive} pattern={pattern} />
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line pt-3 text-xs text-ink-soft">
        <span className="flex items-center gap-1.5">
          <span className="sentence sentence-linked px-2" aria-hidden>Aa</span>
          {linkedCount
            ? `Similar meaning. Hover or focus a sentence to find its partner.`
            : 'No sentence pairs were close enough to link.'}
        </span>
        <span className="flex items-center gap-1.5">
          <mark className="keyword" aria-hidden>Aa</mark>
          {keywords.length ? `Shared words: ${keywords.join(', ')}` : 'No shared keywords.'}
        </span>
      </div>
    </div>
  )
}
