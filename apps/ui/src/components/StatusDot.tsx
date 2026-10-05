import './StatusDot.css'

export type Tone = 'ok' | 'warn' | 'down' | 'idle'

/**
 * A small status dot with an expanding halo.
 *
 * The halo is a sibling element that scales and fades — not a box-shadow or
 * filter animation, both of which repaint every frame. This version stays on
 * the compositor.
 */
export function StatusDot({
  tone,
  size = 10,
  pulse = true,
}: {
  tone: Tone
  size?: number
  pulse?: boolean
}) {
  return (
    <span
      className={`dot dot--${tone}${pulse && tone !== 'idle' ? ' dot--pulse' : ''}`}
      style={{ '--dot-size': `${size}px` } as React.CSSProperties}
      aria-hidden
    >
      <span className="dot__halo" />
      <span className="dot__core" />
    </span>
  )
}
