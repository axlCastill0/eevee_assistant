import type { VoiceState } from '../lib/useVoiceEvents'
import './VoicePill.css'

/** Colour and wording per state. The colours are the status tokens already in
 *  index.css, not new ones — the pill must read the same as the service tiles.
 *    ready     blue   (--accent)  the wake word is armed
 *    listening green  (--ok)      the mic is open, talk now
 *    thinking  amber  (--warn)    transcribing / classifying
 *    speaking  red    (--down)    the assistant has the floor
 *  Red is not an error here. It is borrowed deliberately: it is the one colour
 *  on this panel that means "do not talk over this". */
const LABELS: Record<VoiceState, string> = {
  ready: 'Ready',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
  offline: 'Voice offline',
  unknown: 'Voice unknown',
}

export function VoicePill({
  state,
  transcript,
  connected,
}: {
  state: VoiceState
  transcript: string | null
  connected: boolean
}) {
  // The transcript belongs next to the pill, not in the answer dialog: its
  // purpose is to let you catch a misheard command while the answer is still
  // being worked out. Once the assistant starts speaking it stops being
  // actionable, so it is only shown through the thinking stage.
  const showTranscript = state === 'thinking' && !!transcript

  return (
    <div
      className="voicepill"
      data-state={state}
      /* The socket being down is not a voice state, so it is a separate
         attribute: the pill keeps its last known colour but goes dim, which
         reads as "possibly stale" rather than inventing a status. */
      data-stale={!connected || undefined}
      role="status"
      aria-live="polite"
    >
      <span className="voicepill__dot" aria-hidden />
      <span className="voicepill__label">{LABELS[state]}</span>

      {showTranscript && (
        <span className="voicepill__transcript" title={transcript ?? undefined}>
          &ldquo;{transcript}&rdquo;
        </span>
      )}
    </div>
  )
}
