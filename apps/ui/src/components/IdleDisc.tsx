/**
 * The disc that floats on the music view when nothing is playing.
 *
 * TWO MOTIONS, DELIBERATELY ON DIFFERENT ELEMENTS
 *   ORBIT  -- a slow wander around the centre, pure CSS on the two wrappers,
 *             same trick as the now-playing cover: several transforms on
 *             co-prime-ish periods so the loop never visibly repeats.
 *   SPIN   -- the disc's own rotation, driven here in JS because a finger
 *             drives it.
 *
 *   They are on SEPARATE elements because an element has one `transform`.
 *   CSS owns the wrappers' transforms; this component owns only the inner
 *   one. Nothing ever writes a property an animation is also animating.
 *
 * WHY NOT three.js (USER DECISION 2026-10-25)
 *   The disc is seen face-on, so "spin it on its own axis" is a rotation in
 *   the plane of the screen -- a single `rotate()`. A WebGL context, a scene,
 *   a camera and ~170 KB of library would draw exactly the same pixels as the
 *   line below, on a Pi that is already compositing a kiosk. The project's
 *   rule is CSS-only animation for this reason; a flick needs momentum, which
 *   CSS cannot express, so the rotation (and ONLY the rotation) is a rAF loop.
 *
 * WHY THE TRANSFORM IS WRITTEN TO THE NODE, NOT TO STATE
 *   A spin is 60 renders a second for several seconds. Through React that is
 *   a reconciliation per frame on a Raspberry Pi, for one number that only
 *   ever lands on one element's style. The ref writes it directly; React
 *   renders this component once.
 *
 * THE FLICK
 *   Angular velocity comes from the last two pointer samples, not from the
 *   whole gesture -- what a flick means is how fast your finger was moving
 *   WHEN IT LEFT, and averaging that with a slow lead-in makes a fast flick
 *   feel mushy. Decay is time-based rather than per-frame, so a dropped frame
 *   slows the disc by the same amount as the time it cost, and the spin does
 *   not run longer on a struggling Pi than it does here.
 */
import { useCallback, useEffect, useRef } from 'react'
import discUrl from '../assets/idle-disc.png'
import './IdleDisc.css'

/** Degrees of spin per pixel of horizontal drag. Tuned so a flick across the
 *  disc is a bit more than one turn -- enough to read as a spin, not so much
 *  that a small nudge launches it. */
const DEG_PER_PX = 0.55

/** Fraction of the velocity kept per 16.7 ms. 0.982 coasts for roughly four
 *  seconds from a hard flick, which is about how long a real disc would. */
const DECAY_PER_FRAME = 0.982

/** Below this (deg/ms) the disc is no longer visibly turning, so the loop
 *  stops rather than burning frames on a rotation nobody can see. */
const STOP_BELOW = 0.002

/** A flick cannot hand over more than this (deg/ms). Two pointer samples one
 *  millisecond apart would otherwise divide by almost nothing and launch the
 *  disc at a speed that just looks broken. */
const MAX_SPEED = 2.2

export function IdleDisc() {
  const spinner = useRef<HTMLDivElement>(null)

  const angle = useRef(0)
  const velocity = useRef(0)          // deg/ms
  const frame = useRef(0)
  const lastTick = useRef(0)

  // Last two pointer samples, for the release velocity.
  const prev = useRef<{ x: number; t: number } | null>(null)
  const latest = useRef<{ x: number; t: number } | null>(null)
  const dragging = useRef(false)

  const draw = useCallback(() => {
    const el = spinner.current
    if (el) el.style.transform = `rotate(${angle.current}deg)`
  }, [])

  const stopLoop = useCallback(() => {
    if (frame.current) {
      cancelAnimationFrame(frame.current)
      frame.current = 0
    }
  }, [])

  const coast = useCallback(
    (now: number) => {
      const dt = Math.min(now - lastTick.current, 64) // a long frame must not teleport it
      lastTick.current = now

      angle.current += velocity.current * dt
      // Time-based, so the disc coasts for the same WALL time whatever the
      // frame rate: dropping frames must not make the spin last longer.
      velocity.current *= Math.pow(DECAY_PER_FRAME, dt / 16.7)
      draw()

      if (Math.abs(velocity.current) < STOP_BELOW) {
        velocity.current = 0
        frame.current = 0
        return
      }
      frame.current = requestAnimationFrame(coast)
    },
    [draw],
  )

  const onDown = useCallback(
    (e: React.PointerEvent) => {
      e.currentTarget.setPointerCapture(e.pointerId)
      stopLoop()
      // Catching a spinning disc stops it dead, the way a hand on a record
      // does. Anything softer feels like the disc is ignoring you.
      velocity.current = 0
      dragging.current = true
      const sample = { x: e.clientX, t: e.timeStamp }
      prev.current = sample
      latest.current = sample
    },
    [stopLoop],
  )

  const onMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragging.current || !latest.current) return
      angle.current += (e.clientX - latest.current.x) * DEG_PER_PX
      prev.current = latest.current
      latest.current = { x: e.clientX, t: e.timeStamp }
      draw()
    },
    [draw],
  )

  const onUp = useCallback(
    (e: React.PointerEvent) => {
      if (e.currentTarget.hasPointerCapture(e.pointerId)) {
        e.currentTarget.releasePointerCapture(e.pointerId)
      }
      if (!dragging.current) return
      dragging.current = false

      const a = prev.current
      const b = latest.current
      const dt = a && b ? b.t - a.t : 0
      // dt of 0 happens when the finger never moved (a tap) or when two
      // samples share a timestamp. Either way there is no flick to hand over.
      if (a && b && dt > 0) {
        const speed = ((b.x - a.x) * DEG_PER_PX) / dt
        velocity.current = Math.max(-MAX_SPEED, Math.min(MAX_SPEED, speed))
      }
      prev.current = null
      latest.current = null

      if (velocity.current !== 0) {
        lastTick.current = performance.now()
        frame.current = requestAnimationFrame(coast)
      }
    },
    [coast],
  )

  // A spin must not outlive the view: leaving the page mid-coast would leave
  // a rAF loop running against a detached node for as long as it took to slow
  // down. Same rule as every other long-lived thing an effect owns here.
  useEffect(() => stopLoop, [stopLoop])

  return (
    <div className="idle">
      {/* Two nested wrappers, two CSS loops, so the disc wanders rather than
          tracing one path. */}
      <div className="idle__orbit">
        <div className="idle__bob">
          <div
            className="idle__spin"
            ref={spinner}
            // Without this the browser claims the drag for a scroll and the
            // disc only turns when the finger happens to move just so.
            style={{ touchAction: 'none' }}
            onPointerDown={onDown}
            onPointerMove={onMove}
            onPointerUp={onUp}
            onPointerCancel={onUp}
          >
            <img
              className="idle__img"
              src={discUrl}
              alt=""
              aria-hidden
              draggable={false}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
