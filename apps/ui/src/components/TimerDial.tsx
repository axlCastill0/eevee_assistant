/**
 * Drag-to-set duration dial. Two rings, two speeds.
 *
 * WHY A DIAL AT ALL
 *   The control this replaced moved in one-minute steps, so a 45-minute timer
 *   was 45 taps. There is no keyboard on this panel (and no on-screen one
 *   wanted), so a text field was never an option either -- which leaves a
 *   gesture, and a dial is the gesture everyone already knows from an oven.
 *
 * TWO RINGS (USER DECISION 2026-10-16: timers must reach 1 second)
 *   OUTER ring  = minutes. One revolution is 60 minutes, 6° per minute, so it
 *                 doubles as a clock face: a quarter turn is fifteen minutes.
 *   INNER ring  = seconds. One revolution is 60 seconds, also 6° per unit.
 *
 *   Which ring you are turning is decided ONCE, at touch-down, from how far
 *   from the centre your finger landed -- never re-evaluated mid-drag. That
 *   matters: a circular gesture naturally drifts in radius, and re-testing
 *   every move would silently switch you from minutes to seconds halfway
 *   round. Picking at touch-down means the ring you started on is the ring
 *   you keep, however sloppy the circle.
 *
 *   Turning past the top keeps going on both rings -- wraps are counted, not
 *   clamped -- so two turns of the outer ring is two hours, up to the
 *   backend's 12-hour ceiling. The seconds ring carries into minutes for the
 *   same reason: dragging 58, 59, then one more notch should read 1:00, not
 *   wrap back to zero.
 *
 * WHY POINTER EVENTS AND setPointerCapture
 *   A finger dragging a dial leaves the element almost immediately -- the
 *   whole point is to move in a circle around it. Capture keeps the moves
 *   coming to the element that started the gesture, which is what stops the
 *   dial sticking when your thumb strays over a card next to it.
 *
 * WHY THE ANGLE IS TRACKED AS A DELTA
 *   Reading an absolute angle would make the dial jump to wherever you first
 *   touched it. Only the CHANGE in angle since the last move is applied, so
 *   the gesture starts from the value already set -- you can nudge 45 minutes
 *   to 47 without it leaping to 7.
 *
 * WHY THE CURRENT VALUE IS READ FROM A REF, NOT FROM THE PROP
 *   Each move adds to the value we already have. Reading that from the
 *   `seconds` PROP means reading whatever the last render gave us -- and
 *   pointermove fires faster than React re-renders, so a run of moves inside
 *   one frame would every one of them add to the SAME stale number and only
 *   the last would survive. The dial then loses most of a fast drag, and
 *   loses more of it the busier the Pi is.
 *
 *   The ref is updated the instant a change is emitted, so the next event in
 *   that same frame continues from the new value, and an effect resyncs it
 *   whenever the prop really does change (including the parent resetting the
 *   draft to zero after Start).
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import './TimerDial.css'

/** Matches timers.MAX_DURATION_S on the backend, which clamps anyway. */
const MAX_S = 12 * 3600
const MIN_S = 0

/** Degrees per notch. Both rings turn at the same rate; only the unit the
 *  notch is worth differs. */
const DEG_PER_NOTCH = 6

/** Fraction of the dial's radius below which a touch means the seconds ring.
 *  0.62 puts the boundary just inside the minutes track, so landing ON the
 *  visible outer ring always gets you minutes. */
const INNER_RATIO = 0.62

type Ring = 'minutes' | 'seconds'

/** Any angle difference reduced to the shortest way round, (-180, 180].
 *
 *  WHY A HELPER AND NOT TWO `if`s
 *     A pair of `if (d > 180) d -= 360` / `if (d < -180) d += 360` corrects
 *     ONE wrap and no more. That is fine while the anchor below stays near
 *     the finger -- and it did not, because the anchor was advanced by the
 *     degrees spent and so grew past 360 on a multi-turn drag. The second
 *     revolution then produced deltas of several hundred degrees that one
 *     `if` could not bring back into range, and the dial started subtracting
 *     instead of adding: ANY duration over an hour was unreachable by
 *     dragging. Modulo arithmetic has no such ceiling. */
function shortestTurn(degrees: number): number {
  return (((degrees % 360) + 540) % 360) - 180
}

export function TimerDial({
  seconds,
  onChange,
}: {
  seconds: number
  onChange: (seconds: number) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const lastAngle = useRef<number | null>(null)
  const ring = useRef<Ring>('minutes')
  const [dragging, setDragging] = useState<Ring | null>(null)

  // The authority on "what is the value right now" during a drag. See the
  // header for why the prop alone is not enough.
  const value = useRef(seconds)
  useEffect(() => {
    value.current = seconds
  }, [seconds])

  /** Angle of a point about the dial's centre, in degrees, 0 at twelve
   *  o'clock and increasing clockwise -- the direction a dial turns. Also
   *  reports the distance as a fraction of the dial's radius, which is what
   *  picks the ring at touch-down. */
  const probe = (
    clientX: number,
    clientY: number,
  ): { angle: number; radius: number } | null => {
    const box = ref.current?.getBoundingClientRect()
    if (!box) return null
    const dx = clientX - (box.left + box.width / 2)
    const dy = clientY - (box.top + box.height / 2)
    return {
      angle: (Math.atan2(dx, -dy) * 180) / Math.PI,
      radius: Math.hypot(dx, dy) / (box.width / 2),
    }
  }

  const onDown = useCallback((e: React.PointerEvent) => {
    const hit = probe(e.clientX, e.clientY)
    if (!hit) return
    e.currentTarget.setPointerCapture(e.pointerId)
    // Decided here and only here -- see the header.
    ring.current = hit.radius < INNER_RATIO ? 'seconds' : 'minutes'
    lastAngle.current = hit.angle
    setDragging(ring.current)
  }, [])

  const onMove = useCallback(
    (e: React.PointerEvent) => {
      if (lastAngle.current === null) return

      const hit = probe(e.clientX, e.clientY)
      if (!hit) return

      // Shortest way round, so crossing twelve o'clock is a small positive
      // step rather than a 350-degree jump backwards.
      const delta = shortestTurn(hit.angle - lastAngle.current)

      const notches = Math.round(delta / DEG_PER_NOTCH)

      // The anchor moves by the degrees actually SPENT, not to where the
      // finger is. A move event too small to be worth a notch would
      // otherwise be rounded to zero and then thrown away, so a slow drag
      // would move the dial not at all while a fast one moved it fine.
      // Advancing by `notches` keeps the remainder for the next event.
      if (notches === 0) return
      // Wrapped back into the same range `probe` reports, so the anchor
      // never drifts out of comparable territory however many turns the
      // gesture makes.
      lastAngle.current = shortestTurn(
        lastAngle.current + notches * DEG_PER_NOTCH,
      )

      const step = ring.current === 'seconds' ? 1 : 60
      const next = Math.max(MIN_S, Math.min(MAX_S, value.current + notches * step))

      // Written BEFORE the parent is told, so a second move in this same
      // frame builds on it rather than on the last rendered value.
      value.current = next
      onChange(next)
    },
    [onChange],
  )

  const onUp = useCallback((e: React.PointerEvent) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
    lastAngle.current = null
    setDragging(null)
  }, [])

  // Each ring shows its own unit's progress round its own circle, so the two
  // arcs move independently and at the rate the finger is moving them.
  const minuteTurn = (Math.floor(seconds / 60) % 60) / 60
  const secondTurn = (seconds % 60) / 60

  const hours = Math.floor(seconds / 3600)
  const mm = Math.floor((seconds % 3600) / 60)
  const ss = seconds % 60

  return (
    <div
      ref={ref}
      className={`dial${dragging ? ` is-dragging is-on-${dragging}` : ''}`}
      // Without this the browser claims the gesture for a scroll and the
      // dial only turns while the finger happens to move sideways.
      style={{ touchAction: 'none' }}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
      role="slider"
      aria-label="Timer duration"
      aria-valuemin={MIN_S}
      aria-valuemax={MAX_S}
      aria-valuenow={seconds}
      aria-valuetext={`${hours ? `${hours} hours ` : ''}${mm} minutes ${ss} seconds`}
    >
      <svg className="dial__ring" viewBox="0 0 100 100" aria-hidden>
        {/* Outer: minutes. */}
        <circle className="dial__track" cx="50" cy="50" r="44" />
        {/* `pathLength=1` makes the dash values a plain fraction, so no
            circumference arithmetic lives in the component and a radius can
            change in CSS without touching this. */}
        <circle
          className="dial__fill dial__fill--min"
          cx="50"
          cy="50"
          r="44"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={1 - minuteTurn}
        />

        {/* Inner: seconds. */}
        <circle className="dial__track dial__track--sec" cx="50" cy="50" r="33" />
        <circle
          className="dial__fill dial__fill--sec"
          cx="50"
          cy="50"
          r="33"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={1 - secondTurn}
        />

        {/* Minute marks, one every five minutes, on the outer ring only --
            the inner ring is already busy and a second set of ticks reads as
            clutter at this size. */}
        {Array.from({ length: 12 }, (_, n) => (
          <line
            key={n}
            className="dial__mark"
            x1="50"
            y1="3.5"
            x2="50"
            y2="7.5"
            transform={`rotate(${n * 30} 50 50)`}
          />
        ))}
      </svg>

      {/* Each knob rides a full-size wrapper rotated by its own ring's angle,
          so the only animated property is a transform. */}
      <div
        className="dial__knob-orbit"
        style={{ transform: `rotate(${minuteTurn * 360}deg)` }}
        aria-hidden
      >
        <span className="dial__knob dial__knob--min" />
      </div>
      <div
        className="dial__knob-orbit dial__knob-orbit--sec"
        style={{ transform: `rotate(${secondTurn * 360}deg)` }}
        aria-hidden
      >
        <span className="dial__knob dial__knob--sec" />
      </div>

      <div className="dial__readout">
        <span className="dial__value num">
          {hours > 0
            ? `${hours}:${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
            : `${mm}:${String(ss).padStart(2, '0')}`}
        </span>
        <span className="dial__unit">
          {seconds === 0 ? 'drag to set' : hours > 0 ? 'h · m · s' : 'min · sec'}
        </span>
      </div>
    </div>
  )
}
