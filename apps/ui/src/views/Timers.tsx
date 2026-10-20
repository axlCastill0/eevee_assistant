/**
 * Timers — an app of its own, reached from the launcher.
 *
 * Two panes: the dial that sets a duration on the left, the running timers on
 * the right. Cards are big enough to read across a room, each with its own
 * block meter and pause.
 *
 * PAUSE
 *   The button sends the state it WANTS (`paused: true/false`) rather than a
 *   "toggle", so a double tap on a touchscreen settles instead of flapping.
 *   It is the reason timers.py stores a held remainder rather than only a
 *   monotonic deadline.
 *
 * NOTHING HERE ASSUMES IT IS THE ONLY WRITER
 *   Every control posts and then refetches through `onChanged`, so a timer
 *   started by voice shows up without a reload and two browsers cannot
 *   disagree.
 */
import { useState } from 'react'
import { AppHeader } from '../components/AppHeader'
import { Icon, Meter, Pane } from '../components/Term'
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
            : [running > 0 && `${running} running`, paused > 0 && `${paused} paused`]
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
        <Pane
          title="set"
          icon="stopwatch"
          focus={draft > 0}
          meta={draft > 0 ? countdown(draft) : 'idle'}
          className="timers__set"
        >
          <TimerDial seconds={draft} onChange={setDraft} />

          <div className="timers__presets">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                className={`timers__preset${draft === p.seconds ? ' is-armed' : ''}`}
                /* Tapping a preset ARMS the dial rather than starting
                   immediately. Starting on tap meant a mis-tap was a timer
                   you then had to cancel -- and it made "10 minutes,
                   actually 12" impossible without two actions. Start is one
                   more tap, in a fixed place. */
                onClick={() => setDraft(p.seconds)}
              >
                {p.label}
                {p.label !== '30s' && <span className="timers__preset-unit">m</span>}
              </button>
            ))}
          </div>

          <button
            type="button"
            className="timers__start"
            disabled={draft <= 0}
            onClick={() => start(draft)}
          >
            <span className="timers__start-prompt" aria-hidden>
              ❯
            </span>
            {draft > 0 ? `start ${countdown(draft)}` : 'start'}
          </button>
        </Pane>

        <Pane
          title="running"
          icon="timer"
          flush
          meta={timers.length > 0 ? `${timers.length} active` : 'empty'}
          className="timers__list"
        >
          {timers.length === 0 && (
            <div className="timers__empty">
              <p className="timers__empty-title mono">no timers</p>
              <p className="timers__empty-hint">
                Drag the dial, or say “set a timer for ten minutes”.
              </p>
            </div>
          )}

          {timers.map((timer, i) => (
            <TimerCard key={timer.id} timer={timer} index={i} onChanged={onChanged} />
          ))}
        </Pane>
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
      className={`tcard${timer.ringing ? ' is-ringing' : ''}${
        timer.paused ? ' is-paused' : ''
      }${urgent ? ' is-urgent' : ''}`}
      style={{ '--i': index } as React.CSSProperties}
    >
      <div className="tcard__main">
        <div className="tcard__remaining num">
          {timer.ringing ? 'done' : countdown(timer.remaining_s)}
        </div>
        <div className="tcard__meta mono">
          {timer.label}
          {timer.paused && ' · paused'}
          {timer.ends_at && ` · ends ${timer.ends_at}`}
        </div>
        {/* Blocks rather than a ring: the row already reads as a line of
            output, and a quantised bar is honest about a value that is only
            polled five times a second. */}
        <Meter
          value={elapsed}
          cells={20}
          tone={timer.ringing ? 'down' : timer.paused ? 'dim' : 'accent'}
        />
      </div>

      {/* A ringing timer has nothing to pause: the only thing to do with it is
          acknowledge it, which the ✕ already does. */}
      {!timer.ringing && (
        <button
          type="button"
          className="tcard__btn"
          aria-label={timer.paused ? 'Resume this timer' : 'Pause this timer'}
          onClick={() => void setTimerPaused(timer.id, !timer.paused).then(onChanged)}
        >
          <Icon name={timer.paused ? 'play' : 'pause'} />
        </button>
      )}

      <button
        type="button"
        className="tcard__btn tcard__btn--cancel"
        aria-label={`Cancel the ${timer.label} timer`}
        onClick={() => void deleteTimer(timer.id).then(onChanged)}
      >
        <Icon name="close" />
      </button>
    </article>
  )
}
