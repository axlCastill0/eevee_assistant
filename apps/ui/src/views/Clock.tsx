/**
 * Dashboard — timers and alarms, side by side.
 *
 * This is the panel's main page: the thing most likely to be wanted at a
 * glance from across the room, which is why the running countdowns are the
 * largest type on it.
 *
 * TIMERS are also settable by voice; ALARMS are screen-only (USER DECISION
 * 2026-10-16). Nothing here assumes it is the only writer — every control
 * posts and then refetches, so a timer started by voice appears without a
 * reload, and two browsers cannot disagree.
 */
import { useState } from 'react'
import {
  createTimer,
  deleteTimer,
  updateAlarm,
  type AlarmEntry,
  type TimerEntry,
} from '../lib/api'
import { countdown } from '../lib/useClockState'
import './Clock.css'

/** What a kitchen timer's buttons say. Longer ones go through Custom. */
const PRESETS = [1, 3, 5, 10, 15, 30]

export function Clock({
  timers,
  alarms,
  onChanged,
}: {
  timers: TimerEntry[]
  alarms: AlarmEntry[]
  onChanged: () => void
}) {
  const [customS, setCustomS] = useState(0)

  const start = (seconds: number) => {
    if (seconds <= 0) return
    void createTimer(seconds).then(onChanged)
    setCustomS(0)
  }

  return (
    <main className="clock">
      <section className="clock__col">
        <h2 className="clock__heading">Timers</h2>

        <div className="clock__presets">
          {PRESETS.map((m) => (
            <button key={m} type="button" className="clock__preset"
                    onClick={() => start(m * 60)}>
              {m}
              <span className="clock__preset-unit">min</span>
            </button>
          ))}
        </div>

        {/* Steppers rather than a text field: there is no keyboard on this
            panel, and Chromium's native time/number pickers assume one. */}
        <div className="clock__custom">
          <button type="button" className="clock__step"
                  onClick={() => setCustomS((s) => Math.max(0, s - 60))}>−</button>
          <div className="clock__custom-value num">
            {customS > 0 ? countdown(customS) : '0:00'}
          </div>
          <button type="button" className="clock__step"
                  onClick={() => setCustomS((s) => Math.min(12 * 3600, s + 60))}>+</button>
          <button type="button" className="clock__start" disabled={customS <= 0}
                  onClick={() => start(customS)}>
            Start
          </button>
        </div>

        <div className="clock__timers">
          {timers.length === 0 && (
            <p className="clock__empty">
              No timers running. Tap a preset, or say “set a timer for ten minutes”.
            </p>
          )}

          {timers.map((timer) => (
            <div key={timer.id}
                 className={`clock__timer themed${timer.ringing ? ' is-ringing' : ''}`}>
              <div className="clock__timer-main">
                <div className="clock__timer-remaining num">
                  {timer.ringing ? 'done' : countdown(timer.remaining_s)}
                </div>
                <div className="clock__timer-meta">
                  {timer.label}
                  {timer.ends_at && ` · ends ${timer.ends_at}`}
                </div>
              </div>
              <button type="button" className="clock__cancel"
                      aria-label={`Cancel the ${timer.label} timer`}
                      onClick={() => void deleteTimer(timer.id).then(onChanged)}>
                ✕
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="clock__col">
        <h2 className="clock__heading">Alarms</h2>
        <div className="clock__alarms">
          {alarms.map((alarm) => (
            <AlarmRow key={alarm.weekday} alarm={alarm} onChanged={onChanged} />
          ))}
        </div>
      </section>
    </main>
  )
}

/** One weekday. Tapping the time expands the steppers in place — an
 *  accordion rather than a modal, so the week stays visible while you edit. */
function AlarmRow({ alarm, onChanged }: { alarm: AlarmEntry; onChanged: () => void }) {
  const [open, setOpen] = useState(false)

  const save = (values: { hour?: number; minute?: number; enabled?: boolean }) =>
    void updateAlarm(alarm.weekday, values).then(onChanged)

  // Hours wrap 0-23 internally; the row shows AM/PM, which is what the
  // backend pre-formats into `label`.
  const bump = (deltaH: number, deltaM: number) => {
    let minute = alarm.minute + deltaM
    let hour = alarm.hour + deltaH + Math.floor(minute / 60)
    minute = ((minute % 60) + 60) % 60
    hour = ((hour % 24) + 24) % 24
    save({ hour, minute })
  }

  return (
    <div className={`alarm themed${alarm.enabled ? ' is-on' : ''}`}>
      <div className="alarm__row">
        <span className="alarm__day">{alarm.day.slice(0, 3)}</span>

        <button type="button" className="alarm__time num"
                onClick={() => setOpen((o) => !o)}>
          {alarm.label}
        </button>

        {/* A switch, not a checkbox: it is the control most likely to be hit
            with a thumb, and it has to read as on/off from a distance. */}
        <button type="button"
                className={`alarm__switch${alarm.enabled ? ' is-on' : ''}`}
                role="switch"
                aria-checked={alarm.enabled}
                aria-label={`${alarm.day} alarm`}
                onClick={() => save({ enabled: !alarm.enabled })}>
          <span className="alarm__knob" />
        </button>
      </div>

      {open && (
        <div className="alarm__edit">
          <Stepper label="hour" onDown={() => bump(-1, 0)} onUp={() => bump(1, 0)} />
          <Stepper label="min" onDown={() => bump(0, -5)} onUp={() => bump(0, 5)} />
          <button type="button" className="alarm__done" onClick={() => setOpen(false)}>
            Done
          </button>
        </div>
      )}
    </div>
  )
}

function Stepper({
  label,
  onDown,
  onUp,
}: {
  label: string
  onDown: () => void
  onUp: () => void
}) {
  return (
    <div className="stepper">
      <button type="button" className="stepper__btn"
              aria-label={`${label} down`} onClick={onDown}>−</button>
      <span className="stepper__label">{label}</span>
      <button type="button" className="stepper__btn"
              aria-label={`${label} up`} onClick={onUp}>+</button>
    </div>
  )
}
