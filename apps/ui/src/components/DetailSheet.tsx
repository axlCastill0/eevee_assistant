import { useEffect, useRef, useState } from 'react'
import type { ServiceEntry } from '../lib/api'
import { duration, serviceLabel } from '../lib/format'
import type { Sample } from '../lib/useServices'
import { Sparkline } from './Sparkline'
import { StatusDot } from './StatusDot'
import './DetailSheet.css'

/**
 * Bottom sheet with per-service detail.
 *
 * Dismissal: tap the scrim, press Close, or drag the sheet down. Drag is the
 * gesture people actually reach for on a touch panel, and it means the close
 * button never has to be hunted for.
 *
 * The drag is applied as an inline transform during the gesture and handed
 * back to CSS on release, so dragging never triggers layout.
 */

const DISMISS_PX = 110

export function DetailSheet({
  service,
  samples,
  staleAfterS,
  onClose,
}: {
  service: ServiceEntry
  samples: Sample[]
  staleAfterS: number
  onClose: () => void
}) {
  const [dragY, setDragY] = useState(0)
  const [dragging, setDragging] = useState(false)
  const startY = useRef(0)

  // Escape for a plugged-in keyboard.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const onPointerDown = (e: React.PointerEvent) => {
    startY.current = e.clientY
    setDragging(true)
    // Keeps receiving moves even if the finger leaves the element.
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging) return
    // Downward only; an upward drag should not lift the sheet off the edge.
    setDragY(Math.max(0, e.clientY - startY.current))
  }

  const onPointerUp = () => {
    setDragging(false)
    if (dragY > DISMISS_PX) onClose()
    else setDragY(0)
  }

  const ok = service.healthy
  const total = samples.length
  const healthySamples = samples.filter((s) => s.healthy).length
  const uptimePct = total ? Math.round((healthySamples / total) * 100) : null

  return (
    <div className="sheet-layer">
      <div className="sheet__scrim" onClick={onClose} aria-hidden />

      <div
        className={`sheet themed${dragging ? ' is-dragging' : ''}`}
        style={{ transform: dragY ? `translate3d(0,${dragY}px,0)` : undefined }}
        role="dialog"
        aria-modal="true"
        aria-label={`${serviceLabel(service.name)} detail`}
      >
        {/* Drag handle: a wide grab area, not just the visual pill. */}
        <div
          className="sheet__grab"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          <span className="sheet__handle" aria-hidden />
        </div>

        <div className="sheet__head">
          <StatusDot tone={ok ? 'ok' : 'down'} size={14} />
          <h2 className="sheet__title">{serviceLabel(service.name)}</h2>
          <span className={`sheet__badge ${ok ? 'is-ok' : 'is-down'}`}>
            {ok ? 'Healthy' : 'Down'}
          </span>
        </div>

        <p className="sheet__detail mono">{service.detail}</p>

        <div className="sheet__stats">
          <Stat label="Last heartbeat" value={duration(service.last_seen_s_ago)} />
          <Stat label="Stale threshold" value={duration(staleAfterS)} />
          <Stat
            label="Uptime since load"
            value={uptimePct === null ? '--' : `${uptimePct}%`}
          />
          <Stat label="Samples" value={String(total)} />
        </div>

        <div className="sheet__section">
          <div className="sheet__section-head">
            <span className="sheet__section-title">Heartbeat trail</span>
            <span className="sheet__section-note mono">
              {total} sample{total === 1 ? '' : 's'} &middot; since page load
            </span>
          </div>
          <Sparkline samples={samples} slots={60} height={48} />
        </div>

        <button type="button" className="sheet__close" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <span className="stat__label">{label}</span>
      <span className="stat__value num">{value}</span>
    </div>
  )
}
