/**
 * Timers — an app of its own, reached from the launcher.
 *
 * WHAT CHANGED FROM THE OLD SHARED PAGE (USER DECISION 2026-10-16)
 *   It used to be half a screen next to the alarms, with six preset buttons
 *   and a ± stepper that moved in one-minute taps. Now it has the whole
 *   screen: a dial on the left to set a duration by dragging, and the running
 *   timers on the right as cards big enough to read across a room, each with
 *   a progress ring and its own pause.
 *
 * PAUSE
 *   New, and it is the reason timers.py now stores a held remainder rather
 *   than only a monotonic deadline. The button sends the state it WANTS
 *   (`paused: true/false`) rather than a "toggle", so a double tap on a
 *   touchscreen settles instead of flapping.
 *
 * NOTHING HERE ASSUMES IT IS THE ONLY WRITER
 *   Every control posts and then refetches through `onChanged`, so a timer
 *   started by voice shows up without a reload and two browsers cannot
 *   disagree. Same contract the old page had.
 */
import { useState } from 'react'
import { AppHeader } from '../components/AppHeader'
import { TimerDial } from '../components/TimerDial'
import { createTimer, deleteTimer, setTimerPaused, type TimerEntry } from '../lib/api'
import { countdown } from '../lib/useClockState'
import './Timers.css'

/** What a kitchen timer's buttons say. The 30s is here rather than on the
 *  dial because the dial snaps to whole minutes -- see TimerDial. */
const PRESETS: { label: string; seconds: number }[] = [
  { label: '30s', seconds: 30 },
  { label: '1', seconds: 60 },
  { label: '3', seconds: 180 },
  { label: '5', seconds: 300 },
  { label: '10', seconds: 600 },
  { label: '15', seconds: 900 },
  { label: '30', seconds: 1800 },
  { label: '45', seconds: 2700 },
]

export function Timers({
  timers,
  onChanged,
}: {
  timers: TimerEntry[]
  onChanged: () => void
}) {
  const [draft, setDraft] = useState(0)

  const start = (seconds: number) => {
    if (seconds <= 0) return
    void createTimer(seconds).then(onChanged)
    setDraft(0)
  }

  const running = timers.filter((t) => !t.ringing && !t.paused).length
  const paused = timers.filter((t) => t.paused).length

  return (
    <main className="timers">
      <AppHeader
        title="Timers"
        subtitle={
          timers.length === 0
            ? 'nothing running'
            : [
                running > 0 && `${running} running`,
                paused > 0 && `${paused} paused`,
              ]
                .filter(Boolean)
                .join(' · ')
        }
        action={
          timers.length > 0 ? (
            <span className="timers__count num">{timers.length}</span>
          ) : undefined
        }
      />

      <div className="timers__body">
        <section className="timers__set" aria-label="Set a timer">
          <TimerDial seconds={draft} onChange={setDraft} />

          <div className="timers__presets">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                className="timers__preset"
                /* Tapping a preset ARMS the dial rather than starting
                   immediately. The old page started on tap, which meant a
                   mis-tap was a timer you then had to cancel -- and it made
                   "10 minutes, actually 12" impossible without two actions.
                   Start is one more tap, in a fixed place. */
                onClick={() => setDraft(p.seconds)}
              >
                {p.label}
                {p.label !== '30s' && <span className="timers__preset-unit">min</span>}
              </button>
            ))}
          </div>

          <button
            type="button"
            className="timers__start"
            disabled={draft <= 0}
            onClick={() => start(draft)}
          >
            {draft > 0 ? `Start ${countdown(draft)}` : 'Start'}
          </button>
        </section>

        <section className="timers__list" aria-label="Running timers">
          {timers.length === 0 && (
            <div className="timers__empty">
              <p className="timers__empty-title">No timers</p>
              <p className="timers__empty-hint">
                Drag the dial, or say “set a timer for ten minutes”.
              </p>
            </div>
          )}

          {timers.map((timer, i) => (
            <TimerCard key={timer.id} timer={timer} index={i} onChanged={onChanged} />
          ))}
        </section>
      </div>
    </main>
  )
}

/** One running, paused or ringing timer. */
function TimerCard({
  timer,
  index,
  onChanged,
}: {
  timer: TimerEntry
  index: number
  onChanged: () => void
}) {
  const elapsed =
    timer.duration_s > 0
      ? Math.min(1, Math.max(0, 1 - timer.remaining_s / timer.duration_s))
      : 0

  // Under ten seconds the card goes insistent. Not while paused -- a paused
  // timer at 3 seconds is not about to do anything.
  const urgent = timer.ringing || (!timer.paused && timer.remaining_s <= 10)

  return (
    <article
      className={`tcard themed${timer.ringing ? ' is-ringing' : ''}${
        timer.paused ? ' is-paused' : ''
      }${urgent ? ' is-urgent' : ''}`}
      style={{ '--i': index } as React.CSSProperties}
    >
      {urgent && <span className="tcard__halo" aria-hidden />}

      {/* Progress ring. stroke-dashoffset is not compositor-accelerated, but
          this is one short stroke per card updated five times a second, which
          is the same budget the sparklines already run on. */}
      <svg className="tcard__ring" viewBox="0 0 44 44" aria-hidden>
        <circle className="tcard__ring-track" cx="22" cy="22" r="19" />
        <circle
          className="tcard__ring-fill"
          cx="22"
          cy="22"
          r="19"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={1 - elapsed}
        />
      </svg>

      <div className="tcard__main">
        <div className="tcard__remaining num">
          {timer.ringing ? 'done' : countdown(timer.remaining_s)}
        </div>
        <div className="tcard__meta">
          {timer.label}
          {timer.paused && ' · paused'}
          {timer.ends_at && ` · ends ${timer.ends_at}`}
        </div>
      </div>

      {/* A ringing timer has nothing to pause: the only thing to do with it
          is acknowledge it, which the ✕ already does. */}
      {!timer.ringing && (
        <button
          type="button"
          className="tcard__btn"
          aria-label={timer.paused ? 'Resume this timer' : 'Pause this timer'}
          onClick={() => void setTimerPaused(timer.id, !timer.paused).then(onChanged)}
        >
          {timer.paused ? (
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <path d="M8 5.5v13l11-6.5Z" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <rect x="7" y="5.5" width="3.6" height="13" rx="1.2" />
              <rect x="13.4" y="5.5" width="3.6" height="13" rx="1.2" />
            </svg>
          )}
        </button>
      )}

      <button
        type="button"
        className="tcard__btn tcard__btn--cancel"
        aria-label={`Cancel the ${timer.label} timer`}
        onClick={() => void deleteTimer(timer.id).then(onChanged)}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
             strokeLinecap="round" aria-hidden>
          <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />
        </svg>
      </button>
    </article>
  )
}
