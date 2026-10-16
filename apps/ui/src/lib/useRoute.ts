/**
 * Hash routing, by hand.
 *
 * WHY NOT react-router
 *   Two views, no params, no nested routes, no data loaders. The library is
 *   ~20 KB over the wire to replace the 30 lines below, and every dependency
 *   here has to survive an `npm ci` on the Pi during an image build.
 *
 * WHY THE HASH AND NOT history.pushState
 *   nginx already falls back to index.html, so paths would work -- but the
 *   hash also survives the kiosk being pointed at the bare origin, and it
 *   means a reload never 404s against a dev server either. Nothing links to
 *   this UI from outside, so clean URLs buy nothing.
 */
import { useEffect, useState } from 'react'

// Order here is only the valid set; the sidebar decides what the rail looks
// like. `dashboard` is first because it is the default route.
export const ROUTES = ['dashboard', 'music', 'systems', 'settings'] as const
export type Route = (typeof ROUTES)[number]

// Timers and alarms are what the panel is for day to day, so an unrecognised
// hash lands there rather than on the systems grid.
const DEFAULT: Route = 'dashboard'

function parse(hash: string): Route {
  const name = hash.replace(/^#\/?/, '').split('?')[0]
  return (ROUTES as readonly string[]).includes(name) ? (name as Route) : DEFAULT
}

export function navigate(route: Route) {
  if (parse(window.location.hash) !== route) window.location.hash = `#/${route}`
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash))

  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  return route
}
