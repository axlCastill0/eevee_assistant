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

Target since 2026-10-19 (USER): **a terminal multiplexer, taken seriously.**
Before that it was restrained developer-tooling chrome; the brief was to stop
hedging and commit to the terminal, in red, without it becoming a hacker
costume.

What that means concretely:

- **Every surface is a framed pane** with a bracketed title in its bar, the
  way tmux labels a window. `Pane` in `components/Term.tsx`. At most one pane
  per screen is `focus`ed, which reddens its frame and tick — more than one
  and the marker means nothing.
- **State is a bracketed verdict** — `[ OK ]`, `[FAIL]`, `[WARN]` — padded to
  four characters so a column of them aligns. Colour is the second signal, not
  the only one, which is also what makes the systems page readable to someone
  who cannot tell the red from the green.
- **Progress is drawn in block characters** (`████████░░░░`), not smooth bars.
  `Meter` in `Term.tsx`. The exception is the music progress bar, which has to
  move continuously and still scales a div.
- **Dividers are real box-drawing characters**, clipped by `overflow: hidden`.
  They join seamlessly in JetBrains Mono and cost one text run. Pane frames
  stay CSS borders, which stay exactly 1px.
- **Headings are prompts**: `❯ Dashboard` with a blinking block caret, typed in
  on mount with `clip-path` + `steps()` so the reveal paints a dozen times
  rather than sixty times a second.
- **The rail is a window list.** Numbered `1 dash`, `2 music`, `3 sys`,
  `0 cfg`; the active entry inverts its number and shows a red bar. Nothing on
  this panel can type `1` — the number is what makes it read as a window list
  rather than a phone's tab bar.
- **The top bar is a status line**: segments divided by `│`, with an
  `eevee@panel:~/<route>` prompt under the clock.
- **Settings is a config file**, showing the real stored key
  (`screen_timeout_min`) rather than a sentence, with dotted leaders out to the
  control.
- **A static scanline wash** over the whole shell at 2% (`--scanline`). One
  repeating gradient, no animation, one paint.
- **Corners are nearly square** (`--radius: 3px`) and red is allowed a *static*
  glow (`--glow`), never an animated one.

Light theme is a **paper terminal**, not an inversion: warm stock, ink text,
a darker red, and no glow — bloom on paper reads as a printing fault.

Typography is split by job: **Lexend** for headings and prose, **JetBrains
Mono** for everything else including every number. Lexend has no `tnum`, so a
clock set in it would shift its digits on a wall panel; mono is also simply
what a terminal reads as.

Scaled for touch:

- Minimum target 56px (`--touch-min`); tiles are far larger and the whole tile
  is the target, not a button inside it
- No hover-only affordances — `:active` press states instead
- `touch-action: manipulation` to kill the 300ms tap delay
- Cursor hidden, text selection off, no pinch-zoom
- Detail sheet dismisses by dragging down, the gesture people actually reach
  for, so the Close button never has to be hunted

### Size

The whole type ramp was scaled up ~20% on 2026-10-19 (USER: the panel is read
from across the room) and then a further ~6% on the same day, along with
`--touch-min` (56 → 68px) and `--row-h` (68 → 86px). The ramp moved together rather than a few headings, so the
relationships the design was drawn with still hold.

That does not fit a 600px-high panel on its own, so every view has a
`@media (max-height: 680px)` block that buys the room back from **padding and
card heights, never from type**: the status line and app header tighten, page
headings drop one step, the glance and app cards lose ~30px each, and the
timer dial shrinks (it is dragged, not read). Verified at 1024x600 — the
launcher fits with no scroll, Timers keeps its Start button on screen.

### Resolution

The panel size is not yet known, so nothing is pinned to a width breakpoint:

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

Payload: 285 KB JS (88 KB gzip), 59 KB CSS (11 KB gzip), 95 KB fonts.

### Fonts

Three faces, all self-hosted — the Pi may boot before the network is up, and a
Google Fonts link would leave the panel in a fallback face. They are declared
by hand in `index.css` rather than imported, so only the latin upright subsets
ship.

| Face | Source | Size |
|---|---|---|
| Lexend Variable | npm `@fontsource-variable/lexend` | 40 KB |
| JetBrains Mono Variable | upstream release, subset by `apps/ui/scripts/fonts.py` | 43 KB |
| Symbols Nerd Font | nerd-fonts release, subset to 91 glyphs by the same script | 12 KB |

JetBrains Mono comes from the **upstream** release rather than the Google
subset because the Google latin subset drops U+2500 box drawing, and the
chrome is built out of box characters.

Icons are Nerd Font glyphs, not SVG: one `@font-face` scoped to the private
use area by `unicode-range` replaced every hand-drawn icon in the tree. Add one
by putting its upstream glyph name in `SYMBOLS` in `scripts/fonts.py` and
re-running it — the script resolves names to codepoints and regenerates
`src/fonts/glyphs.ts`, because a hand-written PUA codepoint is unverifiable by
eye and a wrong one is a blank box on the panel rather than an error anywhere.

```bash
# needs: pip install fonttools brotli
python3 apps/ui/scripts/fonts.py ~/JetBrainsMono'[wght]'.ttf ~/SymbolsNerdFontMono-Regular.ttf
```

---

## 5. Layout

The shell is a fixed rail plus one view. Chrome (clock, voice pill, status
icons) is global: it stays put when the view changes, because the clock and
the pill are the two things that must be readable whatever page is up.

```
┌────┬──────────────────────────────────────────────────────┐
│ ~$ │  8:41 ³⁷ PM            [■ READY] │ ◌ LIVE 9ms │ ⏱2 ⏻ │  status line
│EEVEE  eevee@panel:~/dashboard │ Sunday, October 4         │
│ 1  │                                                      │
│dash│                                                      │
│ 2  │                                                      │
│mus │                the active view                       │
│ 3  │                                                      │
│sys │                                                      │
│ 0  │                                                      │
│cfg │                                                      │
└────┴──────────────────────────────────────────────────────┘
  ▲
  The window rail — dash, music, sys, then cfg pinned to the bottom.
  78px targets, numbered like tmux windows.
```

The status line carries one control: a power button that blanks the screen. It is
last in the row because it is the only thing up there that hides everything
else, and because a thumb reaching the corner should not pass over the status
icons on the way. Everything else up there is **status, not control**. The theme toggle moved
to Settings on 2026-10-16 to make room for status icons: a stopwatch when
timers are running (with a count when there are several) and a bell when an
alarm is due within 24 hours. Neither is a countdown and neither is a button —
a ticking number up there would pull the eye every second on every page, and
tapping a status to navigate is a hidden affordance on a panel whose
navigation is a permanent rail two inches to the left.

The music view renders no status line at all; see below.

### Routing

Hash routing, hand-written, in `lib/useRoute.ts`. Six routes, no params, no
nested routes: react-router is ~20 KB to replace 50 lines, and every
dependency here has to survive an `npm ci` during an image build on the Pi.
The hash rather than `pushState` because a reload then never 404s, including
against the dev server.

**The rail lists destinations, not routes.** `timers` and `alarms` are real
routes — a kiosk reload has to come back to the app you were in — but they are
reached from the launcher's tiles, not from the rail, which stays four
entries. `HOME_APPS` is what keeps Dashboard lit while you are inside one; a
rail with nothing highlighted reads as "you are nowhere".

Adding a view is three edits: a `Route` in `useRoute.ts`, a branch in
`App.tsx`, and then either an entry in `Sidebar.tsx`'s `ITEMS` (a destination)
or a tile in `Home.tsx`'s `appTiles` (an app).

### Views

**Dashboard** is the default route: it is what the panel is for day to day, so
an unrecognised hash lands there rather than on the systems grid.

**Dashboard** — the launcher. A glance strip of live state over a grid of app
tiles.

```
┌──────────────────────────────────────────────────────┐
│ TIMER        │ NEXT ALARM   │ TORONTO            ☁   │
│ 13:13        │ 7:00 AM      │ 11°c                   │
│ 15 min·paused│ Mon·in 2d 14h│ overcast · feels 7°    │
├──────────────┴──────────────┴────────────────────────┤
│ ⏱            │ 🔔           │ ♫                      │
│ Timers       │ Alarms       │ Music                  │
│ 1 paused     │ 5 of 7 on    │ playing                │
├──────────────┼──────────────┴────────────────────────┤
│ ▦ Systems    │ ⚙ Settings                            │
└──────────────────────────────────────────────────────┘
```

A glance card appears only when it has something to say — timers while any
exist, the next alarm only while one is enabled, now playing only while
something is playing. **Weather is the exception and is always there**: it is
the one thing worth reading when nothing is happening, and a home screen that
empties to nothing reads as broken.

App tile icons are outline glyphs in the accent, always — not only when the
app is live (USER 2026-10-19). "Something is happening here" is carried by the
red corner tick instead, the same marker the rail uses for the active window,
and the icon floats on `margin: auto 0` so its breathing space stays even at
any tile height.

The grid holds **only apps that have no rail entry**. Music, Systems and
Settings are rail destinations; repeating them as tiles made the home screen
a second copy of the navigation rather than a home for the things with
nowhere else to live.

**Timers** and **Alarms** are apps behind those tiles, with the whole screen
each. Timers are also settable by voice; alarms are screen-only. Full feature
notes are in `docs/TIMERS_AND_ALARMS.md`.

The touch decision that shapes both: there is no keyboard on this panel and no
on-screen one wanted, so neither a text field nor Chromium's native time
picker is available. That leaves **gestures**: a two-ring duration dial you
drag (outer turn = an hour, inner turn = a minute) and scroll-snap **wheels**
for the alarm time. Both replaced `−`/`+` steppers that cost 45 taps for a
45-minute timer. The alarm editor
still **expands in place** rather than opening a modal, so the rest of the
week stays visible while one day changes.

The ringing banner is rendered by the **shell**, not by this view, so a timer
that ends while the panel is on Music still shows and is still stoppable. The
poll behind it lives in the shell for the same reason.

**Settings** — four rows now. Two are server-side (timer and alarm end sounds,
chosen from whatever is in `media/`); the theme is not, and stays in this
browser's localStorage. A theme belongs to a display — a phone opening the
dashboard can be light while the wall panel is dark — and the voice command
`set_theme` writes to that same local store.

#### Screen off

Three things blank the panel — the top-bar button, a voice command, and an
idle timeout (30 minutes by default, changeable in Settings) — and all three
write one piece of backend state (`GET/POST /screen`). The dashboard follows
it, so a voice "screen off" blanks a browser that was opened afterwards too.

Two things wake it: a touch anywhere, and **any wake-word trigger**. The
backend wakes the screen when the pipeline reports `listening`, so speaking to
a dark panel lights it up before you have finished the sentence. Deliberately
only on `listening` — waking on `speaking` too would make "turn the screen
off" switch the panel straight back on while it answered.

The veil is instant but cosmetic. The display itself is switched by
`scripts/screen-agent.sh` on the Pi, which polls that same state — see "The
screen agent" in `README_PI.md`. Without it the panel still goes black and
still wakes on touch, it is just not actually off.

Touch input keeps working with the backlight off, which is what makes
tap-to-wake possible at all.

**Systems** — the service report. A log, not a grid, since 2026-10-19: the
question this page answers is "is anything wrong", and a column of aligned
verdicts answers it in one downward glance where a grid made the eye hunt.

```
❯ Systems ▌
┌ ▌ SYSTEM ───────────────────── stale after 45s ──────┐
│ [ OK ] Everything good.                              │  Overview
│        2 services reporting healthy                  │  (backend's speech)
└──────────────────────────────────────────────────────┘
┌ ▌ SERVICES ──────────────────────────────── 2/2 up ──┐
│ [ OK ]  Backend  heartbeat 0s   ▁▁▃█  0s   ███░░░  › │  one row per
│ [FAIL]  Voice    never checked  ▃█▁▁  --  ██████   › │  service
└──────────────────────────────────────────────────────┘
updated just now │ stale after 45s │ eevee
```

Each row is still the whole touch target and still opens the detail sheet. The
block meter is heartbeat pressure: it fills as the last beat ages, so a
service drifting towards stale shows it before it gets there. The row's
columns drop in order under 1100px and 860px — the verdict, the name and the
age are the row, everything else is detail.

**Music** — Spotify now playing. Cover left, metadata and controls right, both
boxes the same size, the pair centred in both axes:

```
┌──────────────────────────────────────────────────────┐
│          ┌───────────┐   NOW PLAYING · Living Room   │
│          │           │   Everything In Its           │
│          │   cover   │   Right Place                 │
│          │           │   Radiohead                   │
│          │           │   Kid A                       │
│          └───────────┘   ▓▓▓▓░░░░░░░░░░░░░░░░░░      │
│                          0:36              4:03      │
│                          (◀◀)  ( ▶ )  (▶▶)           │
│                          SPOTIFY                      │
└──────────────────────────────────────────────────────┘
```

One custom property, `--np-size`, is both the cover's edge and the panel's
width, so the halves cannot drift apart at any panel size. The background is
built from the cover's two dominant colours; see `lib/coverColors.ts`, and
`docs/SPOTIFY.md` for the whole feature.

This view keeps its own look — full bleed, cover colours, white type. It is a
display surface rather than a pane, and the terminal chrome would only be in
front of the art. The one concession is the corner radius, which now matches
the rest of the app so the boundary at the rail is not jarring.

Two details that follow this UI's existing rules rather than being new ideas:

- the progress bar fills with `transform: scaleX()`, not `width`, because the
  only properties animated anywhere here are transform and opacity
- the background crossfades between two stacked gradient layers, for the same
  reason — a gradient cannot be transitioned, an opacity can

There is deliberately **no scrub**: the bar is a readout (USER DECISION
2026-10-16). It is also the only control that would need a drag, which is the
gesture a touch panel handles worst.

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

### Voice pill and answer dialog

The pill on the top bar is the one element here that is **not** polled. It is
pushed over a WebSocket (`/api/voice/events`) because its job is to tell you
the microphone is open so you can start talking — a 3s poll would show that an
average of 1.5s late, which is after you have already spoken.

| colour | state | meaning |
|---|---|---|
| blue | `ready` | wake word armed (`--info`, **not** `--accent`) |
| green | `listening` | mic open, talk now (dot pulses) |
| amber | `thinking` | transcribing and classifying (slower pulse) |
| red | `speaking` | the assistant has the floor |
| grey | `offline` / `unknown` | not running, or nothing heard from it yet |

Red is not an error. It is the one colour on this panel that means "do not
talk over this".

`ready` is pinned to its own `--info` token rather than following the accent.
The accent went red on 2026-10-16 (user preference) and `speaking` is already
red, so tracking the accent would have made "armed and waiting" and "I have
the floor" the same colour from across the room.

While thinking, the transcript appears beside the pill. It is the **final**
transcript, pushed the moment Whisper returns and before classification —
which on an SLM fallback is another 4-5s — so a misheard command is visible
early. There is no word-by-word streaming; see the decision table in
AGENT_CONTEXT.md.

The answer appears centre-screen in the largest type on the panel and holds for
7 seconds. If the sentence takes longer than that to speak, the dialog stays
until speech ends — hiding an answer still being read aloud would be worse than
holding it a little longer.

A reload repaints the pill from the hub's retained event but does **not**
replay the answer — the dialog ignores the first message of each connection,
which is the replayed one. The pipeline also re-sends its current state every
15s so the pill recovers by itself after a backend restart; the backend treats
an identical republish as a refresh rather than a new event, so those never
re-open the dialog.

The pill falls back to the heartbeat: a pipeline that died mid-utterance cannot
publish `ready`, so a voice service the backend reports as down overrides the
last event. The dialog deliberately does not do this — an answer arriving is
itself proof the pipeline is alive.

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

# drive the voice pill and the answer dialog without any audio hardware
for s in listening thinking speaking ready; do
  curl -s -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
    -d "{\"state\":\"$s\",\"speech\":\"Everything good.\"}" \
    -X POST http://127.0.0.1:8000/voice/state; sleep 1
done
```

```bash
npm run build       # -> dist/   (runs tsc -b strict first)
npm run typecheck
```

There is **no test suite** in this project, by decision — see `## testing` in
AGENT_CONTEXT.md. `npm run build` plus the curl commands above are the check.
One more worth doing after touching the event path: `grep -r "X-API-Key" dist/`
must find nothing.

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

4. **The Vite dev proxy does not inject headers on WebSocket upgrades.** Its
   `proxyReq` event fires for HTTP only; upgrades need a separate `proxyReqWs`
   handler. Without it the voice socket reaches the backend with no API key and
   is closed with 1008, which Chromium reports only as "WebSocket is closed
   before the connection is established". Both handlers are in
   `vite.config.ts`. nginx has no such split.

5. **The event socket has its own nginx location.** `/api/` sets
   `proxy_read_timeout 5s`, which is right for a 3s poll and fatal for a socket
   that sits idle between utterances. `location = /api/voice/events` gets
   3600s plus the `Upgrade`/`Connection` headers. The backend also sends a
   keepalive frame every 20s.

6. **The trail resets on reload.** It is client-side only. If you want real
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
- voice pill driven by the real event stream through all four colours
- transcript beside the pill while thinking
- answer dialog measured at 7001ms; a 10s "utterance" held it until speech
  ended; the same answer twice re-triggered it
- backend killed → pill dims and keeps its last colour; restarted → the socket
  reconnected by itself
- heartbeat gone stale → pill reads "Voice offline", overriding the last event
- production bundle served through an nginx-equivalent proxy
- API key absent from every served file
- no console errors

Not verified — no hardware: real touch gestures, the Docker image building
(no daemon on the dev host), Chromium kiosk, and actual framerate on a Pi.

**Home** — wake-on-LAN. One machine, one button, and a status dot that only
promises something when `WOL_HOST` is set for the backend to probe. Named in
`.env`, because there is no keyboard on this panel and a MAC address is set
once. Full notes in `AGENT_CONTEXT.md` under `## wake on lan`.

### Lyrics

A button in the top right of the music view opens a full-screen lyrics page
over the same drifting cover colours — big Lexend, the line being sung in
white, the rest dimmed, scrolled to stay centred. It follows the song from the
same interpolated `progressMs` the progress bar uses, so it needs no second
clock.

The button is **disabled whenever the track has no lyrics**, which is most of
the information it carries. Lines come from LRCLIB through
`GET /api/spotify/lyrics`; the matching rules, the statuses and the privacy
note are in `docs/SPOTIFY.md` §6b.

Two details worth keeping if this is ever rewritten:

- the hook fetches once per **track id**, not per poll, and retries while the
  answer's `track_id` does not match the track on screen — the backend's
  playback snapshot can lag a skip by up to a second, and the worst possible
  failure for this feature is the previous song's words scrolling under the
  new one
- an untimed set is not shown as if it were timed. It says `not timed ·
  scroll`, dims nothing, and is read by finger

### Motion on the Music view

Widened on 2026-10-19 (USER: more movement, and the background colours should
move too). Everything below animates `transform` only, and every loop is
**paused rather than removed** when playback stops, so the page freezes where
it is and picks the same motion back up on play. One attribute does it:
`data-playing` on `.np`.

| Layer | Motion | Period |
|---|---|---|
| `.np__cover-float` | vertical bob, ±3.4% | 8s |
| `.np__cover` | sway + perspective tilt, ±3° | 13s |
| `.np__cover-img` | breathe, scale to 1.06 | 17s |
| `.np__disc` | the record turning behind the art | 24s |
| `.np__blob--a/b` | the two cover colours drifting across the frame | 34s / 27s |
| `.np__sheen` | one conic sweep of both colours around everything | 90s |

The three cover periods are co-prime enough to realign only every ~49 minutes,
so the drift never reads as a loop. The record peeks ~7% past the cover's right
edge, which reaches into the layout gap and never under the text, and it turns
only while the track does — which makes "is this actually playing" readable
from across the room.

The soft edges are each layer's own radial fall-off. There is **no**
`filter: blur()` anywhere: a translating or rotating layer is free once
composited, where a blurred or animated gradient repaints every frame.
