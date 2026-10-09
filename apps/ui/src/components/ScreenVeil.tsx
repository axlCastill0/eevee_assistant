import './ScreenVeil.css'

/**
 * Black-out overlay for "screen off".
 *
 * WHAT THIS IS NOT
 *   It does not power the display down. A browser cannot do that, and the
 *   backend runs in a container with no access to the host's compositor. What
 *   it does is kill the light coming off a panel that is otherwise bright
 *   enough to notice from across a dark room, which is what "turn the screen
 *   off" actually means to the person saying it at night.
 *
 *   True DPMS power-off needs a helper on the host (`wlopm --off \\*` under
 *   labwc, or `xset dpms force off` under X11) and something to call it. That
 *   is a worthwhile upgrade; this is the version that works today with no new
 *   privileges.
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
