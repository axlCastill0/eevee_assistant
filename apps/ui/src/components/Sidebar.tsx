/**
 * The view switcher, as a multiplexer's window list.
 *
 * A rail rather than a drawer: there are a handful of views and the panel is
 * always on, so a hamburger would hide the only navigation behind an extra
 * tap for no gain. Targets are deliberately larger than --touch-min because
 * this is the control most likely to be hit without looking.
 *
 * Each entry carries a NUMBER, the way tmux numbers windows. Nothing on this
 * panel can type `1`, so the number is not a shortcut -- it is the thing that
 * makes the rail read as a window list rather than as a phone's tab bar, and
 * it gives the active window somewhere to show itself other than the label.
 *
 * The rail lists DESTINATIONS, not every route. Timers, alarms and the wake
 * app are launched from the dashboard (USER DECISION 2026-10-16) and light
 * the dashboard entry while open.
 */
import type { GlyphName } from '../fonts/glyphs'
import type { Route } from '../lib/useRoute'
import { HOME_APPS, navigate } from '../lib/useRoute'
import { Icon } from './Term'
import './Sidebar.css'

interface Item {
  route: Route
  key: string
  label: string
  icon: GlyphName
}

const ITEMS: Item[] = [
  { route: 'dashboard', key: '1', label: 'dash', icon: 'dashboard' },
  { route: 'music', key: '2', label: 'music', icon: 'music' },
  { route: 'systems', key: '3', label: 'sys', icon: 'server' },
]

/* Settings sits apart, at the bottom: it is configuration, not a place you go
   to look at something. Window 0, as the odd one out. */
const FOOTER_ITEMS: Item[] = [
  { route: 'settings', key: '0', label: 'cfg', icon: 'settings' },
]

function RailButton({ item, route }: { item: Item; route: Route }) {
  const active =
    route === item.route ||
    (item.route === 'dashboard' && HOME_APPS.includes(route))

  return (
    <button
      type="button"
      className={`rail__item${active ? ' is-active' : ''}`}
      aria-current={active ? 'page' : undefined}
      onClick={() => navigate(item.route)}
    >
      <span className="rail__bar" aria-hidden />
      <span className="rail__key" aria-hidden>
        {item.key}
      </span>
      <Icon name={item.icon} className="rail__icon" />
      <span className="rail__label">{item.label}</span>
    </button>
  )
}

export function Sidebar({ route }: { route: Route }) {
  return (
    <nav className="rail themed" aria-label="Views">
      <div className="rail__mark" aria-hidden>
        <span className="rail__mark-prompt">~$</span>
        <span className="rail__mark-name">eevee</span>
      </div>

      {ITEMS.map((item) => (
        <RailButton key={item.route} item={item} route={route} />
      ))}

      <div className="rail__spacer" />

      {FOOTER_ITEMS.map((item) => (
        <RailButton key={item.route} item={item} route={route} />
      ))}
    </nav>
  )
}
