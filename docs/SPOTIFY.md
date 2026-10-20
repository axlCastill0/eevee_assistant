# Spotify — Now Playing panel

The Music view shows what is playing on your Spotify account and gives you
previous / play-pause / next. The progress bar is a readout: there is no
scrubbing, on purpose.

Everything below is done once. After it, the Pi stays connected across
reboots and container rebuilds.

---

## 0. What you need, and what will not work

| | |
|---|---|
| Read what is playing | any Spotify account, free included |
| Play / pause / skip | **Spotify Premium only** |
| Anything at all | an **active device** — see below |

**The Web API is a remote control, not a player.** It can only act on a
playback session that already exists. If nothing is playing anywhere on your
account, the controls return `no_device` and the panel says so — that is not a
bug, and there is no setting that changes it. Two ways to always have a
device:

- start playback from your phone or desktop, then control it from the Pi; or
- run a Spotify Connect client **on** the Pi (`raspotify` / `librespot`), which
  makes the Pi itself a device you can transfer playback to. That is a separate
  install, and it will want the same `eeveespk` ALSA card the voice pipeline
  uses — see "Lock the devices in place" in `README_PI.md` before you point two
  things at one speaker.

---

## 1. Register an app with Spotify

1. Go to <https://developer.spotify.com/dashboard> and log in.
2. **Create app**. Name and description are yours; nothing is published.
3. Set the **Redirect URI** to exactly:

   ```
   http://127.0.0.1:8000/spotify/callback
   ```

   Exactly, character for character — Spotify compares the whole string.
   `localhost` is **not** accepted any more; it must be the loopback IP. If you
   put the backend somewhere other than port 8000, change it here and set
   `SPOTIFY_REDIRECT_URI` to match in step 2.
4. Select the **Web API** checkbox, save, then open **Settings** and copy the
   **Client ID** and **Client secret**.

Your app starts in development mode, which is capped at 25 users. That is
irrelevant for a personal panel and needs no extension request.

---

## 2. Configure the backend

In `infra/docker/.env`:

```ini
SPOTIFY_CLIENT_ID=<client id from the dashboard>
SPOTIFY_CLIENT_SECRET=<client secret from the dashboard>

# Only if you changed the redirect URI in step 1.
#SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/spotify/callback
```

The secret stays on the backend. It is never sent to the browser, and the
dashboard bundle has no Spotify credentials in it at all.

Then rebuild and restart:

```bash
cd infra/docker && docker compose up -d --build backend ui
```

The backend now mounts `./state` (repo root) at `/app/state`, which is where
the refresh token lands. It is gitignored. If that directory is missing or
read-only, the backend logs `Could not persist Spotify tokens` and you will
have to re-authorize after every restart.

---

## 3. Connect your account

The consent screen has to open in a browser, and Spotify will redirect that
browser to `127.0.0.1:8000` — which means the browser must be **on the Pi**, or
tunnelled to it. Pick whichever fits.

### A. From the Pi's own screen (simplest)

Open the dashboard, go to **Music**, tap **Open Spotify login**, approve. The
redirect lands back on the Pi's own backend and you get a "Spotify connected"
page. Navigate back to the dashboard.

### B. Over SSH, from your laptop (no touching the kiosk)

```bash
ssh -L 8000:127.0.0.1:8000 tako@takoserv
```

The tunnel is what makes the redirect work: `127.0.0.1:8000` in the laptop's
browser now *is* the Pi's backend.

`bind [127.0.0.1]:8000: Address already in use` means something on the
**laptop** already holds that port — usually a tunnel left over from a previous
attempt. The local port cannot be changed, because it has to match the
registered redirect URI, so free it:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN     # what is holding it
pkill -f 'ssh -L 8000'               # if it is an old tunnel
```

Get the authorize URL from the Pi, through nginx, which adds the API key for
you — open this in the laptop's browser:

```
http://<pi-address>:8080/api/spotify/login
```

Copy the `authorize_url` out of the JSON, open it, approve. The redirect goes
down the tunnel and you land on "Spotify connected".

### C. No tunnel: paste the code by hand

**This is the one to use if the Pi has no keyboard and the kiosk hides the
address bar.** Everything happens on your laptop, which has both.

On the laptop, open `http://<pi-address>:8080/api/spotify/login`, copy the
`authorize_url`, open it, approve. The browser then fails to load a
`127.0.0.1:8000/spotify/callback?code=...` page — expected, nothing is
listening there on the laptop. The code is in the laptop's address bar. Copy
it and post it to the Pi:

```bash
curl -X POST http://<pi-address>:8080/api/spotify/code \
  -H 'Content-Type: application/json' \
  -d '{"code":"<the code from the address bar>"}'
```

Codes are single-use and expire in about a minute, so do this promptly.

### Confirming it worked

```bash
curl -s http://<pi-address>:8080/api/spotify/status
```

`{"configured": true, "connected": true, ...}`. The Music view picks it up
within a second or two by itself.

---

## 4. Scopes

Three, and no more than the four controls need:

| Scope | For |
|---|---|
| `user-read-playback-state` | what is playing, on which device |
| `user-read-currently-playing` | the track itself |
| `user-modify-playback-state` | previous / play / pause / next |

Adding a scope later (volume, shuffle, a queue view) means re-authorizing —
`show_dialog=true` is set so the consent screen always reappears rather than
silently reusing the old grant.

---

## 5. How it fits together

```
 Spotify Web API
        ▲  one request every 3s while playing, 10s when not
        │
   backend/spotify.py          TTL cache + token refresh
        ▲
        │  /api/spotify/now-playing   (polled 1x/sec — hits the cache)
        │  /api/spotify/command       (previous | play | pause | toggle | next)
        │  /api/spotify/art/<id>      (cover, proxied)
        │
   nginx (adds X-API-Key)
        ▲
        │
   dashboard — views/NowPlaying.tsx
```

Points worth knowing:

- **The UI polls the backend, not Spotify.** Spotify sees one request every few
  seconds no matter how many dashboards are open, because the backend holds the
  snapshot. The UI's 1 Hz poll is a localhost call served from that cache.
- **No background poller.** The snapshot refreshes inside whichever request
  finds it stale, so a dashboard nobody is looking at costs Spotify nothing.
  Same shape as `weather.py`.
- **The progress bar is interpolated**, advanced locally from the server's
  `fetched_at` between samples. That is why it moves smoothly on a 1 Hz poll
  and why it does not jump backwards when a response is slow.
- **Cover art is proxied** through `/api/spotify/art/<id>`. Three reasons: the
  kiosk needs no direct access to Spotify's CDN, the image is same-origin so
  the page can read its pixels to pick the background colours, and covers are
  immutable so they cache for a year.
- **The background is the cover's two dominant colours**, extracted on a 32x32
  canvas (`lib/coverColors.ts`). A monochrome cover has its second colour
  derived from the first rather than falling back to a flat wash.

---

## 5b. Voice commands

Added 2026-10-16. Five intents, all of them fast-path matched so they answer
in about a second instead of paying the SLM's ~4 s:

| Say | Does |
|---|---|
| "play", "resume", "music on" | resumes, and names the track if it knows it |
| "pause", "stop the music" | pauses |
| "next", "skip", "skip this song" | next track |
| "previous", "go back", "last song" | previous track |
| "play it again", "start it over", "restart" | restarts the current song |

"Restart" is a **seek to zero**, not the previous-track call: Spotify's
`/previous` is device-dependent — some clients restart the current song when
you are a few seconds in, others always step back one — and "play it again"
should never be a coin flip.

Every Spotify failure gets its own spoken sentence, because they need
opposite reactions from whoever is standing there:

| Spotify says | The assistant says |
|---|---|
| no active device | "Nothing's playing. Start something on Spotify first and I can take it from there." |
| 403, free account | "Spotify only lets Premium accounts control playback…" |
| not connected | "Spotify isn't connected. You can link it on the dashboard's music page." |
| no credentials | "Spotify isn't set up on this machine yet." |
| 429 | "Spotify's asking me to slow down. Try again in a moment." |
| unreachable | "I can't reach Spotify." |

One special case worth knowing: pausing something **already paused** returns
403 from Spotify, which is the same code a free account gets for any write.
The handler re-checks playback state before believing it, so "pause" on
paused music says "Already paused" rather than sending you off to check your
subscription.

Skips deliberately do **not** announce the new track: Spotify needs a beat to
settle after a skip, and asking immediately returns the song you just left —
the assistant would confidently name the wrong thing.

**New intents need the voice container restarted**, because it fetches the
catalogue once at startup:

```bash
cd infra/docker && docker compose restart voice
```

---

## 6. Routes

All under `/spotify`, all requiring `X-API-Key` **except the callback**:

| Route | Does |
|---|---|
| `GET /now-playing` | the snapshot. Always 200; read `status` |
| `GET /lyrics` | lyrics for whatever is playing. Always 200; read `status` |
| `POST /command` | `{"action": "previous\|play\|pause\|toggle\|next"}` |
| `GET /art/{id}` | one cover image |
| `GET /status` | configured? connected? |
| `GET /login` | mints the authorize URL (and a single-use state) |
| `POST /code` | finish authorization with a pasted code |
| `POST /disconnect` | forget the stored tokens |
| `GET /callback` | **keyless.** Where Spotify redirects the browser |

The callback is keyless because the browser Spotify redirects has no API key —
nginx only injects it on `/api/*`. It is protected instead by the single-use
`state` that `/login` mints, and `/login` *does* require the key: no key means
no state, and no state means the callback refuses. Same split as the
WebSocket route in `routes/voice.py`.

---

## 6b. Lyrics

The lyrics button, top right of the music view, opens a full-screen lyrics
page over the same drifting cover colours. It is **disabled whenever the
current track has no lyrics**, which is most of what it tells you.

Lyrics do not come from Spotify. Spotify's own lyrics are Musixmatch's and are
not exposed in the public Web API at all, so this uses
[LRCLIB](https://lrclib.net): no account, no key, no signup, and it returns
LRC — lines with timestamps — which is the point. A wall of untimed text on a
panel across the room is not worth the screen.

- `GET /api/spotify/lyrics` reads the **cached** playback snapshot rather than
  asking Spotify again, so it cannot double the 1Hz now-playing poll. Results
  are cached per track id.
- Matching is strict on purpose: artist + track + album + duration first, then
  a search, and a search hit is accepted only when its duration is within a
  few seconds of the track Spotify is actually playing. A confidently wrong
  set of lyrics scrolling in time with the music is worse than none, so a
  near-miss reports `none` and the button stays disabled.
- The panel highlights the line being sung from the same interpolated progress
  the bar uses, and keeps it centred. If LRCLIB only has an untimed set, the
  page says `not timed · scroll` and you read it by finger.
- Nothing is stored on disk and nothing is sent anywhere else: the request
  carries the track's title, artist, album and length, and nothing about you.

Statuses: `ok`, `none` (nobody has them), `instrumental` (the database says
there are none to have), `idle` (nothing playing), `unreachable`.

---

## 7. Troubleshooting

### The panel says "Spotify not set up"

`SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` are not reaching the backend.
Check they are in `infra/docker/.env` (not `apps/backend/.env`, which is only
for bare-metal runs) and that the container was recreated, not just restarted:

```bash
docker compose up -d --force-recreate backend
```

### "INVALID_CLIENT: Invalid redirect URI"

The URI in the Spotify dashboard and `SPOTIFY_REDIRECT_URI` differ. Trailing
slash, `http` vs `https`, and `localhost` vs `127.0.0.1` all count as different.

### Connected, then "Spotify needs reconnecting" later

The refresh token was revoked — either at
<https://www.spotify.com/account/apps/>, or by changing the app's secret.
Re-run step 3. If it happens on **every restart**, the token file is not
persisting: check that `./state` exists at the repo root and that the backend
service has the `../../state:/app/state` volume.

### Controls do nothing, panel says "Nothing is playing on your account"

That is `404 NO_ACTIVE_DEVICE`. Start a track elsewhere first — see section 0.

### Controls say "Spotify Premium is required"

Reading works on free accounts, writing does not. Nothing to fix.

### The lyrics button is always greyed out

It is disabled per track, so first try a well-known song. If it is disabled
for everything, check the backend log for `LRCLIB`: a container with no DNS or
no CA certificates cannot reach `lrclib.net`, and weather would be broken too.
Podcasts never have lyrics and are rejected before the lookup.

### The lyrics are the wrong song's

Report it to LRCLIB rather than here — the match is pinned to the track's
duration, so a wrong hit means their database has a wrong duration. Nothing on
the Pi caches it longer than the backend runs; restarting the backend clears
it.

### The background colours look wrong or stay neutral

The cover failed to load or the canvas could not be read. The panel falls back
to neutral surfaces by design. Check `/api/spotify/art/<id>` returns an image;
if it 404s, the backend could not reach `i.scdn.co`.

---

## 8. Spotify's rules

Using their API obliges you to follow their design guidelines. The ones this
panel is built around:

- their name is displayed wherever their content is (the `SPOTIFY` label under
  the controls)
- album art is shown unmodified — no cropping, recolouring or overlays on the
  image itself
- their content is not mixed with other sources in the same view

Keep those if you restyle the view.
