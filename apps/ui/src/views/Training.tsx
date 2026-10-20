/**
 * Fingers training — an interval timer for hangboard sessions.
 *
 * THE SESSION IS FIXED (USER 2026-10-19)
 *   Three sections, each 6 rounds of 10s work and 20s rest, in that order,
 *   ending on the sixth rest. Nine minutes exactly. Nothing here is
 *   configurable because nothing was asked to be: the shape of the session is
 *   the point of it. Change the four constants below and the plan, the cues,
 *   the pips and the clock all follow.
 *
 * WHY THE TIMING LIVES IN THE BROWSER
 *   Unlike Timers and Alarms, which the backend owns because they must
 *   survive a reload, this is a session you stand in front of. It needs cue
 *   accuracy in the tens of milliseconds and it is meaningless if you walk
 *   away, so it runs here and dies with the view. The schedule is ABSOLUTE --
 *   every phase and every cue is an offset from one start instant — so a
 *   late tick never accumulates drift the way a decrementing counter would.
 *
 * THE CUES
 *   A sound at every phase start and at 3, 2 and 1 seconds remaining, plus
 *   one at the end of the session. They are a sorted list of offsets with a
 *   pointer into it, so a tick that arrives late fires everything it passed
 *   and makes ONE sound rather than a burst -- which is what happens if
 *   Chromium throttles the panel while something else has the foreground.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { AppHeader } from '../components/AppHeader'
import { Icon } from '../components/Term'
import { soundUrl } from '../lib/api'
import './Training.css'

/** One lead-in, before anything counts (USER 2026-10-19): time to get on the
 *  board. It happens once per session, never between sections. */
const PREP_S = 30
const WORK_S = 10
const REST_S = 20
const REPS = 6
const SECTIONS = ['4 finger half crimp', 'three fingers', 'two fingers']

interface Phase {
  kind: 'prep' | 'work' | 'rest'
  section: number
  rep: number
  /** Milliseconds from the start of the session. */
  start: number
  end: number
}

function buildPlan(): Phase[] {
  const plan: Phase[] = []
  // The lead-in belongs to the first section, so the banner announces what
  // you are getting ready FOR rather than announcing nothing.
  let at = PREP_S * 1000
  plan.push({ kind: 'prep', section: 0, rep: 0, start: 0, end: at })

  for (let section = 0; section < SECTIONS.length; section++) {
    for (let rep = 0; rep < REPS; rep++) {
      plan.push({ kind: 'work', section, rep, start: at, end: at + WORK_S * 1000 })
      at += WORK_S * 1000
      plan.push({ kind: 'rest', section, rep, start: at, end: at + REST_S * 1000 })
      at += REST_S * 1000
    }
  }
  return plan
}

const PLAN = buildPlan()
const TOTAL_MS = PLAN[PLAN.length - 1].end

/** Every moment that makes a sound, in order. */
const CUES: number[] = (() => {
  const out: number[] = []
  for (const phase of PLAN) {
    out.push(phase.start)
    for (const left of [3, 2, 1]) {
      const at = phase.end - left * 1000
      if (at > phase.start) out.push(at)
    }
  }
  out.push(TOTAL_MS)
  return out.sort((a, b) => a - b)
})()

/** How often the clock is read. 100ms is four frames of slack on a cue the
 *  ear cannot place that precisely anyway, and a tenth of the re-renders a
 *  rAF loop would cost this GPU. */
const TICK_MS = 100

type Status = 'idle' | 'running' | 'paused' | 'done'

function mmss(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

export function Training({ sound }: { sound: string }) {
  const [status, setStatus] = useState<Status>('idle')
  const [elapsed, setElapsed] = useState(0)
  const [blocked, setBlocked] = useState(false)
  // Bumped on every start, only so the section banner replays when a session
  // is restarted from the section it is already in.
  const [session, setSession] = useState(0)

  // Milliseconds banked before the current run segment. Pausing adds the
  // segment to it; resuming starts a new one. The wall clock is never
  // consulted -- performance.now() is monotonic and does not step when NTP
  // corrects the Pi's clock mid-session.
  const bankedRef = useRef(0)
  const segmentRef = useRef(0)
  const cueRef = useRef(0)

  // A small pool, because two cues can land a few hundred ms apart and one
  // element cannot overlap itself.
  const poolRef = useRef<HTMLAudioElement[]>([])
  const nextRef = useRef(0)

  useEffect(() => {
    if (!sound) {
      poolRef.current = []
      return
    }
    const pool = Array.from({ length: 3 }, () => {
      const element = new Audio(soundUrl(sound))
      element.preload = 'auto'
      return element
    })
    poolRef.current = pool
    return () => {
      for (const element of pool) {
        element.pause()
        element.src = ''
      }
      poolRef.current = []
    }
  }, [sound])

  const beep = useCallback(() => {
    const pool = poolRef.current
    if (pool.length === 0) return
    const element = pool[nextRef.current++ % pool.length]
    try {
      element.currentTime = 0
    } catch {
      // Not loaded yet. play() below still does the right thing.
    }
    void element.play().catch(() => setBlocked(true))
  }, [])

  /** The Start press is the user gesture Chromium wants before it will let a
   *  page make noise. The kiosk is launched with the autoplay policy relaxed
   *  (see docs/README_PI.md), but a browser opened by hand is not, and a
   *  silent interval timer is a broken one. */
  const prime = useCallback(() => {
    for (const element of poolRef.current) {
      element.muted = true
      void element
        .play()
        .then(() => {
          element.pause()
          element.currentTime = 0
          element.muted = false
        })
        .catch(() => {
          element.muted = false
        })
    }
  }, [])

  useEffect(() => {
    if (status !== 'running') return

    const id = window.setInterval(() => {
      const value = bankedRef.current + (performance.now() - segmentRef.current)

      let passed = false
      while (cueRef.current < CUES.length && CUES[cueRef.current] <= value) {
        cueRef.current += 1
        passed = true
      }
      if (passed) beep()

      if (value >= TOTAL_MS) {
        bankedRef.current = TOTAL_MS
        setElapsed(TOTAL_MS)
        setStatus('done')
        return
      }
      setElapsed(value)
    }, TICK_MS)

    return () => window.clearInterval(id)
  }, [status, beep])

  const start = useCallback(() => {
    prime()
    setBlocked(false)
    bankedRef.current = 0
    cueRef.current = 0
    segmentRef.current = performance.now()
    setElapsed(0)
    setSession((n) => n + 1)
    setStatus('running')
  }, [prime])

  const togglePause = useCallback(() => {
    setStatus((current) => {
      if (current === 'running') {
        bankedRef.current += performance.now() - segmentRef.current
        return 'paused'
      }
      if (current === 'paused') {
        segmentRef.current = performance.now()
        return 'running'
      }
      return current
    })
  }, [])

  const stop = useCallback(() => {
    bankedRef.current = 0
    cueRef.current = 0
    setElapsed(0)
    setStatus('idle')
  }, [])

  // -- what to draw -------------------------------------------------------

  const index = PLAN.findIndex((phase) => elapsed < phase.end)
  const phase = PLAN[index === -1 ? PLAN.length - 1 : index]
  const span = phase.end - phase.start
  const progress = Math.min(1, Math.max(0, (elapsed - phase.start) / span))
  const left = Math.max(0, phase.end - elapsed)
  // Ceil, so the number shown is the number you have left to act on: it reads
  // 10 for the whole first second and hits 0 only at the cue.
  const seconds = Math.ceil(left / 1000)
  const urgent = status === 'running' && left <= 3000
  const live = status === 'running' || status === 'paused'
  const prep = phase.kind === 'prep'
  const KIND_WORD = { prep: 'get ready', work: 'work', rest: 'rest' }

  return (
    <main className="training">
      <AppHeader
        title="Fingers training"
        subtitle={
          live
            ? prep
              ? `get ready · ${SECTIONS[0]}`
              : `${KIND_WORD[phase.kind]} · section ${phase.section + 1}/3 · round ${phase.rep + 1}/${REPS}`
            : status === 'done'
              ? 'session complete'
              : `${PREP_S}s in · 3 sections · ${REPS} × ${WORK_S}s / ${REST_S}s · ${mmss(TOTAL_MS)}`
        }
      />

      <section
        className={`training__stage${live ? ' is-live' : ''}${
          urgent ? ' is-urgent' : ''
        }`}
        data-kind={live ? phase.kind : 'idle'}
        data-state={status}
      >
        {/* Sonar. Three rings on staggered delays, scale and opacity only,
            frozen with the session when it is paused. */}
        <div className="training__sonar" aria-hidden>
          <span style={{ animationDelay: '0s' }} />
          <span style={{ animationDelay: '1.4s' }} />
          <span style={{ animationDelay: '2.8s' }} />
        </div>

        {live && (
          <div className="training__controls">
            <button
              type="button"
              className="training__btn"
              aria-label={status === 'paused' ? 'Resume' : 'Pause'}
              onClick={togglePause}
            >
              <Icon name={status === 'paused' ? 'play' : 'pause'} />
            </button>
            <button
              type="button"
              className="training__btn"
              aria-label="Restart the session"
              onClick={start}
            >
              <Icon name="refresh" />
            </button>
            <button
              type="button"
              className="training__btn training__btn--stop"
              aria-label="Stop the session"
              onClick={stop}
            >
              <Icon name="close" />
            </button>
          </div>
        )}

        {status === 'idle' && (
          <div className="training__idle">
            <p className="training__plan mono">
              {SECTIONS.map((name, i) => (
                <span key={name}>
                  <span className="training__plan-n">{i + 1}</span>
                  {name}
                </span>
              ))}
            </p>
            <button type="button" className="training__start" onClick={start}>
              <span className="training__start-prompt" aria-hidden>
                ❯
              </span>
              start
            </button>
            {!sound && (
              <p className="training__warn mono">
                no cue sound chosen — pick one in Settings
              </p>
            )}
          </div>
        )}

        {status === 'done' && (
          <div className="training__idle">
            <p className="training__done">Session complete</p>
            <p className="training__plan mono">
              3 sections · {REPS * SECTIONS.length} rounds · {mmss(TOTAL_MS)}
            </p>
            <button type="button" className="training__start" onClick={start}>
              <span className="training__start-prompt" aria-hidden>
                ❯
              </span>
              again
            </button>
          </div>
        )}

        {live && (
          <>
            {/* Keyed on the section, so arriving at one replays the banner.
                This is the "sections know when to change" cue on the screen;
                the sound is the same beep either way. */}
            <div
              key={`${session}-${phase.section}`}
              className="training__banner"
              aria-hidden
            >
              <span className="training__banner-n">
                section {phase.section + 1}
              </span>
              <span className="training__banner-name">
                {SECTIONS[phase.section]}
              </span>
            </div>

            <div className="training__dial">
              {/* The glow. A radial disc that breathes and a conic sweep that
                  turns, both coloured by the phase, both transform/opacity
                  only -- no filter anywhere near the ring, which repaints
                  every tick. */}
              <span className="training__aura" aria-hidden />
              <span className="training__sweep" aria-hidden />

              {/* Keyed on the phase, so every change throws one ring
                  outward. This is the motion that makes a transition felt
                  rather than noticed. */}
              <span key={index} className="training__flash" aria-hidden />

              <svg className="training__ring" viewBox="0 0 220 220" aria-hidden>
                <circle className="training__ring-track" cx="110" cy="110" r="96" />
                <circle
                  className="training__ring-fill"
                  cx="110"
                  cy="110"
                  r="96"
                  pathLength={1}
                  strokeDasharray={1}
                  strokeDashoffset={1 - progress}
                />
              </svg>

              {/* One ping per second through the last three. */}
              {urgent && <span className="training__ping" aria-hidden />}

              <div className="training__readout">
                <span className="training__kind">{KIND_WORD[phase.kind]}</span>
                {/* Keyed on the value, so every tick replays the roll-in
                    rather than swapping a glyph in place. */}
                <span key={seconds} className="training__seconds num">
                  {seconds}
                </span>
                <span className="training__of mono">of {span / 1000}s</span>
              </div>
            </div>

            <p className="training__section">{SECTIONS[phase.section]}</p>

            {/* Rounds in this section. */}
            <div className="training__pips" aria-hidden>
              {Array.from({ length: REPS }, (_, rep) => (
                <span
                  key={rep}
                  className={`training__pip${
                    prep
                      ? ''
                      : rep < phase.rep
                        ? ' is-done'
                        : rep === phase.rep
                          ? ' is-now'
                          : ''
                  }`}
                />
              ))}
            </div>

            <div className="training__total">
              <span className="mono">{mmss(elapsed)}</span>
              <span className="training__total-track" aria-hidden>
                <span
                  className="training__total-fill"
                  style={{ transform: `scaleX(${elapsed / TOTAL_MS})` }}
                />
              </span>
              <span className="mono">{mmss(TOTAL_MS)}</span>
            </div>

            {status === 'paused' && (
              <p className="training__paused mono">paused</p>
            )}

            {blocked && (
              <p className="training__warn mono">
                the browser blocked the sound — tap the screen once
              </p>
            )}
          </>
        )}
      </section>
    </main>
  )
}
