/**
 * Alarms — an app of its own, reached from the launcher.
 *
 * THE MODEL IS UNCHANGED (USER DECISION 2026-10-16)
 *   Still seven weekday slots, still persisted, still wall clock, still no
 *   voice control. Only the controls changed. See apps/backend/alarms.py for
 *   why the shape is seven slots rather than a list.
 *
 * WHAT CHANGED
 *   The old page was seven rows, each with a ± stepper behind an accordion:
 *   ten taps to move an alarm an hour and twenty minutes, and the week only
 *   half visible while you did it. Now:
 *
 *     - the week is a strip of seven chips, always visible, each showing its
 *       time and whether it is on. It is the navigation AND the overview.
 *     - the selected day gets a wheel picker, flicked rather than tapped.
 *     - COPY TO: the one thing seven slots makes tedious is setting the same
 *       time five times. "Mon-Fri" does it in a tap. This is the single
 *       biggest win available without changing the data model, which is why
 *       it is here and prominent.
 *
 * WHY NOT A MODAL FOR THE EDITOR
 *   Same reason the accordion was not a modal: the week has to stay readable
 *   while you edit one day of it, because "is Thursday also set" is the
 *   question you are usually answering.
 */
import { useState } from 'react'
import { AppHeader } from '../components/AppHeader'
import { Drum, type DrumItem } from '../components/Drum'
import { Pane, Rule } from '../components/Term'
import { updateAlarm, type AlarmEntry } from '../lib/api'
import { duration } from '../lib/format'
import './Alarms.css'

const HOURS: DrumItem[] = Array.from({ length: 12 }, (_, n) => ({
  value: n + 1,
  label: String(n + 1),
}))

/** Every minute (USER DECISION 2026-10-16: 7:43 has to be settable).
 *
 *  Sixty rows is a long flick end to end, which is the cost of the decision.
 *  It is bearable because the wheel opens on the value already set, so the
 *  common edit is a nudge of a few rows -- and because the alternative, a
 *  five-minute grid, made a third of all times simply unreachable.
 *
 *  No SECONDS wheel: alarms.FIRE_WINDOW_S is 120s, so a seconds value would
 *  be decorative -- the alarm can legitimately ring up to two minutes after
 *  the time shown. Timers are the control that goes to the second. */
const MINUTES: DrumItem[] = Array.from({ length: 60 }, (_, n) => ({
  value: n,
  label: String(n).padStart(2, '0'),
}))

const MERIDIEM: DrumItem[] = [
  { value: 0, label: 'AM' },
  { value: 1, label: 'PM' },
]

/** Groups the Copy-to buttons offer. Weekday indices match Python's
 *  datetime.weekday(): 0 = Monday. */
const GROUPS: { label: string; days: number[] }[] = [
  { label: 'Mon–Fri', days: [0, 1, 2, 3, 4] },
  { label: 'Sat–Sun', days: [5, 6] },
  { label: 'All 7', days: [0, 1, 2, 3, 4, 5, 6] },
]

export function Alarms({
  alarms,
  onChanged,
}: {
  alarms: AlarmEntry[]
  onChanged: () => void
}) {
  // Opens on today, which is the slot most likely to be wanted. Falls back to
  // Monday before the first poll lands.
  const [day, setDay] = useState(() => (new Date().getDay() + 6) % 7)
  const [copied, setCopied] = useState<string | null>(null)

  const selected = alarms.find((a) => a.weekday === day)
  const enabled = alarms.filter((a) => a.enabled)

  const next = enabled
    .filter((a) => a.next_fire_in_s !== null)
    .sort((a, b) => (a.next_fire_in_s ?? 0) - (b.next_fire_in_s ?? 0))[0]

  const save = (
    weekday: number,
    values: { hour?: number; minute?: number; enabled?: boolean },
  ) => void updateAlarm(weekday, values).then(onChanged)

  /** Hour on the wheel is 1-12; the backend stores 0-23. */
  const setHour12 = (h12: number) => {
    if (!selected) return
    const pm = selected.hour >= 12
    save(day, { hour: (h12 % 12) + (pm ? 12 : 0) })
  }

  const setMeridiem = (pm: number) => {
    if (!selected) return
    const h12 = selected.hour % 12
    save(day, { hour: h12 + (pm ? 12 : 0) })
  }

  /** Copy this slot's time to a group of days, and turn those days on.
   *
   *  Enabling is part of it on purpose: "same as Monday" means you want the
   *  alarm, not a row that merely agrees about a time it will never ring at.
   *  The requests go out together and the single refresh at the end is what
   *  the panel redraws from. */
  const copyTo = async (group: { label: string; days: number[] }) => {
    if (!selected) return
    await Promise.all(
      group.days.map((weekday) =>
        updateAlarm(weekday, {
          hour: selected.hour,
          minute: selected.minute,
          enabled: true,
        }),
      ),
    )
    onChanged()
    setCopied(group.label)
    window.setTimeout(() => setCopied(null), 2000)
  }

  return (
    <main className="alarms">
      <AppHeader
        title="Alarms"
        subtitle={
          enabled.length === 0
            ? 'all off'
            : next
              ? `${enabled.length} on · next in ${duration(next.next_fire_in_s)}`
              : `${enabled.length} on`
        }
      />

      <Rule label="week" icon="calendar" />

      {/* The week. Navigation and overview in one strip: every day's time is
          legible without selecting it. */}
      <div className="week" role="tablist" aria-label="Day">
        {alarms.map((alarm, i) => (
          <button
            key={alarm.weekday}
            type="button"
            role="tab"
            aria-selected={alarm.weekday === day}
            className={`week__day themed${alarm.weekday === day ? ' is-selected' : ''}${
              alarm.enabled ? ' is-on' : ''
            }`}
            style={{ '--i': i } as React.CSSProperties}
            onClick={() => setDay(alarm.weekday)}
          >
            <span className="week__name">{alarm.day.slice(0, 3)}</span>
            <span className="week__time num">{alarm.label}</span>
            <span className="week__dot" aria-hidden />
          </button>
        ))}
      </div>

      {selected && (
        <Pane
          /* Keyed on the day, so switching days replays the entrance
             animation -- which is the cue that the editor below now refers to
             a different slot. */
          key={selected.weekday}
          title={selected.day}
          icon="bell"
          focus={selected.enabled}
          className="editor"
          meta={
            selected.enabled
              ? selected.next_fire_in_s !== null
                ? `rings in ${duration(selected.next_fire_in_s)}`
                : 'on'
              : 'off'
          }
        >
          <div className="editor__head">
            <div className="editor__state">
              <span className="editor__state-label">
                {selected.enabled ? 'enabled' : 'disabled'}
              </span>
              <span className="editor__state-time num">{selected.label}</span>
            </div>

            {/* A switch, not a checkbox: the control most likely to be hit
                with a thumb, and it has to read as on/off from a distance. */}
            <button
              type="button"
              className={`bigswitch${selected.enabled ? ' is-on' : ''}`}
              role="switch"
              aria-checked={selected.enabled}
              aria-label={`${selected.day} alarm`}
              onClick={() => save(day, { enabled: !selected.enabled })}
            >
              <span className="bigswitch__knob" />
            </button>
          </div>

          <div className="editor__wheels">
            <Drum
              items={HOURS}
              value={selected.hour % 12 === 0 ? 12 : selected.hour % 12}
              onChange={setHour12}
              ariaLabel="Hour"
            />
            <span className="editor__colon" aria-hidden>
              :
            </span>
            <Drum
              items={MINUTES}
              value={selected.minute}
              onChange={(minute) => save(day, { minute })}
              ariaLabel="Minute"
            />
            <Drum
              items={MERIDIEM}
              value={selected.hour >= 12 ? 1 : 0}
              onChange={setMeridiem}
              ariaLabel="AM or PM"
            />
          </div>

          <div className="editor__copy">
            <span className="editor__copy-label">
              {copied ? `Copied to ${copied}` : 'Copy this time to'}
            </span>
            <div className="editor__copy-btns">
              {GROUPS.map((group) => (
                <button
                  key={group.label}
                  type="button"
                  className={`editor__copy-btn${copied === group.label ? ' is-done' : ''}`}
                  onClick={() => void copyTo(group)}
                >
                  {group.label}
                </button>
              ))}
            </div>
          </div>
        </Pane>
      )}
    </main>
  )
}
