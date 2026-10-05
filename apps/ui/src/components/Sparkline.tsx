import { useMemo } from 'react'
import type { Sample } from '../lib/useServices'
import './Sparkline.css'

/**
 * Heartbeat trail: one vertical bar per poll, full height when healthy,
 * stub height when down.
 *
 * Bars rather than a line chart on purpose — health is binary, and a line
 * between two states implies interpolation that did not happen. This is the
 * same reasoning behind the bar style in CI dashboards.
 */
export function Sparkline({
  samples,
  slots = 40,
  height = 28,
}: {
  samples: Sample[]
  slots?: number
  height?: number
}) {
  const bars = useMemo(() => samples.slice(-slots), [samples, slots])

  if (bars.length === 0) {
    return <div className="spark spark--empty" style={{ height }} aria-hidden />
  }

  // Right-align the trail: a partially filled history grows leftward from the
  // present rather than stretching to fill, so bar width never changes as
  // samples accumulate.
  const pad = Math.max(0, slots - bars.length)

  return (
    <div
      className="spark"
      style={{ height, '--slots': slots } as React.CSSProperties}
      aria-hidden
    >
      {Array.from({ length: pad }, (_, i) => (
        <span key={`pad-${i}`} className="spark__bar spark__bar--pad" />
      ))}
      {bars.map((s, i) => (
        <span
          key={s.t}
          className={`spark__bar ${s.healthy ? 'spark__bar--ok' : 'spark__bar--down'}`}
          // Stagger the entrance only for the initial fill, capped so a long
          // trail does not animate for seconds.
          style={{ animationDelay: `${Math.min(i * 12, 420)}ms` }}
        />
      ))}
    </div>
  )
}
