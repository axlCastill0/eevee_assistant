/**
 * The view switcher.
 *
 * A rail rather than a drawer: there are two views and the panel is always
 * on, so a hamburger would hide the only navigation behind an extra tap for
 * no gain. Targets are deliberately larger than --touch-min because this is
 * the control most likely to be hit without looking.
 */
import type { Route } from '../lib/useRoute'
import { navigate } from '../lib/useRoute'
import './Sidebar.css'

interface Item {
  route: Route
  label: string
  icon: React.ReactNode
}

/* Icons are inline SVG at 24px on a 24px grid, stroke-only, so they inherit
   currentColor and need no icon package. */
const ITEMS: Item[] = [
  {
    route: 'dashboard',
    label: 'Systems',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
           strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <rect x="3" y="3" width="7.5" height="7.5" rx="1.5" />
        <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" />
        <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" />
        <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5" />
      </svg>
    ),
  },
  {
    route: 'music',
    label: 'Music',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
           strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <circle cx="7" cy="18" r="3" />
        <circle cx="18" cy="15.5" r="3" />
        <path d="M10 18V6.5l11-2v11" />
      </svg>
    ),
  },
]

export function Sidebar({ route }: { route: Route }) {
  return (
    <nav className="sidebar themed" aria-label="Views">
      <div className="sidebar__mark" aria-hidden>
        {/* The wordmark doubles as the "you are home" anchor. Not a button:
            there is nowhere above the two views to go. */}
        <span className="sidebar__mark-dot" />
      </div>

      {ITEMS.map((item) => {
        const active = route === item.route
        return (
          <button
            key={item.route}
            type="button"
            className={`sidebar__item${active ? ' is-active' : ''}`}
            aria-current={active ? 'page' : undefined}
            onClick={() => navigate(item.route)}
          >
            {/* The active marker is a separate element so switching views
                animates transform only, never a layout property. */}
            <span className="sidebar__item-icon">{item.icon}</span>
            <span className="sidebar__item-label">{item.label}</span>
          </button>
        )
      })}
    </nav>
  )
}
