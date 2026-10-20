/**
 * The terminal chrome: icon, pane, rule, meter, verdict.
 *
 * Five primitives in one file because they are one idea -- the window
 * furniture every view is built out of -- and splitting them would mean five
 * files of a dozen lines each.
 *
 * Where a line is drawn with real box-drawing characters rather than a CSS
 * border, that is deliberate: the characters are slightly heavier and sit on
 * the text baseline, which is what makes a divider read as terminal output
 * instead of as a web page's hairline. Panes keep CSS borders, which stay
 * exactly 1px at any zoom.
 */
import { GLYPH, type GlyphName } from '../fonts/glyphs'
import './Term.css'

/** A glyph from the subset Nerd Font. Decorative by default -- every icon in
 *  this UI sits beside its own label. */
export function Icon({ name, className }: { name: GlyphName; className?: string }) {
  return (
    <span className={`ico${className ? ` ${className}` : ''}`} aria-hidden>
      {GLYPH[name]}
    </span>
  )
}

/** A framed pane with a titled bar, as a multiplexer draws a window.
 *
 *  `focus` marks the pane that currently matters -- it reddens the frame and
 *  the bar's tick. At most one per screen; more than one and it means
 *  nothing. */
export function Pane({
  title,
  icon,
  meta,
  focus,
  flush,
  className,
  children,
}: {
  title: string
  icon?: GlyphName
  /** Right-hand side of the bar: a count, a latency, a state. */
  meta?: React.ReactNode
  focus?: boolean
  /** Drops the body padding, for a pane whose content is its own list. */
  flush?: boolean
  className?: string
  children: React.ReactNode
}) {
  return (
    <section
      className={`pane themed${focus ? ' is-focus' : ''}${className ? ` ${className}` : ''}`}
    >
      <header className="pane__bar">
        <span className="pane__tick" aria-hidden />
        {icon && <Icon name={icon} className="pane__icon" />}
        <h2 className="pane__title">{title}</h2>
        <span className="pane__fill" aria-hidden>
          ────────────────────────────────────────────────────────────────────
        </span>
        {meta !== undefined && <span className="pane__meta mono">{meta}</span>}
      </header>

      <div className={`pane__body${flush ? ' is-flush' : ''}`}>{children}</div>
    </section>
  )
}

/** A labelled divider: ── ▣ LABEL ─────────────── */
export function Rule({ label, icon }: { label?: string; icon?: GlyphName }) {
  return (
    <div className="rule" aria-hidden>
      <span className="rule__dash">──</span>
      {icon && <Icon name={icon} className="rule__icon" />}
      {label && <span className="rule__label">{label}</span>}
      <span className="rule__fill">
        ────────────────────────────────────────────────────────────────────
      </span>
    </div>
  )
}

/** A block-character bar: ████████░░░░░░░░
 *
 *  Used instead of a smooth fill anywhere the value is a reading rather than
 *  a motion -- load, heartbeat pressure, a countdown's progress. Redrawing it
 *  swaps a short text run, which is cheaper than it looks and the only honest
 *  way to show a quantised value. Anything that has to move smoothly (the
 *  music progress bar) still scales a div. */
export function Meter({
  value,
  cells = 16,
  tone = 'accent',
}: {
  /** 0..1, clamped. */
  value: number
  cells?: number
  tone?: 'accent' | 'ok' | 'warn' | 'down' | 'dim'
}) {
  const safe = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0
  const on = Math.round(safe * cells)
  return (
    <span className={`meter meter--${tone}`} aria-hidden>
      <span className="meter__on">{'█'.repeat(on)}</span>
      <span className="meter__off">{'░'.repeat(cells - on)}</span>
    </span>
  )
}

/** A bracketed verdict: [ OK ] [FAIL] [WARN] [ -- ]
 *
 *  Padded to four characters so a column of them aligns, and spelled out so
 *  the state does not depend on telling red from green. */
export function Verdict({
  tone,
  label,
}: {
  tone: 'ok' | 'warn' | 'down' | 'idle'
  label?: string
}) {
  const text = label ?? { ok: 'OK', warn: 'WARN', down: 'FAIL', idle: '--' }[tone]
  const pad = Math.max(0, 4 - text.length)
  const left = ' '.repeat(Math.ceil(pad / 2))
  const right = ' '.repeat(Math.floor(pad / 2))
  return (
    <span className={`verdict verdict--${tone}`}>
      [{left}
      {text}
      {right}]
    </span>
  )
}
