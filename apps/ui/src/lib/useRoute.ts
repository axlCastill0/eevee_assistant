/**
 * Hash routing, by hand.
 *
 * WHY NOT react-router
 *   A handful of views, no params, no nested routes, no data loaders. The
 *   library is ~20 KB over the wire to replace the 50 lines below, and every
 *   dependency here has to survive an `npm ci` on the Pi during an image
 *   build.
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
//
// `timers` and `alarms` are APPS launched from the dashboard, not rail
// entries: the sidebar stays as it is (USER DECISION 2026-10-16) and the home
// screen is the launcher. They still get real routes rather than view state
// inside Home, because the kiosk reloads and a reload has to come back to the
// app you were in.
export const ROUTES = [
  'dashboard',
  'timers',
  'alarms',
  'training',
  'wake',
  'music',
  'systems',
  'settings',
] as const
export type Route = (typeof ROUTES)[number]

// The launcher: an unrecognised hash lands somewhere with a way onward.
const DEFAULT: Route = 'dashboard'

/** Apps that live behind the Dashboard tile. The sidebar uses this to keep
 *  Dashboard lit while you are inside one. */
export const HOME_APPS: readonly Route[] = ['timers', 'alarms', 'training', 'wake']

function parse(hash: string): Route {
  const name = hash.replace(/^#\/?/, '').split('?')[0]
  return (ROUTES as readonly string[]).includes(name) ? (name as Route) : DEFAULT
}

export function navigate(route: Route) {
  if (parse(window.location.hash) !== route) window.location.hash = `#/${route}`
}

/** Back out of an app to the launcher. A function of its own rather than
 *  history.back(): the kiosk may have been pointed straight at `#/timers`,
 *  where there is no previous entry to go back to. */
export function goHome() {
  navigate(DEFAULT)
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
