import type { ServiceEntry } from '../lib/api'
import { duration, serviceLabel } from '../lib/format'
import type { Sample } from '../lib/useServices'
import { Sparkline } from './Sparkline'
import { Icon, Meter, Verdict } from './Term'
import './ServiceTile.css'

/**
 * One service, as a log row. Tap opens the detail sheet.
 *
 * The verdict is first and spelled out, so a column of these can be read
 * downward without comparing colours. The whole row is the touch target
 * rather than a control inside it -- on a finger-driven panel, small
 * affordances inside a large row are a mis-tap waiting to happen.
 */
export function ServiceTile({
  service,
  samples,
  staleAfterS,
  index,
  onOpen,
}: {
  service: ServiceEntry
  samples: Sample[]
  staleAfterS: number
  index: number
  onOpen: () => void
}) {
  const ok = service.healthy
  const age = service.last_seen_s_ago

  // Fraction of the stale window consumed. Approaching 1 means a heartbeat is
  // overdue and the service is about to be marked down, which is worth seeing
  // before it happens.
  const pressure = age === null ? 1 : Math.min(1, age / staleAfterS)
  const nearStale = ok && pressure > 0.6
  const tone = ok ? (nearStale ? 'warn' : 'ok') : 'down'

  return (
    <button
      type="button"
      className={`srow is-${tone}`}
      style={{ '--i': index } as React.CSSProperties}
      onClick={onOpen}
      aria-label={`${serviceLabel(service.name)}: ${service.detail}`}
    >
      <Verdict tone={tone} />

      <span className="srow__name">{serviceLabel(service.name)}</span>

      <span className="srow__detail">{service.detail}</span>

      <span className="srow__spark" aria-hidden>
        <Sparkline samples={samples} />
      </span>

      <span className="srow__age num">{duration(age)}</span>

      {/* Heartbeat pressure, in blocks: it fills as the last beat ages, so the
          row shows a service drifting towards stale before it gets there. */}
      <span className="srow__meter">
        <Meter value={pressure} cells={8} tone={nearStale ? 'warn' : ok ? 'ok' : 'down'} />
      </span>

      <Icon name="right" className="srow__chev" />
    </button>
  )
}
