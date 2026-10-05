# Dashboard

Room control panel for the home system. Runs fullscreen in Chromium kiosk on a
Raspberry Pi 5 under i3, on a ~10" touchscreen.

Stack: **Vite + React + TypeScript**, built to static files, served by **nginx**
which also reverse-proxies the API.

---

## 1. Why this shape

### Static build, no Node runtime

There is one viewer, no SEO, and all data is live-polled. SSR would buy nothing
and would cost a Node process sitting next to a 1.2 GB language model and
Chromium on a 4-core board. The runtime is nginx plus a directory of files.

### nginx exists for the API key

This is the deciding constraint. The browser must not hold the shared secret.
nginx attaches it server-side:

```
browser ──GET /api/services (no key)──> nginx ──+ X-API-Key──> FastAPI
```

Verified: `grep -r "<key>" dist/` finds nothing, and the bundle's only API
reference is the literal string `/api`.

### The dashboard is a separate container from the API

Its job includes reporting that the backend is down. If FastAPI served the
bundle, a dead backend would mean a blank screen — exactly when you most need
to see something. Same reasoning as the voice container: no `depends_on`.

---

## 2. Theme

Three modes, persisted in `localStorage`:

| Mode | Behaviour |
|---|---|
| Light | forced |
| Dark | forced |
| Auto | light 08:00–17:59, dark 18:00–07:59 |

Two things that are easy to get wrong on a kiosk, both handled in
`src/lib/useTheme.ts`:

- **Auto re-evaluates on a timer.** The panel runs for months without a reload,
  so a one-shot check at mount would leave it in the wrong theme until
  something re-rendered. A timeout is scheduled for the next boundary.
- **The Pi has no RTC.** Before NTP syncs, `new Date()` can read 1970. Auto
  would then pick a theme from a bogus hour. If the year looks implausible the
  UI holds **dark** (a surprise white screen at 3am is worse than the reverse),
  shows `clock not synced` under the toggle, and re-checks every 15s.

Boundaries are `DAY_START` / `DAY_END` in that file.

The clock reads 12-hour with an AM/PM suffix, matching the backend's spoken
format (`intents.get_time` uses `%-I:%M %p`), so the panel and the voice
assistant report the same wall time the same way. The hour is not zero-padded;
minutes and seconds are.

---

## 3. Design notes

Target: modern developer tooling — Linear, Vercel, Raycast. Restrained neutral
surfaces, one accent, hairline borders, monospace with tabular figures for
every number, short decisive easing. Explicitly not a terminal or a sci-fi HUD.

Scaled for touch:

- Minimum target 56px (`--touch-min`); tiles are far larger and the whole tile
  is the target, not a button inside it
- No hover-only affordances — `:active` press states instead
- `touch-action: manipulation` to kill the 300ms tap delay
- Cursor hidden, text selection off, no pinch-zoom
- Detail sheet dismisses by dragging down, the gesture people actually reach
  for, so the Close button never has to be hunted

### Resolution

The panel size is not yet known, so nothing is pinned to a breakpoint:

- every type size is a `clamp()` between a 1024x600 floor and a 1920x1200 ceiling
- the tile grid is `auto-fit` + `minmax`, so services reflow by available width
- a `max-height: 700px` compact mode trims the hero, clock and tile padding —
  verified at 1024x600, where the full-size layout clipped

---

## 4. Pi performance rules

These are enforced throughout and are the reason the UI looks the way it does:

1. **No `backdrop-filter` anywhere.** Frosted glass is the obvious trend choice
   and the single most expensive thing this GPU can be asked to do — per-frame
   blur over a large area. The visual weight it would have provided comes from
   static gradients and a status rail instead.
2. **Animate only `transform` and `opacity`.** Both stay on the compositor.
   Nothing animates `width`, `top`, `box-shadow` or `filter`.
3. **Shadows are static.** Declared, never transitioned.
4. **The poll ring is pure CSS.** A React-driven progress indicator would
   re-render the tree many times a second; this loops without React involved.
5. `prefers-reduced-motion` disables everything — also a one-line escape hatch
   if the Pi turns out slower than expected.

Payload: 239 KB JS (74 KB gzip), 18 KB CSS (4 KB gzip), 89 KB fonts.

Fonts are self-hosted and latin-subset only. The full `@fontsource` packages
ship Cyrillic, Greek and Vietnamese — about 150 KB this panel would download
and never render. They are declared by hand in `index.css` rather than
imported, because the package has no per-subset entrypoint. Self-hosting
matters because the Pi may boot before the network is up; a Google Fonts link
would leave the dashboard in a fallback face.

---

## 5. Layout

```
┌──────────────────────────────────────────────────────┐
│  8:41 ³⁷ PM      [live 9ms]  [Light|Dark|Auto]       │  TopBar
│  Sunday, October 4                                    │
├──────────────────────────────────────────────────────┤
│ ▌ SYSTEM                                             │  Overview
│   Everything good.                                   │  (backend's own
│   2 services reporting healthy                       │   speech string)
├─────────────┬─────────────┬──────────────────────────┤
│ ● Backend  ›│ ● Voice    ›│                          │
│ Healthy     │ Healthy     │          +               │  ServiceTile grid
│ 0s   45s    │ 5s   45s    │  More systems land here  │
│ ▁▁▃█████    │ ▁▃███▁██    │                          │
├─────────────┴─────────────┴──────────────────────────┤
│ eevee │ updated just now │ stale after 45s           │  footer
└──────────────────────────────────────────────────────┘
```

The headline reuses the backend's `speech` field — the same sentence the voice
assistant says aloud. The panel and the assistant cannot disagree, because
there is one place that phrases it.

Tiles show:
- **Heartbeat trail** — one bar per poll, full height healthy, stub down.
  Bars not a line, because health is binary and a line implies interpolation
  that did not happen. Labelled "since load": the backend reports current
  state only, so this history is accumulated client-side and does not survive
  a reload. The UI says so rather than implying persisted uptime.
- **Pressure bar** along the bottom, filling as the last heartbeat ages toward
  `stale_after_s`. Past 60% the dot and bar turn amber — you see a service
  drifting before it is marked down.

Tap a tile for the detail sheet: last heartbeat, stale threshold, uptime since
load, sample count, and a longer trail.

---

## 6. Development

```bash
cd apps/ui
npm install
cp .env.example .env.local      # set VITE_DEV_API_KEY to match the backend
npm run dev                     # http://127.0.0.1:5173
```

The Vite dev server proxies `/api` and injects the key the same way nginx does,
so dev behaves like production. Those vars are read in the dev server process
and are **not** compiled into the bundle — do not rename them to something
Vite would inline at build time.

Run the backend alongside:

```bash
cd apps/backend && uvicorn main:app --port 8000
```

Useful for exercising states:

```bash
# flip voice healthy
curl -H "X-API-Key: $API_KEY" -X POST http://127.0.0.1:8000/voice/heartbeat

# watch it go stale (default 45s), or shorten the window
SERVICE_STALE_AFTER_S=5 uvicorn main:app --port 8000
```

```bash
npm run build       # -> dist/
npm run typecheck
```

---

## 7. Deployment

```bash
cd infra/docker
docker compose up --build -d ui
```

Serves on **port 8080** (unprivileged). Needs `API_KEY` in `infra/docker/.env`;
compose fails fast with a message if it is missing.

### Chromium kiosk

In the i3 config:

```
exec --no-startup-id chromium-browser \
  --kiosk http://127.0.0.1:8080 \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --check-for-update-interval=31536000 \
  --password-store=basic \
  --autoplay-policy=no-user-gesture-required
```

Also worth doing on the Pi:

```bash
xset s off -dpms       # stop the screen blanking
unclutter -idle 0 &    # belt and braces; the CSS already hides the cursor
```

---

## 8. Gotchas

1. **`NGINX_ENVSUBST_FILTER` is mandatory.** The nginx image runs `envsubst`
   over the config template using every environment variable. Without the
   filter it also expands nginx's own `$host` and `$uri`, which are not set in
   the environment, producing `proxy_set_header Host ;` — a syntax error that
   stops nginx booting. Verified both ways; the filter is set in the Dockerfile.

2. **A gateway 5xx is not a backend error.** nginx returns 502 when it cannot
   reach FastAPI. The UI reports that as "Backend unreachable", not "returned
   502", so you are not sent reading backend logs that were never written. The
   Vite dev proxy uses 500 for the same condition, so in `npm run dev` only, a
   dead backend reads as "Backend error".

3. **The theme flash on cold boot** is prevented by an inline `<style>` in
   `index.html` painting the background before the CSS bundle loads. If you
   change `--bg`, change that inline rule and the `theme-color` meta too.

4. **The trail resets on reload.** It is client-side only. If you want real
   uptime history it has to be persisted server-side — see the backlog note in
   AGENT_CONTEXT.md.

---

## 9. Verified

On a macOS dev host, against the real backend, at 1280x800 and 1024x600:

- healthy state, down state, mixed state
- live transition: voice down → heartbeat → "Everything good."
- near-stale amber warning at 36s of a 45s window
- backend killed mid-session → "retrying (n)", paused ring, stale badge, last
  known values retained
- cold load with no backend → "Backend unreachable" (the case that justifies
  the separate container)
- all three theme modes; auto correctly resolved to dark at 8:41 PM; choice
  persisted across reload
- detail sheet open and dismiss
- production bundle served through an nginx-equivalent proxy
- API key absent from every served file
- no console errors

Not verified — no hardware: real touch gestures, the Docker image building
(no daemon on the dev host), Chromium kiosk, and actual framerate on a Pi.
