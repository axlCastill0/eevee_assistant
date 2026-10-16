/**
 * What happens when a timer or an alarm goes off.
 *
 * AUDIO LIVES IN THE BROWSER (USER DECISION 2026-10-16)
 *   The kiosk plays the mp3 itself, rather than the backend shelling out to a
 *   player. The voice container owns the speaker through ALSA and its loop is
 *   single-threaded, so a three-minute song played there would deafen the
 *   wake word for its whole duration. Chromium mixes alongside it instead.
 *
 * IT STOPS ON PURPOSE, OR WHEN THE SONG ENDS
 *   Nothing fades it out on a timer of its own: a song that has been ignored
 *   is not a song that has been dealt with. `ended` reports to the backend
 *   exactly like the Stop button does, because both mean the same thing.
 *
 * AUTOPLAY
 *   Chromium blocks audio with no user gesture unless the kiosk is launched
 *   with --autoplay-policy=no-user-gesture-required (see docs/README_PI.md).
 *   If play() is rejected anyway, the banner says so and becomes the gesture:
 *   tapping it starts the sound. The alarm is still visible and still
 *   stoppable either way, which is the part that must not depend on a flag.
 */
import { useEffect, useRef, useState } from 'react'
import { soundUrl, type AlarmEntry, type TimerEntry } from '../lib/api'
import './RingingBanner.css'

export function RingingBanner({
  timers,
  alarm,
  timerSound,
  alarmSound,
  onStopTimers,
  onStopAlarm,
}: {
  timers: TimerEntry[]
  alarm: AlarmEntry | null
  timerSound: string
  alarmSound: string
  onStopTimers: () => void
  onStopAlarm: () => void
}) {
  const audio = useRef<HTMLAudioElement | null>(null)
  const [blocked, setBlocked] = useState(false)

  // The alarm wins if both go off at once: it is the one with a wall-clock
  // commitment behind it.
  const kind = alarm ? 'alarm' : timers.length > 0 ? 'timer' : null
  const file = kind === 'alarm' ? alarmSound : timerSound
  const stop = kind === 'alarm' ? onStopAlarm : onStopTimers

  // The effect below must depend ONLY on what identifies the sound. `stop` is
  // a fresh closure on every render and this component re-renders on every
  // poll, so depending on it tore the <audio> element down and rebuilt it
  // about once a second: each play() was interrupted by its own cleanup,
  // which rejects, which looked exactly like an autoplay block. The banner
  // flickered a Play button and nothing was ever audible.
  // Seen on the Pi 2026-10-16. Keep the callback in a ref instead.
  const stopRef = useRef(stop)
  useEffect(() => {
    stopRef.current = stop
  }, [stop])

  useEffect(() => {
    if (!kind || !file) return

    const element = new Audio(soundUrl(file))
    audio.current = element
    // One play-through, then the ringing is over by itself. Looping would
    // mean an alarm nobody is home for plays until the Pi is unplugged.
    element.loop = false

    const onEnded = () => stopRef.current()
    element.addEventListener('ended', onEnded)

    let cancelled = false
    element.play().then(
      () => {
        if (!cancelled) setBlocked(false)
      },
      (err: unknown) => {
        if (cancelled) return
        // Only a real policy refusal should offer the tap-to-play button.
        // An AbortError means something interrupted the play() -- a teardown,
        // or a second play() racing it -- and showing "tap to play" for that
        // is how the flicker above presented itself.
        const name = err instanceof DOMException ? err.name : ''
        setBlocked(name === 'NotAllowedError')
        if (name !== 'NotAllowedError') {
          console.warn('Ringing sound could not start:', err)
        }
      },
    )

    return () => {
      cancelled = true
      element.removeEventListener('ended', onEnded)
      element.pause()
      element.currentTime = 0
      audio.current = null
      // Clear it here rather than during render: the next play() sets it
      // correctly, and `cancelled` stops this teardown's own rejection from
      // racing that.
      setBlocked(false)
    }
    // IDENTITY OF THE SOUND ONLY. Nothing else belongs in here.
  }, [kind, file])

  if (!kind) return null

  const title = kind === 'alarm' ? `${alarm?.day} alarm` : 'Timer finished'
  const detail =
    kind === 'alarm'
      ? alarm?.label
      : timers.map((t) => t.label).join(', ')

  return (
    <div className={`ringing ringing--${kind}`} role="alert">
      <div className="ringing__text">
        <div className="ringing__title">{title}</div>
        <div className="ringing__detail">
          {detail}
          {!file && ' · no sound chosen in Settings'}
          {blocked && file && ' · tap to play the sound'}
        </div>
      </div>

      {blocked && file && (
        <button
          type="button"
          className="ringing__btn"
          onClick={() => {
            void audio.current?.play().then(() => setBlocked(false))
          }}
        >
          Play
        </button>
      )}

      <button type="button" className="ringing__btn ringing__btn--stop" onClick={stop}>
        Stop
      </button>
    </div>
  )
}
