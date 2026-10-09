import { useEffect, useRef, useState } from 'react'
import './VoiceDialog.css'

/** How long the answer stays up once it has appeared. */
const HOLD_MS = 7000

/**
 * The answer, big enough to read from across the room, for 7 seconds.
 *
 * TIMING RULE (user spec, plus one correction):
 *   it appears the instant the assistant starts speaking and holds for 7s. If
 *   the sentence takes longer than 7s to speak, the dialog stays until speech
 *   ends — hiding an answer that is still being read aloud would be worse than
 *   holding it a little longer.
 */
export function VoiceDialog({
  speech,
  seq,
  speaking,
  retained,
}: {
  /** The sentence being spoken, from the latest 'speaking' event. */
  speech: string | null
  /** Event sequence number. This is what distinguishes a new answer from a
   *  re-render of the same one, so asking the same question twice re-triggers
   *  the dialog instead of silently reusing a timer that already expired. */
  seq: number
  /** Whether the pipeline is still in the speaking state. */
  speaking: boolean
  /** True when this event is the hub's replayed state rather than something
   *  that just happened. A reload must repaint the pill without re-announcing
   *  an answer that may be hours old. */
  retained: boolean
}) {
  const [shown, setShown] = useState<{ text: string; seq: number } | null>(null)
  // Separate from `shown` so the hold can expire while speech continues: the
  // dialog hides only when both the timer has run out AND speaking has ended.
  const [held, setHeld] = useState(false)
  const lastSeq = useRef(0)

  // 1. Latch a new answer. Only `seq` advancing counts, so asking the same
  //    question twice re-triggers the dialog instead of being swallowed as an
  //    unchanged prop.
  useEffect(() => {
    if (!speaking || !speech) return
    if (seq === lastSeq.current) return

    lastSeq.current = seq
    // Consumed, not shown: claiming it as seen stops a later re-render from
    // treating the same replayed answer as new.
    if (retained) return

    setShown({ text: speech, seq })
    setHeld(true)
  }, [speech, seq, speaking, retained])

  // 2. Run the hold. This is deliberately its own effect, keyed ONLY on which
  //    answer is showing. Putting the timer in the effect above meant React
  //    ran its cleanup when `speaking` flipped to false — clearing the timer
  //    without re-arming it, so the dialog stayed up forever. Found exactly
  //    that way on 2026-10-08.
  const shownSeq = shown?.seq ?? null
  useEffect(() => {
    if (shownSeq === null) return

    const timer = window.setTimeout(() => setHeld(false), HOLD_MS)
    return () => window.clearTimeout(timer)
  }, [shownSeq])

  // 3. Dismiss once the hold has expired and the assistant has stopped
  //    talking. A sentence longer than 7s keeps its dialog until it ends.
  useEffect(() => {
    if (!shown) return
    if (held || speaking) return
    setShown(null)
  }, [held, speaking, shown])

  if (!shown) return null

  return (
    <div
      className="voicedialog"
      // key on seq so a second answer restarts the entrance animation rather
      // than swapping text inside a dialog that is already settled.
      key={shown.seq}
      role="status"
      aria-live="assertive"
    >
      <div className="voicedialog__card themed">
        <p className="voicedialog__text">{shown.text}</p>

        {/* Elapsed-time bar. On a panel with no input, this is what tells you
            the dialog is going to leave on its own rather than being stuck.
            It is a transform animation on a single element, so it costs the
            compositor and nothing else. The bar runs for HOLD_MS regardless of
            how long speech actually lasts; it reports the hold, not the TTS. */}
        <div className="voicedialog__bar" aria-hidden>
          <span className="voicedialog__bar-fill" />
        </div>
      </div>
    </div>
  )
}
