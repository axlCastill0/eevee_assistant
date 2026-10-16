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

export const ROUTES = ['dashboard', 'music'] as const
export type Route = (typeof ROUTES)[number]

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
