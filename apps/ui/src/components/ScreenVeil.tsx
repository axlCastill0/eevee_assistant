import './ScreenVeil.css'

/**
 * Black-out overlay for "screen off".
 *
 * WHAT THIS IS, AND WHAT ACTUALLY KILLS THE BACKLIGHT
 *   This overlay only blacks out the picture. On its own that leaves the
 *   panel lit, which in a dark room is as bright as it ever was -- the
 *   complaint that prompted the real fix on 2026-10-16.
 *
 *   The backlight is switched by `scripts/screen-agent.sh`, which runs on the
 *   Pi outside Docker (neither a browser nor a container can reach the
 *   device) and follows `GET /screen`. This veil still exists because it is
 *   instant where the agent polls: the picture goes black immediately and the
 *   backlight follows within a couple of seconds. It also covers the case
 *   where no agent is installed, which is how this behaved before.
 *
 * It stays tappable on purpose: the assistant is still listening and "wake up"
 * works, but a touch is faster and nobody should have to talk to a black
 * screen to get it back.
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
