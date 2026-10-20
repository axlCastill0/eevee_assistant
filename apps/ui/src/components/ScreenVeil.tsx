import './ScreenVeil.css'

/**
 * Black-out overlay for "screen off".
 *
 * Cosmetic only: this kills the picture, and scripts/screen-agent.sh on the
 * Pi kills the display itself. Both exist because the overlay is instant
 * where the agent polls, and because it still works if no agent is installed.
 *
 * Stays tappable: a touch wakes it, which beats talking to a black screen.
 */
export function ScreenVeil({ on, onDismiss }: { on: boolean; onDismiss: () => void }) {
  if (!on) return null

  return (
    <div
      className="veil"
      role="button"
      tabIndex={0}
      aria-label="Screen off. Tap to wake."
      onPointerDown={onDismiss}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onDismiss()
      }}
    >
      {/* A faint hint, far below the brightness that made the screen worth
          turning off. It fades out so a dark room goes properly dark, but it
          is there for the first few seconds when someone is still looking. */}
      <span className="veil__hint">tap to wake</span>
    </div>
  )
}
