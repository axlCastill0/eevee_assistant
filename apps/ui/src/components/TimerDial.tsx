/**
 * Drag-to-set duration dial.
 *
 * WHY THIS REPLACED THE ± STEPPER
 *   The old control moved in one-minute steps. A 45-minute timer was 45 taps.
 *   There is no keyboard on this panel (and no on-screen one wanted), so a
 *   text field was never an option either -- which leaves a gesture, and a
 *   dial is the gesture everyone already knows from an oven.
 *
 * THE MAPPING
 *   One full revolution is 60 minutes, so 6° per minute, and the ring
 *   doubles as a clock face: "a quarter turn" is fifteen minutes. Turning
 *   past the top keeps going -- wraps are counted, not clamped -- so two
 *   turns is two hours, up to the backend's 12-hour ceiling.
 *
 *   The dial snaps to whole minutes and nothing finer. That is not a
 *   limitation of the gesture, it is the same granularity the ± stepper it
 *   replaced had, and the sub-minute end is served by a preset: nobody dials
 *   up 40 seconds, they tap "30s".
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
 */
import { useCallback, useRef, useState } from 'react'
import './TimerDial.css'

/** Matches timers.MAX_DURATION_S on the backend, which clamps anyway. */
const MAX_S = 12 * 3600
const MIN_S = 0

/** Degrees per minute: a full turn is an hour. */
const DEG_PER_MIN = 6

export function TimerDial({
  seconds,
  onChange,
}: {
  seconds: number
  onChange: (seconds: number) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const lastAngle = useRef<number | null>(null)
  const [dragging, setDragging] = useState(false)

  /** Angle of a point about the dial's centre, in degrees, 0 at twelve
   *  o'clock and increasing clockwise -- the direction a dial turns. */
  const angleOf = (clientX: number, clientY: number): number | null => {
    const box = ref.current?.getBoundingClientRect()
    if (!box) return null
    const dx = clientX - (box.left + box.width / 2)
    const dy = clientY - (box.top + box.height / 2)
    return (Math.atan2(dx, -dy) * 180) / Math.PI
  }

  const onDown = useCallback((e: React.PointerEvent) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    lastAngle.current = angleOf(e.clientX, e.clientY)
    setDragging(true)
  }, [])

  const onMove = useCallback(
    (e: React.PointerEvent) => {
      if (lastAngle.current === null) return

      const angle = angleOf(e.clientX, e.clientY)
      if (angle === null) return

      // Shortest way round, so crossing twelve o'clock is a small positive
      // step rather than a 350-degree jump backwards.
      let delta = angle - lastAngle.current
      if (delta > 180) delta -= 360
      if (delta < -180) delta += 360

      const steps = Math.round(delta / DEG_PER_MIN)

      // The anchor moves by the degrees actually SPENT, not to where the
      // finger is. A move event too small to be worth a minute would
      // otherwise be rounded to zero and then thrown away, so a slow drag
      // would move the dial not at all while a fast one moved it fine.
      // Advancing by `steps` keeps the remainder for the next event.
      if (steps === 0) return
      lastAngle.current += steps * DEG_PER_MIN

      onChange(Math.max(MIN_S, Math.min(MAX_S, seconds + steps * 60)))
    },
    [onChange, seconds],
  )

  const onUp = useCallback((e: React.PointerEvent) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
    lastAngle.current = null
    setDragging(false)
  }, [])

  // How far round the current revolution we are. A 90-minute timer shows half
  // a turn, and the hour count below it is what says which turn.
  const turnFraction = (seconds % 3600) / 3600
  const hours = Math.floor(seconds / 3600)

  const mm = Math.floor((seconds % 3600) / 60)
  const ss = seconds % 60

  return (
    <div
      ref={ref}
      className={`dial${dragging ? ' is-dragging' : ''}`}
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
        {/* Track. */}
        <circle className="dial__track" cx="50" cy="50" r="44" />

        {/* Filled arc. `pathLength=1` makes the dash values a plain
            fraction, so no circumference arithmetic lives in the component
            and the radius can change in CSS without touching this. */}
        <circle
          className="dial__fill"
          cx="50"
          cy="50"
          r="44"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={1 - turnFraction}
        />

        {/* Minute marks, one every five minutes. Drawn here rather than as
            twelve elements in TSX: it is the same loop either way, and this
            keeps the DOM to one node per mark with no React keys. */}
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

      {/* The knob rides a wrapper rotated by the current angle, so the only
          animated property is a transform. */}
      <div
        className="dial__knob-orbit"
        style={{ transform: `rotate(${turnFraction * 360}deg)` }}
        aria-hidden
      >
        <span className="dial__knob" />
      </div>

      <div className="dial__readout">
        <span className="dial__value num">
          {hours > 0
            ? `${hours}:${String(mm).padStart(2, '0')}`
            : `${mm}:${String(ss).padStart(2, '0')}`}
        </span>
        <span className="dial__unit">
          {seconds === 0
            ? 'drag to set'
            : hours > 0
              ? 'hours · minutes'
              : 'minutes'}
        </span>
      </div>
    </div>
  )
}
