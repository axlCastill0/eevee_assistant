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

Get the authorize URL from the Pi, through nginx, which adds the API key for
you — open this in the laptop's browser:

```
http://<pi-address>/api/spotify/login
```

Copy the `authorize_url` out of the JSON, open it, approve. The redirect goes
down the tunnel and you land on "Spotify connected".

### C. No tunnel: paste the code by hand

Open the authorize URL anywhere, approve, and the browser will fail to load a
`127.0.0.1:8000/spotify/callback?code=...` page. That is fine — the code is in
the address bar. Copy it and post it:

```bash
curl -X POST http://<pi-address>/api/spotify/code \
  -H 'Content-Type: application/json' \
  -d '{"code":"<the code from the address bar>"}'
```

Codes are single-use and expire in about a minute, so do this promptly.

### Confirming it worked

```bash
curl -s http://<pi-address>/api/spotify/status
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

## 6. Routes

All under `/spotify`, all requiring `X-API-Key` **except the callback**:

| Route | Does |
|---|---|
| `GET /now-playing` | the snapshot. Always 200; read `status` |
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
