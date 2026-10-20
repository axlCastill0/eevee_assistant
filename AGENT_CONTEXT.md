# AGENT_CONTEXT

Machine-oriented state file for coding agents. Read fully before any change.
UPDATE THIS FILE IN THE SAME COMMIT AS ANY CHANGE IT DESCRIBES. See `## update_protocol`.

```yaml
meta:
  project: eevee_assistant
  root: /Users/tako/root/eevee_assistant
  last_updated: 2026-10-19
  git_branch_main: main
  target_host: Raspberry Pi 5 (8GB recommended), Raspberry Pi OS Lite 64-bit
               CONFIRMED 2026-10-07: the Pi runs Trixie (Debian 13), aarch64.
               The host release does NOT constrain the images - containers
               bring their own userland. Only host-facing docs/packages care.
```

## layout

```
apps/
  backend/            FastAPI service. Owns data + response wording.
    main.py           App entrypoint, root logging, GET /
    auth.py           X-API-Key dependency, shared by all routes
    events.py         VOICE EVENT HUB - in-memory fan-out behind the WS;
                      also publish_command() for theme/screen instructions
    intents.py        INTENT REGISTRY - single source of truth; handlers and
                      their hand-written phrasing variants
    sysinfo.py        host uptime + SoC temperature, read from /proc and /sys
    timers.py         TIMERS: monotonic deadlines, duration parsing, in memory
    alarms.py         ALARMS: 7 weekday slots, wall clock, persisted to state/
    settings.py       timer/alarm sound choice, screen idle timeout, media/
    screen.py         SCREEN POWER STATE. In memory. Written by the top-bar
                      button, voice, and the idle timer; READ BY THE HOST
                      AGENT, which is the only thing that can switch a
                      backlight
    spotify.py        SPOTIFY: OAuth tokens, TTL'd playback snapshot, the four
                      controls, cover-art fetch. urllib, no new deps
    weather.py        Open-Meteo lookup, cached, no API key
    wol.py            WAKE-ON-LAN: magic packet + a TCP liveness probe for
                      ONE machine, configured in the environment. Works only
                      because the backend is network_mode: host
    services.py       SERVICE HEALTH - heartbeat registry + summarize()
    routes/
      __init__.py     Empty, marks package
      voice.py        /voice/health, /voice/heartbeat, /voice/intents,
                      /voice/intent, /voice/state, WS /voice/events
      spotify.py      /spotify/now-playing|command|art|status|login|code|
                      disconnect (keyed) + /spotify/callback (KEYLESS)
      screen.py       /screen GET+POST. Polled by scripts/screen-agent.sh
      clock.py        /clock/state (ONE poll for timers+alarms+settings+screen),
                      /clock/timers, /clock/timers/<id>/pause,
                      /clock/alarms/<weekday>, /clock/settings,
                      /clock/sounds/<file>
      weather.py      GET /weather. Its OWN route, not a /clock/state field:
                      a cache miss blocks on Open-Meteo and that poll is the
                      one that rings alarms
      wake.py         GET/POST /wake. Wake-on-LAN; own route for the same
                      reason (the probe is a TCP connect with a timeout)
      status.py       GET /services - the dashboard's data source
    requirements.txt
    .env.example
  voice/              Voice pipeline. Separate container, separate lifecycle.
    run.py            Entrypoint; loads .env BEFORE importing config
    requirements.txt
    .env.example      For bare-metal runs only; Docker uses infra/docker/.env
    voice_assistant/
      config.py       ALL config, env-driven (VOICE_*); resolve_device()
      helpers.py      downsample_mic, resample_for_output, preprocess_transcript
      wake_word.py    make_detector() engine picker + openWakeWord wrapper
      wake_heed.py    HEED WAKE WORD - log-mel frontend (HPF/notch, STFT,
                      mel, CMN), energy gate, consecutive/refractory trigger
      wake_check.py   `python -m voice_assistant.wake_check f.wav` prob check
      vad.py          Silero VAD v5 via onnxruntime (64-sample context)
      recorder.py     VAD-gated capture with frame-based pre-roll
      stt.py          faster-whisper tiny.en int8
      fastpath.py     Regex pre-classifier, tried BEFORE the SLM
      slm.py          Qwen2.5 + GBNF grammar built from the API catalogue
      activity.py     StateReporter: queued, off-thread voice state publishing
      api_client.py   httpx client; failure-tolerant, never raises upward
      heartbeat.py    Daemon thread posting /voice/heartbeat every 15s
      tts.py          Piper TTS + output resampling
      pipeline.py     Main loop wiring every stage
      devices.py      `python -m voice_assistant.devices` audio device lister
      alsa.py         CARD ID -> CARD NUMBER via libasound ctypes. Exists
                      because /proc/asound is MASKED inside the container
  ui/                 Dashboard SPA. Vite + React + TS, static, nginx-served.
    index.html        Inline bg style prevents a white flash on cold boot
    src/App.tsx       Shell: sidebar + global chrome + the active view
    src/views/        Home.tsx (THE LAUNCHER, route "dashboard": glance strip
                      + app grid), Timers.tsx, Alarms.tsx, NowPlaying.tsx
                      (Spotify), Dashboard.tsx (systems grid, route
                      "systems"), Settings.tsx
                      Wake.tsx ("Home" -- the wake-on-LAN app)
                      (Clock.tsx was DELETED 2026-10-16: it was timers and
                      alarms sharing one page; they are now an app each)
    src/components/RingingBanner.tsx  plays the mp3, Stop button; in the SHELL
    src/components/StatusIcons.tsx    top-bar timer/alarm icons
    (ThemeToggle.tsx was DELETED 2026-10-16: the control moved to Settings)
    src/components/Sidebar.tsx   view switcher rail. Lists DESTINATIONS, not
                      every route: timers/alarms are launched from Home and
                      light the Dashboard entry while open
    src/components/AppHeader.tsx  back-to-launcher header for Timers/Alarms
    src/components/TimerDial.tsx  drag-to-set duration. TWO rings: outer =
                      minutes, inner = seconds; the ring is chosen at
                      touch-down from the radius and never re-tested
    src/components/Drum.tsx       scroll-snap wheel picker (alarm hour/minute)
    src/components/WeatherGlyph.tsx  WMO-code icons, inline SVG
    src/lib/useRoute.ts          hand-written hash router (no react-router)
    src/lib/useSpotify.ts        1Hz poll + local progress interpolation
    src/lib/coverColors.ts       two dominant cover colours off a 32x32 canvas
    src/lib/useClockState.ts     1Hz /clock/state poll + local countdown
    src/lib/useIdle.ts           pointer/key idle timer for screen auto-sleep
    vite.config.ts    Dev-only /api proxy that injects the key like nginx does
    package.json
    .env.example      Dev server only; NOT compiled into the bundle
    src/
      main.tsx
      App.tsx         Layout, grid, sheet state
      index.css       DESIGN TOKENS, both themes, all keyframes, font faces
      vite-env.d.ts   Ambient types for CSS side-effect imports
      lib/
        api.ts        fetch wrapper -> /api; maps gateway 5xx to "unreachable"
        useServices.ts  3s poll + client-side heartbeat history
        useVoiceEvents.ts  WebSocket to /api/voice/events; reconnect + watchdog
        useTheme.ts   light/dark/auto, boundary timer, RTC guard
        useClock.ts   second-aligned tick (plain intervals drift)
        useWeather.ts 5-minute poll of /weather; keeps the last good reading
        format.ts     durations, clock, labels
      components/
        TopBar/ThemeToggle/PollRing      header, 3-state toggle, poll sweep
        Overview                         hero; reuses backend's speech string
        ServiceTile/Sparkline/StatusDot  per-service tile
        DetailSheet                      drag-to-dismiss bottom sheet
        VoicePill                        top-bar activity pill + transcript
        VoiceDialog                      big-font answer, 7s hold
        ScreenVeil                       black-out overlay for "screen off"
infra/
  docker/
    docker-compose.yml       services: backend, voice (independent)
    .env.example
    backend/Dockerfile       python:3.13-slim
    voice/Dockerfile         python:3.11-slim-bookworm (base != host; see below)
    ui/Dockerfile            node build -> nginx:1.27-alpine
    ui/nginx.conf.template   serves dist + proxies /api INJECTING X-API-Key
docs/
  README_PI.md        Pi setup from a fresh clone; audio device lock-in
  VOICE_SETUP.md      Pi setup, architecture, latency, gotchas, wake word
  SPOTIFY.md          Spotify app registration, the one-time connect, routes
  TIMERS_AND_ALARMS.md  media folder, kiosk autoplay flag, voice phrasings
  PSU.md              power supply requirements
  UI.md               dashboard stack rationale, theme, touch, Pi perf, kiosk
scripts/
  fetch-voice-models.sh      Downloads ~1.3GB into models/ (gitignored)
  install-wake-model.sh      Copies hey_eevee_model/ -> models/hey_eevee.{onnx,json}
  screen-agent.sh            HOST-SIDE, runs in the kiosk session (NOT Docker).
                             Polls /api/screen and switches the display:
                             sysfs bl_power -> wlr-randr -> xset -> vcgencmd
hey_eevee_model/             COMMITTED. "hey eevee" heed export + its README.
                             wake.onnx (fp32), wake.int8.onnx, wake.json.
models/                      GITIGNORED. Bind-mounted read-only into voice.
state/                       GITIGNORED. Bind-mounted READ-WRITE into backend
                             at /app/state. Holds spotify.json (refresh token,
                             mode 0600), alarms.json and settings.json.
media/                       GITIGNORED. Bind-mounted READ-ONLY at /app/media.
                             Timer/alarm sounds; read per request, so a new
                             file appears in Settings with no restart.
_temp/                       GITIGNORED. Original prototype; reference only.
AGENT_CONTEXT.md             This file.
```

## stack

```yaml
backend:
  python_version: "3.13"        # pinned in infra/docker/backend/Dockerfile
  framework: fastapi
  server: uvicorn
  deps: [fastapi, "uvicorn[standard]", python-dotenv]
  listen: 0.0.0.0:8000          # hardcoded in Dockerfile CMD and main.py __main__

voice:
  python_version: "3.11"        # NOT 3.13 - see gotcha py311_required
  deps: [sounddevice, numpy, scipy, openwakeword, faster-whisper,
         llama-cpp-python, piper-onnx, httpx, python-dotenv]
  pip_extra_index: https://abetlen.github.io/llama-cpp-python/whl/cpu
  reason: prebuilt aarch64 CPU wheels for llama-cpp-python; without it pip
          compiles llama.cpp from source (10+ min on a Pi 5)

ui:
  build: vite 6 + react 19 + typescript, STATIC output
  runtime: nginx:1.27-alpine (no Node at runtime, by design)
  port: 8080
  styling: hand-written CSS with custom properties. NO Tailwind, NO CSS-in-JS.
  animation: CSS only. NO framer-motion or other animation library.
  reason: the theme is a token swap on one attribute, and CSS keyframes stay
          on the compositor. A JS animation library would add ~50KB and run
          work on the main thread the Pi does not need to do.
  deps: react, react-dom (runtime). Everything else is devDependencies.
  payload: 283KB js / 87KB gzip, 51KB css / 10KB gzip, 89KB fonts
           (was 265/82 js and 35/7 css before the launcher, the timer and
            alarm apps and the wake app landed on 2026-10-16)
  fonts: Inter + JetBrains Mono, SELF-HOSTED, latin subset only, declared by
         hand in index.css. The @fontsource package has no per-subset entry
         and its index.css pulls ~150KB of unused Cyrillic/Greek/Vietnamese.
         Self-hosted because the Pi may boot before the network is up.
```

## ui dashboard

```yaml
purpose: room control panel. Chromium kiosk, i3, Raspberry Pi 5, ~10" TOUCH.
data: polls GET /api/services every 3s (POLL_MS in lib/useServices.ts)
docs: docs/UI.md

THE KEY CONSTRAINT - why nginx exists:
  the browser must never hold API_KEY. nginx proxies /api/* and attaches the
  header server-side. The bundle contains only the literal string "/api".
  VERIFIED: grep of dist/ finds no key.
  Do NOT "simplify" this by calling the backend directly from the browser or
  by serving the bundle from FastAPI's StaticFiles.

independence: NO depends_on, same as voice. The dashboard's job includes
  reporting that the backend is down, which it cannot do if it is served BY
  the backend or blocked on it starting.

theme:
  modes: light | dark | auto, persisted in localStorage
  auto: light 08:00-17:59, dark otherwise (DAY_START/DAY_END in useTheme.ts)
  TIMER: auto re-evaluates at the next boundary. A kiosk runs for months
         without a reload, so a mount-time check alone would stick.
  clock format: 12-hour with AM/PM (format.ts clockTime). Matches the backend's
         spoken "%-I:%M %p" so panel and assistant agree. Hour not zero-padded.
  RTC GUARD: the Pi has no RTC, so pre-NTP the clock can read 1970 and auto
         would pick a theme from a bogus hour. If the year is implausible the
         UI holds DARK, shows "clock not synced", and re-checks every 15s.
         Same bug class as the backend's monotonic-clock choice.

touch:
  --touch-min: 56px floor; the whole tile is the target, not a button inside it
  no hover-only affordances anywhere; :active press states instead
  touch-action: manipulation (kills the 300ms tap delay)
  cursor hidden, selection off, pinch-zoom off
  detail sheet drags down to dismiss

resolution: UNKNOWN - user has not measured the panel yet
  every type size is clamp() between a 1024x600 floor and 1920x1200 ceiling
  tile grid is auto-fit + minmax, so services reflow by width
  a max-height:700px compact mode trims hero/clock/tile padding
  VERIFIED at 1280x800 and 1024x600

PI PERFORMANCE RULES - enforced, do not relax without measuring:
  - NO backdrop-filter anywhere. Frosted glass is the obvious trend pick and
    the most expensive thing this GPU can do. Static gradients instead.
  - animate ONLY transform and opacity (compositor-only)
  - shadows are declared, never transitioned
  - the poll ring is CSS, not React state, so it does not re-render the tree
  - prefers-reduced-motion disables everything; also the escape hatch if the
    Pi turns out slower than expected

honesty constraints already encoded in the UI:
  - the heartbeat trail is accumulated CLIENT-SIDE and labelled "since load".
    It does not survive a reload. Do not relabel it as uptime.
  - a gateway 5xx reads as "Backend unreachable", not "returned 502"
  - a failed poll keeps the last good values and marks them stale rather than
    freezing silently or blanking
  - the hero reuses the backend's own `speech` string, so the panel and the
    voice assistant can never disagree
```

## auth

```yaml
mechanism: static_shared_secret
header: X-API-Key               # auth.API_KEY_HEADER
env_var: API_KEY                # read via os.environ.get at request time
dependency: auth.require_api_key
responses:
  missing_or_wrong_header: 401
  API_KEY_unset_on_server: 500
note: the voice container uses the SAME API_KEY to call the backend
```

RULE: every route MUST be guarded. The voice router applies the guard
router-level (`APIRouter(dependencies=[...])`); `main.py` guards `/`
per-endpoint. Verified: all four endpoints return 401 unauthenticated.

## routes

| method | path | module | auth | returns |
|---|---|---|---|---|
| GET | `/` | `main.py` | yes | `{"status","service"}` |
| GET | `/services` | `routes/status.py` | yes | `{"all_healthy","speech","stale_after_s","services":[...]}` |
| GET | `/voice/health` | `routes/voice.py` | yes | `{"status","route"}` — route liveness only, NOT pipeline health |
| POST | `/voice/heartbeat` | `routes/voice.py` | yes | `{"status","stale_after_s"}` |
| GET | `/voice/intents` | `routes/voice.py` | yes | `{"intents":{name:{description,needs_item}}}` |
| POST | `/voice/intent` | `routes/voice.py` | yes | `{"speech","intent","item","ok"}` |
| POST | `/voice/state` | `routes/voice.py` | yes | `{"status","seq"}` — pipeline reports a stage transition |
| GET | `/voice/state` | `routes/voice.py` | yes | `{"event","subscribers"}` — last known activity |
| WS | `/voice/events` | `routes/voice.py` | yes (manual) | voice activity stream for the dashboard |

`/services` is unprefixed because it is system-wide, not scoped to a
subsystem. It is the dashboard's data source and must work when voice is down.

`WS /voice/events` is on `voice.ws_router`, NOT the guarded router: the
router-level `require_api_key` raises `HTTPException`, which has no meaning on
a socket that has not been accepted. The handler checks the same header by hand
and closes with 1008 instead, so the UI can tell "rejected" from "unreachable".

`POST /voice/intent` body: `{intent, item?, transcript?}`. Unknown intent names
are downgraded to `"unknown"` rather than rejected — the classifier is not
trusted to be correct. `item` is forced to null for intents with
`needs_item: false`.

## voice pipeline

```yaml
flow: wake_word -> record(VAD) -> STT -> fastpath|SLM -> HTTP -> TTS

activity: every stage transition is published to the backend for the
  dashboard's pill. Emitted at: greeting (speaking->ready), wake word
  (listening), end of recording (thinking), transcript ready (thinking +
  text), TTS start (speaking + text), end of utterance (ready), shutdown
  (offline). Every spoken line - including the error paths - goes through
  VoiceAssistant._say(), so the dialog can never be skipped for exactly the
  messages worth reading. See `## voice activity`.

models:
  baked_into_image:          # no network needed on first boot
    - openWakeWord (~50MB)   # bundled "hey_jarvis"
    - whisper tiny.en (~75MB)
  bind_mounted_from_models_dir:   # too large to bake, or repo-local
    - hey_eevee.onnx + hey_eevee.json (44KB + 2KB)  # install-wake-model.sh
    - silero_vad.onnx (2MB)
    - qwen2.5-1.5b-instruct-q5_k_m.gguf (1.2GB)
    - en_US-amy-medium.onnx + .onnx.json (60MB)

wake_word: hey_jarvis (openWakeWord, baked into the image) DEFAULT AGAIN
  2026-10-16. USER DECISION: the "hey eevee" heed export fired on non-speech
  room noise even at VOICE_WW_THRESHOLD=0.9. It is still supported and still
  installed by scripts/install-wake-model.sh; set VOICE_WAKE_WORD=
  models/hey_eevee.onnx to go back, AND clear VOICE_WW_THRESHOLD -- 0.9 is a
  sensible tightening for heed and leaves hey_jarvis deaf.
  Everything below describes the heed path, which is unchanged.
wake_word_heed: "hey eevee" (models/hey_eevee.onnx) WAS the default 2026-10-15
  engine_picked_by: wake_word.make_detector() -> wake_heed.is_heed_model(),
    which is TRUE when a .json sidecar sits beside the .onnx. No sidecar, or a
    bare name like hey_jarvis, falls through to the openWakeWord wrapper.
  WHY NOT openWakeWord: incompatible input. openWakeWord models consume its
    own melspectrogram+embedding frontend output; a heed export consumes
    log-mel directly (input "mel", shape (1,40,101)).
  sidecar_is_mandatory: wake.json carries threshold (0.603), mel params,
    filter cutoffs, trigger and energy-gate constants. Loading fails without it.
  preprocessing (wake_heed.py, order matters):
    1. causal 100Hz 8th-order Butterworth HPF + 50/60Hz notches, biquad state
       retained across frames (equivalent to one pass over the whole stream)
    2. peak normalize to -3dBFS (cosmetic after CMN; kept for fidelity)
    3. log-mel: 400-sample hann in a 512-pt FFT, hop 160, 40 bins, centred and
       reflect-padded -> exactly 101 frames for a 1s window
    4. CMN per mel bin across time. OMITTING IT MAKES THE MODEL WILDLY WRONG
  trigger: 2 consecutive frames over threshold, then 0.7s refractory (from
    wake.json, not env). Replaces the openWakeWord wrapper's COOLDOWN_FRAMES.
  energy_gate: skips the model when RMS < -55dBFS or <15% of energy in
    100-7000Hz. Measured on UNFILTERED audio on purpose - the HPF has already
    deleted the rumble that would prove the energy is not speech.
  UNPINNED CONVENTIONS (sidecar does not state them; defaults = torchaudio,
    because the export is a torch 2.11 graph): mel scale HTK, filterbank
    unnormalised (peak 1.0), natural log, notch Q=30. Overridable with
    VOICE_WW_MEL_SCALE / VOICE_WW_MEL_NORM / VOICE_WW_LOG_BASE /
    VOICE_WW_NOTCH_Q. NOT yet confirmed against a positive clip - only against
    noise/tone/silence negatives. Use wake_check.py on a real "hey eevee"
    recording to close that gap.
  SURPRISE COST (2026-10-15, real Pi): first SLM warmup after a rebuild took
    216 s, not the ~2 s a warm one takes -- 1.2 GB of GGUF being read off the
    SD card with a cold page cache. Not a hang. Subsequent boots are fast.
  REAL-WORLD TUNING (Pi, 2026-10-16): the sidecar's calibrated 0.603 fired on
    non-speech room noise. USER set VOICE_WW_THRESHOLD=0.9. Next levers if it
    recurs, in order: consecutive_frames 2->3 in models/hey_eevee.json, then
    mic capture gain in `alsamixer -c eeveemic`.
  window: detector keeps its own 1s ring buffer, so frame length is free; the
    pipeline feeds 1280 samples (80ms), so the model runs at an 80ms hop.

classifier:
  model: Qwen2.5-1.5B-Instruct Q5_K_M
  chosen_for: accuracy over latency (USER DECISION 2026-10-04)
  cost: ~4-5s per classification on a Pi 5, ~1.2GB resident
  constrained_by: GBNF grammar built at runtime from GET /voice/intents
  composes_speech: NO - returns (intent, item) only

fastpath:
  what: regex pre-classifier in fastpath.py, tried before the SLM
  why: the 1.5B model costs 4-5s; a regex hit skips it entirely
  rule: only returns confident matches; ambiguity falls through to the SLM
  scope: rules are pruned to intents the API actually advertises, so it can
         never emit an intent with no handler
  extending: check logs for "Classified by SLM" - each is a missing rule

BOOT GOTCHA - WHISPER MUST NOT TOUCH THE NETWORK (fixed 2026-10-08):
  symptom: after a Pi reboot the voice container exits with
           `httpx.RemoteProtocolError: Server disconnected without sending a
           response` from inside load_whisper -> huggingface_hub.
  cause:   stt.py passed `local_files_only=False`. faster-whisper then calls
           snapshot_download EVEN WHEN THE CACHE IS COMPLETE, to revalidate
           against HF. On a Pi that just booted, the connection is made and
           then dropped. huggingface_hub falls back to the cache on
           ConnectionError and Timeout, but RemoteProtocolError is NEITHER, so
           it escapes and kills startup. A REFUSED port is handled fine - which
           is why this only shows up on a real boot, never on a dev box with no
           network.
  fix:     config.WHISPER_LOCAL_ONLY, default True. The weights are baked into
           the image at /opt/models-cache, so there is nothing to fetch.
           VOICE_WHISPER_ALLOW_DOWNLOAD=true re-enables fetching for a
           bare-metal first run or a changed VOICE_WHISPER_SIZE.
  REPRODUCED AND FIXED under a TCP server that accepts then hangs up; see
  `## verified`.
  restart policy note: voice is `unless-stopped`, so this exits once and STAYS
  down rather than restart-looping. That is the intended behaviour for a
  missing model, and it is why the container was simply gone after the reboot.

latency:
  fastpath_hit: ~2s end-to-end
  slm_fallback: ~6-7s end-to-end
```

## timers and alarms

```yaml
home_route: "dashboard" = views/Home.tsx, THE LAUNCHER (REBUILT 2026-10-16).
  A glance strip over a grid of app tiles. Timers and alarms are apps behind
  it, at routes "timers" and "alarms", each with the whole screen.

  glance strip: a card appears only when it has something to say -- timers
    while any exist, the next alarm only while one is ENABLED, now playing
    only while something is actually playing. WEATHER IS ALWAYS THERE, and is
    the exception on purpose: it is the one thing worth reading when nothing
    is happening, and a home screen that empties to nothing reads as broken.
  app tiles: ONLY apps with NO sidebar entry (USER DECISION 2026-10-16).
    Timers, Alarms, Home(wake). Music/Systems/Settings were removed -- the
    launcher was a second copy of the rail. Each tile carries a line of live
    state ("2 running", "5 of 7 on"), counted BY STATE: a paused timer reads
    "1 paused", never "1 running". The wake tile is deliberately NOT live --
    a reading there would mean probing that machine's TCP port every few
    seconds for as long as the panel sits idle on the home screen.
  grid: rows capped and centred. A stretching row made each tile 300px of
    mostly nothing once the list dropped to three; add enough apps to wrap to
    a second row and it fills the panel on its own.
  NO SHEEN. The tiles had a slow highlight sweep; removed 2026-10-16 (USER).

  SIDEBAR UNCHANGED (USER DECISION 2026-10-16). It lists destinations, not
  routes: Dashboard, Music, Systems, Settings pinned to the bottom. Dashboard
  stays lit while you are inside Timers, Alarms or Home -- see HOME_APPS in
  lib/useRoute.ts.

timers:
  storage: IN MEMORY, monotonic deadlines. Not persisted on purpose -- a
    countdown only means anything relative to now, and resurrecting one that
    should have fired two minutes ago is worse than losing it.
  several at once (USER DECISION 2026-10-16). Labelled by duration, which is
    what makes a spoken "cancel the 10 minute timer" resolvable.
  PAUSE (added 2026-10-16): a paused timer holds the remainder it had, and
    resuming computes a fresh monotonic deadline from it. Storing the
    REMAINDER rather than a "paused at" instant is what makes a pause survive
    an NTP step. `_sweep` skips paused timers entirely, so one can sit past
    its original deadline without ringing. `active()` sorts paused timers
    last however little they have left: the list reads as "what is about to
    happen", and a paused timer is not going to happen.
    Route: POST /clock/timers/<id>/pause with `{"paused": true|false}` -- the
    state the panel WANTS, not a toggle verb, so a double tap on a
    touchscreen settles instead of flapping. Idempotent. A ringing timer
    cannot be paused.
  SCREEN UX (REBUILT 2026-10-16): components/TimerDial.tsx. TWO CONCENTRIC
    RINGS, both 6 deg per notch:
      OUTER = minutes, one revolution = 60 minutes.
      INNER = seconds, one revolution = 60 seconds. Carries into minutes.
    Which ring you are turning is decided ONCE, at touch-down, from the
    radius -- never re-tested during the drag. A circular gesture drifts in
    radius, and re-testing every move would silently switch you from minutes
    to seconds halfway round.
    Resolution is 1 SECOND (USER DECISION 2026-10-16), which is also why
    timers.MIN_DURATION_S dropped from 5 to 1: clamping a dialled 0:03 up to
    0:05 would make the control lie.
    Tapping a preset ARMS the dial rather than starting immediately, so a
    mis-tap is not a timer you then have to cancel.
    WHY A GESTURE AT ALL: there is no keyboard on this panel and no on-screen
    one wanted (USER 2026-10-16), so a text field was never an option and the
    old stepper was 45 taps for a 45-minute timer.
  voice: set_timer / cancel_timer / timer_status, with fast-path regexes.
    Durations parsed on the BACKEND (timers.parse_duration): "half an hour",
    "ninety seconds", and a bare "ten" = ten minutes.
    NOTE: new intents need `docker compose restart voice` -- the pipeline
    fetches the catalogue once at startup.

alarms:
  7 weekday slots (USER DECISION 2026-10-16), NOT a list of arbitrary alarms.
  storage: PERSISTED to state/alarms.json. A schedule is still true after a
    reboot. WALL CLOCK, deliberately opposite to timers: "has 7:30 happened"
    is a wall-clock question, so an NTP step must move the alarm with it.
  fires once per day: stopping records the date, which is also what stops a
    restart inside the 120s fire window from re-ringing it.
  screen-only. No voice (USER DECISION): a misheard word costs most on a
    recurring weekly commitment.
  SCREEN UX (REBUILT 2026-10-16, model UNCHANGED -- USER chose to keep the 7
    slots and rebuild only the controls):
      - the week is a strip of seven chips, always visible. It is the
        navigation AND the overview: every day's time is legible without
        selecting it. Selected is a border, enabled is colour plus a filled
        dot -- two different questions, so two signals.
      - the selected day gets components/Drum.tsx wheel pickers (hour /
        minute / AM-PM), flicked rather than tapped. CSS scroll-snap does the
        physics; the component only reads which row ended up centred.
        MINUTES ARE 0-59, every minute (USER DECISION 2026-10-16). Sixty rows
        is a long flick end to end; bearable because the wheel opens on the
        value already set, and the five-minute grid it replaced made a third
        of all times simply unreachable.
        NO SECONDS WHEEL, deliberately: FIRE_WINDOW_S is 120s, so an alarm
        may legitimately ring up to two minutes after the time shown and a
        seconds value would be decorative. Timers are the control that goes
        to the second.
      - COPY THIS TIME TO Mon-Fri / Sat-Sun / All 7, which also ENABLES those
        days: "same as Monday" means you want the alarm, not a row that
        merely agrees about a time it will never ring at. This is the single
        biggest win available without changing the data model, which is why
        seven slots remain comfortable.
    NOT a modal, for the same reason the old accordion was not: "is Thursday
    also set" is the question you are usually answering while you edit.

audio:
  PLAYS IN THE KIOSK BROWSER (USER DECISION 2026-10-16), not the backend and
  not the voice container -- the voice loop is single-threaded, so a 3-minute
  song there would deafen the wake word for its whole duration.
  Needs --autoplay-policy=no-user-gesture-required in kiosk.sh (already in
  the documented launcher). Without it the banner offers a tap-to-play
  button rather than failing silently.
  One play-through, then silence. Stop button or `ended` both POST the same
  acknowledgement.

polling:
  /clock/state is polled 1Hz BY THE APP SHELL, not by the Dashboard view. An
  alarm must ring whatever page is on screen, and the top bar's icons need
  the same data. Countdowns are advanced locally between samples.

top_bar: theme toggle REMOVED (moved to Settings) to make room for static
  status icons: stopwatch while timers run, bell when an alarm is due within
  24h. Neither is a countdown; neither is a button.

theme: still per-browser localStorage, NOT a server setting. A theme belongs
  to a display, and `set_theme` by voice writes the same local store. The
  Settings page shows the control next to two server-side ones anyway,
  because that is where a person looks for it.
```

## wake on lan ("Home")

```yaml
purpose: turn on ONE Windows PC on the LAN from the panel or by voice.
  USER's machine already has WoL enabled in firmware/Windows; nothing here
  configures the target end.

LOAD-BEARING: network_mode: host
  apps/backend runs with host networking (infra/docker/docker-compose.yml).
  A BRIDGED container cannot put a broadcast on the LAN -- the packet dies at
  docker0, sendto() still succeeds, and nothing ever wakes. If the backend is
  ever moved off host networking THIS BREAKS SILENTLY. The probe would keep
  working, which makes it look like the PC is simply ignoring the packet.

packet: 6x 0xFF then the MAC 16 times, UDP broadcast, sent THREE times.
  A single UDP broadcast may be dropped by any switch on the way and nothing
  retransmits it. No dependency: `wakeonlan` would be a package for a
  constant, same call as urllib in weather.py.

probe: TCP connect, default port 3389 (Windows RDP), 0.6s timeout, cached 5s.
  NOT ICMP: a raw socket needs CAP_NET_RAW, which means a privileged
  container or a setuid ping in the image. A connect() needs neither.
  WOL_HOST unset => `online` is null => the panel says "status unknown"
  rather than drawing an offline dot it has not earned.

voice: intent `wake_computer`. Fast-path patterns sit ABOVE the wake_screen
  block in voice_assistant/fastpath.py and MUST stay there -- the screen owns
  bare "wake up" (its own spoken reply tells you to say it) and
  `(switch|turn) (it) (back) on`, either of which would swallow "turn on the
  pc". Covers computer/pc/desktop/machine/tower/rig/BROTHER (USER's name for
  it). Verified 2026-10-16: 18 phrasings match, 16 existing ones unaffected.
  Remember `docker compose restart voice` -- the pipeline fetches the intent
  catalogue once at startup.

the machine's name in speech comes from WOL_NAME, never from the transcript:
  "wake your brother" and "wake the pc" are the same request, and echoing the
  words back would make the assistant sound like it heard a different
  machine each time.

ui: views/Wake.tsx, route "wake", titled "Home". The poll tightens from 6s to
  2s for two minutes after a press, because that is the only window in which
  "did it come up" is worth asking often, then falls back on its own. The
  button stays pressable while waiting: a dropped magic packet is real and
  pressing again is the correct remedy.
```

## ui gotchas

```yaml
unstable_callback_restarted_audio:
  SYMPTOM (real, on the Pi 2026-10-16): a timer fired, the ringing banner
  appeared, a "Press play" button flickered once a second, and NO SOUND
  played.
  CAUSE: RingingBanner's audio effect depended on its `stop` prop. App passed
  a fresh arrow every render and the component re-renders on every 1Hz poll,
  so the <audio> element was torn down and rebuilt once a second. Each play()
  was aborted by its own cleanup; the rejection was treated as an autoplay
  block, which is what drew the Play button.
  FIX: the effect depends only on [kind, file]; the callback lives in a ref;
  the rejection handler only treats NotAllowedError as a policy block;
  useClockState returns the memoised `refresh` itself rather than a fresh
  arrow, and App wraps its stop handlers in useCallback.
  RULE: anything long-lived that an effect owns -- audio, sockets, timers --
  must not have a per-render callback in its dependency array.

dial_lost_a_fast_drag_and_could_not_pass_one_turn:
  TWO bugs in components/TimerDial.tsx, both found 2026-10-16 by driving the
  dial with synthesised pointer events, and BOTH present in the single-ring
  version shipped earlier the same day.

  1) STALE PROP. Each move added its notches to the `seconds` PROP, i.e. to
     whatever the last render produced. pointermove fires faster than React
     re-renders, so a run of moves inside one frame every one of them added
     to the SAME number and only the last survived -- the dial lost most of a
     fast drag, and would lose more the busier the Pi got.
     FIX: a ref is the authority during a drag, written before the parent is
     told, resynced from the prop by an effect.

  2) SINGLE-STEP WRAP. The delta was normalised with one
     `if (d > 180) d -= 360` / `if (d < -180) d += 360` pair, which corrects
     exactly one wrap. The anchor is advanced by the degrees SPENT, so on a
     multi-turn drag it grew past 360 and the second revolution produced
     deltas of several hundred degrees that one `if` could not bring back
     into range. The dial then started subtracting: ANY duration over an hour
     was unreachable by dragging.
     FIX: `shortestTurn()`, modulo arithmetic, applied to the delta AND to
     the anchor so it stays in the range `probe` reports.

  RULE: a gesture handler that accumulates must read its running total from a
  ref, not from a prop, and must reduce angles with modulo, not with an `if`.

sound_cache: /clock/sounds sends Cache-Control: max-age=3600, so a repeat
  test shows ZERO server hits and still plays. Do not read "no request in the
  log" as "no audio"; use an untouched filename to force a real fetch.
```

## container gotchas

```yaml
slm_context_window:
  The system prompt grows with the intent catalogue (one line per intent) and
  llama.cpp does NOT degrade when it stops fitting -- it raises and the
  pipeline exits at startup. 2026-10-19: 22 intents = 1048 tokens into a 1024
  window, and the voice container restart-looped unnoticed for days.
  Now: config default 2048, slm.py estimates the prompt before loading and
  re-checks exactly after, growing n_ctx in 256-token steps. An explicit
  VOICE_SLM_N_CTX is a FLOOR, never shrunk. Measured 2026-10-19: 22 intents
  estimate 1257 tokens (the estimator errs high on purpose), so 2048 holds
  about 30 more intents before it grows itself.

screen_off:
  RESOLVED 2026-10-19 on the real Pi. This panel is HDMI (card1-HDMI-A-2,
  EDID "MPI107"), the session is labwc/Wayland, and the working method is
  `wlr-randr --output HDMI-A-2 --off`, which genuinely darkens it.
  Ruled out on this hardware, do not retry:
    /sys/class/backlight  EMPTY -- HDMI has no kernel backlight device, and
                          dtoverlay=rpi-backlight is for the DSI display only
    ddcutil               panel answers EDID but "DDC communication failed"
    xset                  X11 is not running
    vcgencmd display_power  refused by Pi 5 firmware under vc4-kms-v3d
    uhubctl               would work but the Pi 5's USB ports are GANGED, so
                          it would cut the USB mic and speaker too
  The agent must run INSIDE the kiosk session: over SSH it has no
  WAYLAND_DISPLAY and now exits with a message rather than guessing. It was
  never installed before 2026-10-19, which is why the panel only ever dimmed
  to a black page while staying lit.

utc_by_default:
  A container's local time is UTC no matter what the host says. Found on the
  Pi 2026-10-16: the dashboard clock (drawn by the BROWSER, so it follows the
  host) was right while `docker compose exec backend date` was hours out.
  What that breaks: intents._get_time, timers' ends_at, and alarms.py, which
  is wall-clock by design and would have fired every alarm at the UTC hour.
  Fixed by mounting /etc/localtime + /etc/timezone read-only into backend and
  voice. A plain `restart` does NOT apply a new mount -- it needs
  `up -d --force-recreate`.
  Verified 2026-10-16: same python:3.13-slim image read 03:13 without the
  mount and 23:13 (matching the host, EDT) with it.

masked_proc:
  /proc/asound is EMPTY inside the voice container -- it is on the container
  runtime's default masked-paths list, so Docker mounts a tmpfs over it.
  Symptom: the host's `cat /proc/asound/cards` lists every card while the
  container reports `No such file or directory: /proc/asound/cards`.
  Also masked by default: /proc/acpi, /proc/kcore, /proc/keys,
  /proc/timer_list, /sys/firmware. Do not build a feature on reading any of
  them from inside a container.
  What to use instead for audio: libasound over /dev/snd (voice_assistant/
  alsa.py). Cost the project one Pi rebuild cycle on 2026-10-16.
```

## spotify panel

```yaml
view: apps/ui/src/views/NowPlaying.tsx, route #/music
controls: previous, play/pause, next. NO SEEK (user decision 2026-10-16)

hard_constraints:
  - the Web API is a REMOTE CONTROL: it cannot originate audio. Nothing
    playing anywhere => every control returns 404 NO_ACTIVE_DEVICE. The fix is
    a Spotify Connect client on the Pi (raspotify), not a code change
  - playback control requires PREMIUM; reading does not
  - scopes: user-read-playback-state, user-read-currently-playing,
    user-modify-playback-state. Adding one means re-authorizing

data_flow:
  spotify.py holds a TTL'd snapshot (3s playing / 10s not) refreshed inside
  whichever request finds it stale. UI polls /api/spotify/now-playing at 1Hz
  and interpolates progress from the snapshot's `fetched_at` between samples.
  A tap flips is_playing optimistically and refetches after 350ms (Spotify
  needs a beat to settle, especially on a skip).

statuses: ok | idle | unconfigured | unauthorized | unreachable | rate_limited
  Always HTTP 200: a panel must tell "paused" from "not connected" from
  "Spotify is down", and an error code would be swallowed by the UI's generic
  backend-unreachable handling.
  command adds: no_device | premium_required | unsupported

degraded: a failed refresh serves the LAST GOOD snapshot with `degraded` set
  rather than blanking a populated panel.

auth: Authorization Code. Refresh token in /app/state/spotify.json, 0600,
  written atomically. Does not expire unless revoked -> one consent screen,
  then months unattended. See docs/SPOTIFY.md.

colours: lib/coverColors.ts draws the cover into a 32x32 canvas, buckets into
  a 5-bit-per-channel histogram, takes the heaviest bucket plus the heaviest
  one far enough away in hue/lightness. A monochrome cover DERIVES the second
  colour (hue rotated, lightness pushed the other way) instead of showing a
  flat wash. Two stacked gradient layers crossfade on track change, because a
  gradient cannot transition and an opacity can.

spotify_rules: their design guidelines are mandatory for API users. Keep the
  SPOTIFY attribution, do not alter album art, do not mix other content
  sources into the view.
```

## service independence

```yaml
requirement: the API must not fail if the voice pipeline is broken (USER SPEC)

how:
  - separate containers, separate images, separate restart policies
  - NO depends_on between them (deliberate; do not add one)
  - backend holds no pipeline state
  - voice calls the backend over HTTP, never imports it

inverse_also_holds: voice survives the API being down
  - fetch_intents() falls back to api_client.FALLBACK_INTENTS
  - submit_intent() returns a speakable error string, never raises
  - greeting changes to "ready, but I can't reach the backend"
  - VERIFIED 2026-10-04 against a closed port and against a wrong API_KEY

restart_policies:
  backend: always            # per original spec
  voice:   unless-stopped    # NOT always: a missing model file exits non-zero
                             # and `always` would restart-loop forever
```

## intent system

```yaml
source_of_truth: apps/backend/intents.py
published_at: GET /voice/intents
consumed_by: voice builds BOTH its system prompt AND its GBNF grammar from it
             at startup
why: the prototype had three places to keep in sync (prompt, grammar, handler
     list) and they drifted. Now there is one.

adding_an_intent:
  1. add an Intent to INTENTS in apps/backend/intents.py
  2. write a handler returning (speech, ok) and register it in _HANDLERS.
     Give it AT LEAST THREE phrasings via _pick() — see `## answer phrasing`.
  3. add a row to `## routes` only if a new endpoint was added
  4. restart the voice container (it refetches on boot)
  5. optionally add fastpath.py rules once the real phrasings are known
  NOTHING in apps/voice/ needs to change for a new intent.

current_intents: [system_health, get_time, get_date, greeting, repeat_last,
                  set_theme, wake_screen, sleep_screen, get_weather,
                  list_capabilities, get_uptime, cpu_temp, unknown]
  set_theme is the ONLY one with needs_item: true (dark|light|auto)

system_health:
  scope: ALL services at once. There is deliberately NO per-service intent -
         "is the voice pipeline up" is still system_health with item null.
  speech: "Everything good." when all healthy, else the down services named
          ("voice is down." / "a and b are down." / "a, b, and c are down.")
  composed_by: services.summarize(), given a varied lead-in by
          intents._system_health(). The NAMES always come from summarize().
```

## service health

```yaml
source_of_truth: apps/backend/services.py
exposed_at:
  GET  /services          # dashboard polls this
  POST /voice/heartbeat   # the pipeline calls this on a timer
spoken_via: system_health intent -> services.summarize()
note: the JSON and the spoken answer come from the same summarize(), so the
      dashboard and the assistant cannot disagree

mechanism: HEARTBEAT, not probing
why: a crashed or hung service cannot answer a probe and cannot report its own
     failure. Silence is the signal. This is what lets the dashboard show
     "voice is down" when the voice pipeline is the thing that died.
     (USER RATIONALE 2026-10-04)

tracked:
  backend: always healthy by definition - if the code runs, it is up
  voice:   HEARTBEAT_SERVICES; sends every 15s, marked down after 45s silence

timings:
  sender:   VOICE_HEARTBEAT_INTERVAL_S  default 15.0  (voice/config.py)
  receiver: SERVICE_STALE_AFTER_S       default 45.0  (backend/services.py)
  rule: keep the stale window a comfortable multiple of the send interval.
        45/15 tolerates two dropped beats before flapping.

never_checked_in: reported DOWN, not "unknown". A service that has not started
                  is not running; "unknown" would hide a failed boot.

state: IN-MEMORY and intentionally not persisted - heartbeats are only
       meaningful relative to now, and a restarted backend should start from
       "nobody has checked in yet" rather than trust stale timestamps.

clock: time.monotonic(), NOT wall clock. A Pi without an RTC can step its wall
       clock by hours at boot, which would make a live service look long dead.

CONSTRAINT: single-process only. uvicorn --workers > 1 gives each worker its
            own registry dict and health reporting becomes inconsistent. Moving
            to workers means moving this state to Redis or similar.

adding_a_tracked_service:
  1. add its name to services.HEARTBEAT_SERVICES
  2. have it POST /voice/heartbeat (or add a dedicated endpoint) on a timer
     faster than SERVICE_STALE_AFTER_S
  Nothing else changes - summarize() and /services pick it up automatically.
```

## voice activity (the pill and the answer dialog)

```yaml
added: 2026-10-08 (USER SPEC)
purpose: the user has to know WHEN to speak, and be able to read the answer
         from across the room.

transport: WEBSOCKET. GET (upgrade) /voice/events, pushed from the backend.
  publisher: voice pipeline -> POST /voice/state
  subscriber: dashboard -> WS /voice/events (through nginx, which injects the key)
  NOT polled: a 3s poll shows "listening" an average of 1.5s late, i.e. after
              the user has already spoken into a pipeline that was not
              recording. This is the only state in the system that must be
              pushed. See `## mqtt` for why not MQTT.
  MEASURED 2026-10-08: POST -> browser receives = 0.8-1.2ms on the dev host.

states (backend/events.py STATES, ui VoicePill colours):
  ready      blue   --accent   wake word armed
  listening  green  --ok       mic open; pulsing dot
  thinking   amber  --warn     STT + classification; slow pulse
  speaking   red    --down     assistant has the floor
  offline    grey              pipeline not running
  unknown    grey              nothing heard from it yet this backend process
  red is NOT an error here; it is "do not talk over this".
  an unrecognised state is downgraded to "unknown", never rejected - same
  posture as an unknown intent name.

retained event: the hub keeps the last event and sends it to every new
  subscriber, so a kiosk reload paints the right colour immediately instead of
  waiting for the next utterance, which may be hours away. This is the one
  part of MQTT's semantics that was actually needed.
  THE UI MUST DISTINGUISH IT: useVoiceEvents flags the first message of each
  connection as `retained`, and VoiceDialog ignores those. Without that, every
  reload re-announced whatever was last spoken. Seen doing exactly that on
  2026-10-08.

republish + dedupe: the hub is in-memory, so a backend restart forgets the
  state and the pill would sit on "unknown" until the next utterance. The
  reporter re-sends the current state every VOICE_STATE_REPEAT_S (default: the
  heartbeat interval, 15s). The hub treats an IDENTICAL republish as a refresh
  - it moves `at`, does NOT bump `seq`, and does NOT re-broadcast - so the
  dashboard never reads a repeat as a new answer. Any changed field is a real
  event, which is what makes `thinking` -> `thinking + transcript` work.

offline override (ui App.tsx): the event stream reports what the pipeline SAYS
  it is doing, so a pipeline that died mid-utterance would leave the pill stuck
  on green. A voice service the backend reports unhealthy overrides the last
  event. The DIALOG deliberately uses the raw event state instead: an answer
  arriving is itself proof the pipeline is alive, and the override would
  suppress exactly the dialog the user is waiting on if a beat were late.

transcript: shown next to the pill, during `thinking` only. It is the FINAL
  transcript, published the moment Whisper returns and before classification
  (which is 4-5s away on an SLM fallback), so a misheard command is visible
  early. There is no word-by-word streaming - see `## backlog`.

dialog: VoiceDialog.tsx. Appears when speaking starts, holds 7s (HOLD_MS),
  and stays past 7s if TTS is still going. Response text only (USER DECISION).
  font-size clamp(2rem, 4.5vw + 0.8rem, 4rem) - the largest type on the panel.
  HOLD_MS and the CSS drain animation duration must agree; both are 7s.

keepalive: the backend sends {"type":"ping"} after 20s of silence
  (PING_INTERVAL_S). Two things need it: nginx closes idle proxied connections,
  and a suspended Pi network leaves a socket that looks open but is dead. The
  UI treats 45s of total silence as a dead socket and reconnects.

publisher is OFF-THREAD (voice/activity.py): `listening` is published before
  recording starts, so a synchronous POST would put an HTTP round trip - and
  with a dead backend, a full connect timeout - between the wake word and the
  microphone. The queue is bounded (8) and drops the OLDEST on overflow,
  because the newest event is the current state.

single-process only, same constraint as services.py: with uvicorn
  --workers > 1 each worker holds its own subscriber set and only the worker
  that received the publish would forward it. Workers means Redis pub/sub.

nginx: `location = /api/voice/events` is SEPARATE from `/api/`, because /api/
  sets proxy_read_timeout 5s (right for a 3s poll, fatal for an idle socket).
  The socket location gets 3600s plus the Upgrade/Connection headers.

VITE DEV GOTCHA (cost a debugging round trip 2026-10-08): the dev proxy's
  `proxyReq` event does NOT fire for WebSocket upgrades. Without a matching
  `proxyReqWs` handler the socket reaches the backend with no API key and is
  closed with 1008, which Chromium reports only as "WebSocket is closed before
  the connection is established". Both handlers are now in vite.config.ts.
  nginx has no such split.

REACT GOTCHA (cost a round trip 2026-10-08): the dialog's 7s timer originally
  lived in the same effect that latched the answer. That effect depends on
  `speaking`, so React ran its cleanup when speaking flipped to false -
  clearing the timer without re-arming it, and the dialog never hid. The timer
  now lives in its own effect keyed only on the shown event's seq.
  Also: StrictMode's double mount means a shared "closed" ref is reset by the
  second mount before the first socket's onclose fires. useVoiceEvents scopes
  that flag to the effect run instead.
```

## answer phrasing

```yaml
rule: EVERY spoken word in this system is written by a person, in
      apps/backend/intents.py. The language model classifies and does nothing
      else. A 1.5B model will state that a service is running without having
      looked.

HISTORY, so this is not re-proposed: a second SLM pass that re-worded the
  backend's answer was built on 2026-10-08 and REVERTED the same day — the
  user found the added latency worse than expected. It worked and was
  validated; it was simply not worth the wait. Do not revisit without real
  latency numbers measured on the Pi.

variation: intents._pick(*options) chooses between hand-written phrasings.
  MINIMUM THREE per answer, including the failure branches ("I can't read the
  temperature sensor") — those are heard as often as the happy ones when
  something is misconfigured.

_pick NEVER repeats back-to-back. With three options, plain random repeats
  about a third of the time, which reads as broken rather than random.

  THE TRAP: _pick keys on the CALL SITE (sys._getframe(1), filename + line),
  not on the option strings. Most variants are f-strings, so they are fresh
  objects on every call — the first version keyed on id(options[0]) and
  therefore remembered nothing, repeating 7 times in 20 draws. Do not
  "simplify" it back to keying on the strings.

repeat_last: `intents._last_spoken` is set by handle() for every intent
  EXCEPT repeat_last itself, or asking twice would nest into
  "I said: I said: ...". Module state on purpose: a repeat surviving a
  restart would be a surprise, not a feature.

facts stay in one place: where a sentence contains data (the down service
  names, the time, a temperature), the variation is in the lead-in and the
  data is interpolated once. Never write the same fact into three strings.
```

## panel commands (theme and screen)

```yaml
added: 2026-10-08. Rides the voice event WebSocket built the same day.

transport: events.hub.publish_command(name, value) ->
           {"type":"command","command":...,"value":...} over WS /voice/events
           -> useVoiceEvents -> App.tsx effect.

NOT RETAINED, and outside the state sequence. A command is a thing that
  happened once; replaying "screen off" to a browser that reconnects an hour
  later would re-blank a panel somebody is using. Retained state answers
  "what is true", commands answer "do this now".

commands:
  set_theme     value dark|light|auto -> useTheme.choose(), persisted
  sleep_screen  -> ScreenVeil
  wake_screen   -> clears it

repeated identical commands DO apply again: the UI keys the effect on the
  command object's identity, which is fresh every time. Verified by sending
  sleep_screen twice.

SCREEN OFF IS AN OVERLAY, NOT DISPLAY POWER-OFF:
  a browser cannot DPMS, and the backend runs in a container with no access
  to the host's compositor. ScreenVeil paints pure #000 (not --bg: the dark
  theme's #08090b is still visibly lit in a dark room) and is tappable, so
  nobody has to talk to a black screen to get it back.
  REAL power-off needs a host helper — `wlopm --off \*` under labwc, or
  `xset dpms force off` under X11 — plus something to call it. Worth doing
  later; this version needs no new privileges and works today.

an unrecognised command is IGNORED by the UI, not guessed at: that is a
  backend newer than the bundle, which happens on every partial deploy.
```

## testing

```yaml
status: THERE ARE NO AUTOMATED TESTS, BY DECISION (USER, 2026-10-08).
deleted: apps/backend/tests/, apps/voice/tests/, and both conftest.py files.

RULE FOR AGENTS: do not add a test file, a test directory, a test dependency,
  or CI to this repo unless the user explicitly asks for it. Adding tests
  "while you are in there" is the thing that was removed.

rationale: one operator, one panel, one Pi. The suites were larger than the
  code they guarded, and every behaviour they covered is reachable by hand in
  under a minute against a running backend.

HOW TO VERIFY INSTEAD - all of it works without audio hardware or models:

  compile check (cheap, catches the import-root mistakes this repo invites):
    python -m py_compile apps/backend/*.py apps/backend/routes/*.py \
                         apps/voice/voice_assistant/*.py

  ui:
    cd apps/ui && npm run build        # tsc -b strict + vite build
    grep -r "X-API-Key" dist/          # MUST find nothing

  backend, live:
    API_KEY=dev uvicorn main:app --port 8000     # from apps/backend
    curl -i http://127.0.0.1:8000/services                    # expect 401
    curl -H "X-API-Key: dev" http://127.0.0.1:8000/services
    curl -H "X-API-Key: dev" http://127.0.0.1:8000/voice/intents

  health transitions, without the pipeline:
    SERVICE_STALE_AFTER_S=3 uvicorn main:app --port 8000
    curl -X POST -H "X-API-Key: dev" .../voice/heartbeat   # -> Everything good.
    (wait 3s)                                              # -> voice is down.

  every intent, without audio hardware:
    for i in get_time get_date greeting get_uptime cpu_temp get_weather \\
             list_capabilities repeat_last system_health unknown; do
      curl -s -H "X-API-Key: dev" -H 'Content-Type: application/json' \\
        -d "{\"intent\":\"$i\"}" -X POST .../voice/intent; echo
    done
    # ask the same one 3+ times: the wording must change, and must never
    # repeat back-to-back

  theme and screen (watch the dashboard while this runs):
    curl -s -H "X-API-Key: dev" -H 'Content-Type: application/json' \\
      -d '{"intent":"set_theme","item":"dark"}' -X POST .../voice/intent
    curl -s -H "X-API-Key: dev" -H 'Content-Type: application/json' \\
      -d '{"intent":"sleep_screen"}' -X POST .../voice/intent

  voice pill and answer dialog, without the pipeline:
    for s in listening thinking speaking ready; do
      curl -s -H "X-API-Key: dev" -H 'Content-Type: application/json' \
        -d "{\"state\":\"$s\",\"speech\":\"Everything good.\"}" \
        -X POST http://127.0.0.1:8000/voice/state; sleep 1
    done

  the dashboard end to end:
    cd apps/ui && VITE_DEV_API_URL=http://127.0.0.1:8000 \
      VITE_DEV_API_KEY=dev npm run dev
    then drive it with the curl loop above and watch the pill.

  what to re-check after touching the event path specifically:
    - reload the page while the retained state is `speaking`: the pill must
      repaint red and the dialog must NOT replay
    - kill the backend: pill dims, keeps its colour; restart: it reconnects
    - leave it idle 20s+: the socket must survive (keepalive)
```

## conventions

```yaml
imports:
  backend: flat - `from auth import ...`, `from intents import ...`
  voice:   package-relative inside voice_assistant/ (`from . import config`),
           flat from outside (`from voice_assistant.x import y`)
  reason: both Dockerfiles copy the app dir to /app, so the app dir is the
          import root. A `backend.`/`apps.` prefix WILL break in the container.

config:
  voice: ALL config in voice_assistant/config.py, env-driven with _str/_int/
         _float/_bool helpers. Never read os.environ in a stage module.
  caveat: config.py reads the environment AT IMPORT TIME. run.py therefore
          loads .env before importing anything from voice_assistant.

audio_devices:
  prefer a NAME SUBSTRING over an index; indexes are reordered by reboots and
  replugs. config.resolve_device() accepts either.
  candidates are filtered by DIRECTION first, then by substring; a spec
  matching >1 device logs a warning and takes the first.
  HOST ALSA GOTCHA (seen on the real Pi 2026-10-07): the host's `default` PCM
  was an `asym` with no capture slave, so `arecord` failed while the hardware
  was fine. This does NOT affect the containers - host asound.conf is not
  mounted, only /dev/snd - and the pipeline never opens `default` anyway.
  Documented in docs/README_PI.md.

failure_posture:
  voice: degrade and keep listening. TTS failures, playback failures, API
         failures and per-utterance exceptions are logged, not raised. Only a
         missing model file or an unresolvable device exits.
  backend: normal HTTP error semantics.

env_files:
  - infra/docker/.env.example   # BOTH containers (compose env_file)
  - apps/backend/.env.example   # bare-metal backend
  - apps/voice/.env.example     # bare-metal voice
  real .env files are gitignored; never commit one, never put a real value in
  an .example

secrets: never hardcode a key in source, compose, docs, or this file
```

## env

| var | required | consumed_by | notes |
|---|---|---|---|
| `API_KEY` | yes | backend `auth.py`, voice `api_client.py` | shared secret; must match across both |
| `AUDIO_GID` | yes (Pi) | voice Dockerfile **build arg** | must equal `getent group audio` (29 on Pi OS); changing it needs a rebuild |
| `VOICE_INPUT_DEVICE` | no | voice `config.py` | `CARD=<alsa id>` (best), name substring, or index; default `0` |
| `VOICE_OUTPUT_DEVICE` | no | voice `config.py` | `CARD=<alsa id>` (best), name substring, or index; default `1` |
| `VOICE_API_BASE_URL` | no | voice `api_client.py` | default `http://127.0.0.1:8000` |
| `VOICE_SLM_MODEL` | no | voice `config.py` | default 1.5B Q5; swap for 0.5B Q4 to trade accuracy for speed |
| `VOICE_WAKE_WORD` | no | voice `wake_word.py` | default `models/hey_eevee.onnx`. A heed `.onnx` (sidecar beside it), an openWakeWord `.onnx`, or a bundled name |
| `VOICE_WAKE_WORD_META` | no | voice `wake_heed.py` | sidecar path override; empty = derive from the model name |
| `VOICE_WW_THRESHOLD` | no | voice `wake_word.py` | UNSET = use the model's own (0.603 for hey eevee). 0.5 is the openWakeWord default only |
| `VOICE_WW_MEL_SCALE` | no | voice `wake_heed.py` | `htk` (default) or `slaney`. Only for a preprocessing mismatch |
| `VOICE_WW_MEL_NORM` | no | voice `wake_heed.py` | `none` (default) or `slaney` |
| `VOICE_WW_LOG_BASE` | no | voice `wake_heed.py` | `e` (default) or `10` |
| `VOICE_WW_NOTCH_Q` | no | voice `wake_heed.py` | default 30 |
| `VOICE_FASTPATH` | no | voice `fastpath.py` | default true; false forces every utterance through the SLM |
| `VOICE_SLM_ENABLED` | no | voice `pipeline.py` | default true; false saves ~1.2GB RSS |
| `VOICE_VERBOSE` | no | voice `config.py` | DEBUG logs with per-stage timings |
| `VOICE_HEARTBEAT_INTERVAL_S` | no | voice `heartbeat.py` | default 15.0; 0 disables |
| `VOICE_STATE_EVENTS` | no | voice `activity.py` | default true; false stops publishing and the pill reads "unknown" |
| `VOICE_STATE_EVENT_TIMEOUT_S` | no | voice `api_client.py` | default 1.0; deliberately shorter than `VOICE_API_TIMEOUT_S` |
| `VOICE_WHISPER_ALLOW_DOWNLOAD` | no | voice `config.py` | default false. True lets Whisper fetch from HuggingFace; see the boot gotcha below |
| `SPOTIFY_CLIENT_ID` | no | backend `spotify.py` | from developer.spotify.com. Without it the Music view says "not set up" |
| `SPOTIFY_CLIENT_SECRET` | no | backend `spotify.py` | never leaves the backend |
| `SPOTIFY_REDIRECT_URI` | no | backend `spotify.py` | default `http://127.0.0.1:8000/spotify/callback`; must match the Spotify dashboard EXACTLY. `localhost` is rejected by Spotify |
| `SPOTIFY_TOKEN_PATH` | no | backend `spotify.py` | default `/app/state/spotify.json`; must be writable or authorization is lost on restart |
| `MEDIA_DIR` | no | backend `settings.py` | default `/app/media`; the sound library |
| `SCREEN_AGENT_URL` | no | `scripts/screen-agent.sh` | default `http://127.0.0.1:8080/api/screen` (through nginx, which adds the key) |
| `SCREEN_AGENT_KEY` | no | `scripts/screen-agent.sh` | only when pointing the agent straight at the backend, which requires the header |
| `SCREEN_AGENT_INTERVAL` | no | `scripts/screen-agent.sh` | seconds between polls; default 2 |
| `ALARMS_PATH` | no | backend `alarms.py` | default `/app/state/alarms.json` |
| `SETTINGS_PATH` | no | backend `settings.py` | default `/app/state/settings.json` |
| `WEATHER_LAT` | no | backend `weather.py` | required for get_weather AND the launcher's weather card; without it both say so |
| `WEATHER_LON` | no | backend `weather.py` | as above |
| `WEATHER_PLACE` | no | backend `weather.py` | spoken aloud ("12 degrees in Toronto"); empty omits it |
| `WEATHER_UNITS` | no | backend `weather.py` | `celsius` (default) or `fahrenheit` |
| `WOL_MAC` | no | backend `wol.py` | target MAC; `aa:bb:..`, `aa-bb-..` or bare hex. Unset = the Home app says it is not configured |
| `WOL_NAME` | no | backend `wol.py` | what the machine is called on screen and out loud; default "the computer" |
| `WOL_BROADCAST` | no | backend `wol.py` | default `255.255.255.255`; a subnet broadcast (e.g. `192.168.0.255`) if your network drops the global one |
| `WOL_PORT` | no | backend `wol.py` | default 9. Nothing listens; the NIC firmware reads the frame |
| `WOL_HOST` | no | backend `wol.py` | IP/hostname for the liveness probe. Unset = no status dot |
| `WOL_PROBE_PORT` | no | backend `wol.py` | default 3389 (Windows RDP). 445 or 22 work as well |
| `VOICE_STATE_REPEAT_S` | no | voice `activity.py` | default = `VOICE_HEARTBEAT_INTERVAL_S`; re-sends the current state so the pill survives a backend restart. 0 disables |
| `SERVICE_STALE_AFTER_S` | no | backend `services.py` | default 45.0; must stay a multiple of the send interval |
| `BACKEND_VERBOSE` | no | backend `main.py` | DEBUG logs |
| `BACKEND_ORIGIN` | no | ui nginx template | default `http://127.0.0.1:8000` |
| `VITE_DEV_API_URL` | no | ui `vite.config.ts` | DEV SERVER ONLY, not bundled |
| `VITE_DEV_API_KEY` | no | ui `vite.config.ts` | DEV SERVER ONLY, not bundled. Do not rename to something Vite inlines at build time |

`API_KEY` is consumed by all three containers: the backend validates it, voice
sends it, and the ui's nginx injects it into proxied requests.

Full tunable list (thresholds, recording envelope, thread counts) is in
`apps/voice/voice_assistant/config.py` and `infra/docker/.env.example`.

## docker

```yaml
compose_file: infra/docker/docker-compose.yml
build_context: ../..                   # repo root for BOTH services, NOT infra/docker
reason: the Dockerfiles COPY apps/<name>/, which is outside infra/docker
env_file: {path: .env, required: false}    # "load if present" per spec
run: cd infra/docker && docker compose up --build

backend:
  image: python:3.13-slim
  restart: always
  network_mode: host

voice:
  image: python:3.11-slim-bookworm
  restart: unless-stopped
  network_mode: host
  devices: ["/dev/snd:/dev/snd"]
  volumes: ["../../models:/app/models:ro"]
  mem_limit: 2560m          # guard: a leak must not take the API down with it
  build_args: [AUDIO_GID]
  user: non-root `eevee`, supplementary group AUDIO_GID
    NOT named `voice`: Debian base-passwd has a system group of that name
    (GID 22) and useradd's default user-group creation collides with it.
  apt_runtime: libportaudio2 libsndfile1 espeak-ng alsa-utils
    note: portaudio19-dev is NOT needed - sounddevice binds via CFFI at runtime
    note: espeak-ng is Piper's phonemiser backend

ui:
  image: multi-stage, node:22-alpine build -> nginx:1.27-alpine runtime
  restart: always
  network_mode: host
  port: 8080                # unprivileged on purpose
  mem_limit: 128m
  env: [API_KEY (required, compose fails fast), BACKEND_ORIGIN]
  nothing from the build stage ships; the runtime is nginx + a dist directory
```

### GOTCHA: NGINX_ENVSUBST_FILTER is mandatory

```yaml
what: the nginx image runs envsubst over /etc/nginx/templates/*.template using
      EVERY environment variable.
problem: without a filter it also expands nginx's own $host and $uri, which
      are not set in the environment, producing `proxy_set_header Host ;` -
      a syntax error that stops nginx booting.
fix: ENV NGINX_ENVSUBST_FILTER="^(API_KEY|BACKEND_ORIGIN)$" in the Dockerfile.
status: set, and PROVEN both ways on 2026-10-04.
```

### network_mode: host

```yaml
status: intentional, resolved 2026-10-04
decision: keep `network_mode: host`, no `ports:` (USER DECISION)
reason: deploys to a Raspberry Pi 5 running Pi OS Lite, where host networking
        is real
macos_caveat: on Docker Desktop for Mac, host mode attaches the container to
        the Docker Linux VM's network, NOT the host, so localhost:8000 is
        unreachable from the Mac. This config cannot be smoke-tested on macOS.
        Do not "fix" this by adding `ports:` - host mode and port bindings are
        mutually exclusive and Docker rejects the combination outright.
```

## pi runtime constraints

```yaml
discovered: 2026-10-07, on the real hardware

memory_cgroups_OFF_BY_DEFAULT:
  symptom: compose prints "Your kernel does not support memory limit
           capabilities or the cgroup is not mounted. Limitation discarded."
  meaning: mem_limit on the voice and ui services is INERT until fixed. The
           guard against a leak taking the API down does not exist.
  fix: append `cgroup_enable=memory cgroup_memory=1` to the single line in
       /boot/firmware/cmdline.txt, then reboot. Documented in README_PI §3b.
  verify: `cat /sys/fs/cgroup/cgroup.controllers` lists `memory`

power:
  requirement: official 27W USB-C PD (5.1V/5A). NOT a 5V/3A phone charger.
  why: four cores saturate while a 1.2GB model loads, with USB audio attached.
       A Pi 5 browns out and CUTS POWER rather than erroring. With a 3A supply
       the firmware also caps total USB current at 600mA.
  diagnosis: `vcgencmd get_throttled`; bit 0 = undervoltage now,
             bit 16 = undervoltage occurred since boot. 0x0 is clean.
  NOTE FOR AGENTS: nothing in this stack can power the board off. There is no
  shutdown call. An OOM kills a process; a panic reboots. A hard power-off is
  hardware - do not go looking for it in the code.

startup_load_spike:
  all three containers starting at once is the worst moment. Bringing them up
  one at a time (backend, ui, then voice) isolates which one trips it.
  VOICE_SLM_THREADS / VOICE_WHISPER_THREADS can drop to 3 to leave a core;
  the stages are sequential so the models never contend anyway.
```

## display session / kiosk

```yaml
researched: 2026-10-07, against Raspberry Pi forums + official docs + Debian pkgs

TRIXIE SHIPS `chromium`, NOT `chromium-browser`.
  A .xinitrc or autostart referencing chromium-browser fails with "not found",
  the client exits, and X shuts down reporting "Server terminated
  successfully" - which reads like success. kiosk.sh probes both names.

RECOMMENDED PATH IS NOW labwc (Wayland), NOT i3/X11:
  - Trixie's Pi OS defaults to Wayland; labwc is what Raspberry Pi documents
    and tests for kiosks, and Chromium is shipped built for Wayland
  - this panel runs ONE fullscreen browser, so i3's tiling buys nothing
  - labwc removes the X server, xinit, .xinitrc and the i3 config from the
    failure surface entirely
  - labwc 0.8.3 is in Debian trixie for arm64 and pulls xwayland
  - setup: apt install labwc; `exec labwc` from .bash_profile on tty1 only;
    ~/.config/labwc/autostart contains "<abs path>/kiosk.sh &" (the & is
    required or the session never finishes starting)
  i3/X11 is kept in README_PI section 8.4 as Option B, fully fixed.

THE DIAGNOSTIC THAT ACTUALLY WORKS:
  startx > ~/startx.log 2>&1   (or: labwc > ~/labwc.log 2>&1)
  Xorg.0.log records only X server activity and says NOTHING about a client
  that failed to launch. Client errors only appear on stdout/stderr.

i3 config parser traps (both fail SILENTLY):
  - LINE BASED: no backslash continuation. A multi-line exec is parsed as
    several broken commands.
  - NO ~ OR $HOME EXPANSION in exec paths. Must be absolute. The guide writes
    it with an unquoted heredoc so $HOME expands, with \$mod escaped so i3's
    own variables survive. Verified.

black screen is ambiguous:
  i3 with no window and no bar looks identical to i3 never starting.
  Super+Return -> xterm appears => i3 is alive, the browser exec is at fault.
  i3 -C -c <config> validates without starting a session.

xterm is required on Lite: there is no terminal emulator, so the
  $mod+Return escape hatch does nothing without it - and that is also the
  fastest way to tell whether i3 is running.

package check (verified on packages.debian.org/trixie):
  xserver-xorg HARD-depends on xserver-xorg-core, -input-all and -video-all,
  so the short package list is sufficient. Driver packages were NOT the cause.
```

## i3 kiosk gotchas

```yaml
discovered: 2026-10-07, on the real hardware

i3_config_is_LINE_BASED:
  i3 has NO backslash line continuation. A command split across lines is
  parsed as several broken commands and silently does nothing. This cost a
  debugging round trip: the Chromium exec was written multi-line and the
  browser never launched.
  fix: the browser lives in ~/kiosk.sh; i3 execs it on ONE line.

i3_does_not_expand_tilde_or_HOME:
  `exec ~/kiosk.sh` is passed through literally and never runs. The exec line
  needs an absolute path, written in by sed at setup time.

black_screen_is_ambiguous:
  i3 with no window and no bar looks exactly like i3 not starting. Always
  establish which before changing anything:
    Super+Return -> xterm appears => i3 is alive, the browser exec is at fault
    i3 -C -c ~/.config/i3/config  => validates without starting a session
  A temporary `bar { status_command i3status }` makes a live i3 visible.

xterm_is_required:
  Pi OS Lite ships no terminal emulator, so `bindsym $mod+Return exec xterm`
  (or i3-sensible-terminal) does nothing unless xterm is installed. That also
  removes the quickest way to tell whether i3 is running. It is in the package
  list in README_PI section 2.
```

## decisions

| date | decision | why |
|---|---|---|
| 2026-10-19 | SLM sizes its own context window from the prompt | the 22nd intent pushed the system prompt to 1048 tokens into a 1024 window and llama.cpp refused to run, crash-looping the voice container for DAYS. Adding an intent must never be able to do that again |
| 2026-10-19 | a failed classifier degrades to fast-path-only, never exits | on an always-on panel a crash loop is invisible (the pill just reads offline) and writes logs as fast as it can. A degraded assistant beats a dead one |
| 2026-10-19 | container logs capped at 10MB x 3 | the json-file driver is UNLIMITED by default, so the crash loop above was also filling the SD card |
| 2026-10-19 | agent keeps three methods only: sysfs backlight, wlr-randr, xset | ddcutil and vcgencmd were tried and ruled out on this hardware (see `## container gotchas`), and carrying dead branches in a script that runs unattended is cost without benefit. USER asked for less in the codebase |
| 2026-10-19 | screen agent writes bl_power=1, not 4 | 0/1 is what the Pi's backlight driver documents; 4 (FB_BLANK_POWERDOWN) works on some drivers and is SILENTLY IGNORED by others, which looks exactly like "off but still lit" |
| 2026-10-16 | ANY wake-word trigger wakes the screen, on `listening` only | USER. Having to touch a dark panel you have already spoken to feels broken. `listening` and not the later stages: the same utterance's `speaking` event would undo a "screen off" command it was in the middle of carrying out |
| 2026-10-16 | idle timeout defaults to 30 minutes, not never | USER. Long enough never to blank mid-glance; any voice trigger wakes it, so the cost of it being wrong is one word |
| 2026-10-16 | real screen-off via a HOST agent, not the container | USER: the UI veil left the backlight on and the panel was still bright in the dark. A container cannot reach the backlight; the agent runs in the kiosk session, where the compositor tools and the sysfs file are reachable, and holds no API key because it polls through nginx |
| 2026-10-16 | screen power is backend STATE, not just the existing WS command | a command is a thing that happened once -- an agent that starts late or misses it cannot ask what is true now. The command still fires, because it is what blanks the UI instantly while the agent polls |
| 2026-10-16 | the agent auto-detects the display rather than being configured | the method differs per panel (DSI vs HDMI) and per session (labwc vs i3), and a wrong hard-coded path fails silently at night |
| 2026-10-16 | idle auto-sleep lives in the BROWSER | it is the only party that knows about touches. The backend keeps the timeout value (a panel policy); the dashboard enforces it |
| 2026-10-16 | /etc/localtime mounted read-only into backend and voice | a container runs on UTC whatever the host is set to, and the backend computes the ALARM SCHEDULE from its local clock -- a 7:30 alarm would have fired at 7:30 UTC. Mount rather than a TZ env var: glibc reads /etc/localtime directly, so it needs no tzdata in the image and follows the host |
| 2026-10-16 | accent is RED (`--accent`), status `--down` stays red too | USER preference. Tolerable because nothing reads "red" alone as "broken": a down service is always labelled, carries a status dot, and pulses -- the accent never animates |
| 2026-10-16 | voice pill's `ready` pinned to a new `--info` token, not `--accent` | `speaking` is red and means "do not talk over this". With a red accent, `ready` would have been the same colour, so the old blue survives as its own token |
| 2026-10-16 | wake word back to `hey_jarvis` | USER: "hey eevee" fired on non-speech room noise even at 0.9. The heed engine stays in the code and the model stays installable -- only the default moved |
| 2026-10-16 | five music intents (play/pause/next/previous/restart) | USER. `restart` is a seek to zero rather than Spotify's device-dependent `/previous`, so "play it again" is never a coin flip |
| 2026-10-16 | every Spotify failure gets its own spoken sentence | "no Premium" and "nothing is playing anywhere" need opposite reactions from the person standing there; one generic apology would be useless. Mapped once in `intents._music_problem` so five handlers cannot drift |
| 2026-10-16 | fastpath matches the RAW sentence before the filler-stripped one | "again" is filler in "what's the time again" and the entire meaning of "play it again". Two passes, literal first, keeps both |
| 2026-10-16 | Dashboard (timers+alarms) is the home route; systems grid demoted to "systems" | USER: the new page is the main one. An unrecognised hash lands there too |
| 2026-10-16 | launcher shows ONLY apps without a sidebar entry | USER. Music, Systems and Settings are rail destinations; repeating them as tiles made the home screen a second copy of the navigation instead of a home for the things that have no rail entry |
| 2026-10-16 | tile sheen removed | USER. A highlight sweeping each tile on a loop is motion with nothing to say; the glance strip is where the panel should be drawing the eye |
| 2026-10-16 | cover art drifts while a track plays, three transforms on 7s/11s/13s | USER wants motion. Co-prime-ish periods only realign every ~17 minutes, so it reads as drift rather than a loop. Pausing sets animation-play-state rather than removing the animations, so the art freezes where it is instead of snapping back to square |
| 2026-10-16 | timer dial grew a SECOND ring for seconds; ring chosen at touch-down | USER wants 1-second timers. A circular gesture drifts in radius, so re-testing the radius each move would switch you from minutes to seconds halfway round a turn. Deciding once, at touch-down, means the ring you start on is the ring you keep |
| 2026-10-16 | timers.MIN_DURATION_S 5 -> 1 | the dial can now express 0:03, and clamping it up to 0:05 would make the control lie about what it is about to do. The old floor existed to stop a spoken "one second" timer firing before the confirmation finished; that is now the rarer harm |
| 2026-10-16 | alarm minutes 0-59; still NO seconds | USER. The 5-minute grid made a third of all times unreachable. Seconds stay out because FIRE_WINDOW_S is 120s -- an alarm can ring two minutes late by design, so a seconds field would be decorative |
| 2026-10-16 | wake-on-LAN is a backend feature, NOT a host agent like screen-agent.sh | the backend already runs network_mode: host, so it can broadcast directly. The screen agent exists because a container cannot reach a backlight; nothing equivalent applies here |
| 2026-10-16 | liveness by TCP connect, not ICMP ping | a raw socket needs CAP_NET_RAW, meaning a privileged container or a setuid ping binary in the image. A connect() to a port Windows already listens on needs neither |
| 2026-10-16 | one wake target, configured in .env | USER. There is no keyboard on the panel, so a MAC was never going to be typed into Settings, and this is set once |
| 2026-10-16 | wake_computer fast-path rules sit ABOVE wake_screen | the screen owns bare "wake up" and `(switch\|turn) (it) (back) on`. Anything naming a MACHINE has to be claimed first or it never reaches the new intent |
| 2026-10-16 | home became a LAUNCHER; timers and alarms split into apps behind it | USER: "a kind of application page". Sharing one screen capped both halves at controls that fit in half a column -- which is how the alarm editor ended up a +/- stepper behind an accordion. A whole screen each is what paid for the dial and the wheel pickers |
| 2026-10-16 | sidebar stays four destinations; timers/alarms are NOT in the rail | USER: keep the current sidebar. They are apps opened from the launcher, so Dashboard stays lit while you are inside one -- a rail with nothing highlighted reads as "you are nowhere" |
| 2026-10-16 | glance cards are conditional, EXCEPT weather | a card with nothing to say is noise. Weather is the exception because it is the one thing worth reading when nothing is happening, and a home screen that empties to nothing reads as broken |
| 2026-10-16 | timer duration is a DRAG, not a stepper or a text field | there is no keyboard on the Pi and no on-screen one wanted (USER), so a field was never an option, and the stepper was 45 taps for a 45-minute timer. A dial is the gesture an oven already taught everyone |
| 2026-10-16 | alarm times are scroll-snap WHEELS, physics by the browser | same no-keyboard constraint; `<input type="time">` opens a picker that assumes one. Native scrolling is the one smooth thing a Pi gets for free, so the component only reads which row ended up centred |
| 2026-10-16 | 7 alarm slots KEPT; only the controls rebuilt | USER chose this over arbitrary alarms with repeat patterns. "Copy this time to Mon-Fri" removes the tedium that would have justified the bigger model, with no migration of state/alarms.json |
| 2026-10-16 | pause sends the state it WANTS, not a toggle | a touchscreen double tap on a toggle flaps; on `{"paused": true}` it settles. Also makes the call idempotent and the UI unable to guess wrong |
| 2026-10-16 | weather got its own route, not a field on /clock/state | /clock/state is polled 1Hz and is all in memory; `weather.current()` blocks up to 4s on a cache miss, which is the dashboard's whole timeout for the poll that RINGS ALARMS |
| 2026-10-16 | timers in memory, alarms persisted | opposite lifetimes for opposite reasons: a countdown is only meaningful relative to now, a weekly schedule is still true after a reboot |
| 2026-10-16 | timers monotonic, alarms wall clock | the Pi has no RTC and steps its clock at boot. A countdown must ignore that step; an alarm must follow it |
| 2026-10-16 | alarm/timer audio plays in the KIOSK BROWSER | USER CHOICE from three options. The voice container owns the speaker but its loop is single-threaded, so a song there would deafen the wake word for minutes; the backend would need /dev/snd and a dmix setup to share the card |
| 2026-10-16 | durations parsed on the backend, not in the voice container | same rule as the wording: the backend owns the data, the classifier's job ends at handing over the words it heard |
| 2026-10-16 | /clock/state polled by the app shell, not the Dashboard view | an alarm set for 7am would be silent whenever the panel was left on Music |
| 2026-10-16 | theme control moved from the top bar to Settings | USER: free the top bar for status icons. Storage stays per-browser localStorage -- a theme belongs to a display, not the house |
| 2026-10-16 | sounds are files in a read-only bind mount, not uploads | `scp` is the whole interface, and there is no upload endpoint to defend |
| 2026-10-16 | music view is full bleed, no top bar | USER: the clock, voice pill and connection readout are noise in front of an album cover. The sidebar stays, so there is always a way out of the view |
| 2026-10-16 | VOICE_WW_THRESHOLD=0.9 on the Pi, overriding the sidecar's 0.603 | USER: the calibrated value fired on non-speech room noise. Env only, no rebuild, and the sidecar stays the documented default for anyone else |
| 2026-10-16 | dashboard became an SPA: sidebar rail + hash router | USER: multiple views. Chrome (clock, voice pill) stays global because those two must be readable on every page |
| 2026-10-16 | hand-written hash router, not react-router | two views, no params, no loaders. ~20 KB and an npm dependency to replace 30 lines, on a bundle that is built on the Pi |
| 2026-10-16 | Spotify: UI polls the BACKEND at 1Hz, backend polls Spotify on a TTL | Spotify sees one request every few seconds regardless of how many dashboards are open, and a page nobody is looking at costs nothing. Progress is interpolated client-side, so 1Hz looks continuous |
| 2026-10-16 | no background poller task; refresh inside the stale request | same shape as weather.py. No concurrency to supervise, and demand-driven by construction |
| 2026-10-16 | progress bar is a READOUT; no scrub | USER DECISION. Also removes the only drag gesture on the page, which is what a touch panel handles worst |
| 2026-10-16 | cover art proxied through the backend | same-origin pixels for the colour extraction (no CORS dependency), no direct CDN access needed from the kiosk, and immutable so it caches for a year |
| 2026-10-16 | OAuth callback route is KEYLESS, protected by a single-use state | the browser Spotify redirects has no API key and nginx only injects on /api/*. /login mints the state and DOES require the key, so no key means no state means the callback refuses |
| 2026-10-16 | dominant colours by hand (32x32 canvas histogram), not node-vibrant | two colours behind large text is a lower bar than perceptual palette extraction, and this runs on every track change on a Pi |
| 2026-10-15 | wake word = "hey eevee" heed export, own frontend in `wake_heed.py` | USER supplied the model. openWakeWord cannot load it: different input contract (log-mel vs its own embedding frontend), so the sidecar's chain had to be reimplemented on numpy+scipy rather than configured |
| 2026-10-15 | engine chosen by sidecar presence, not an env var | one less thing to set wrong; `hey_jarvis` and openWakeWord exports keep working untouched |
| 2026-10-15 | threshold defaults to the sidecar's, not 0.5 | 0.603 is what the model was calibrated at; a hardcoded default would silently detune it |
| 2026-10-15 | audio devices pinned by udev `ATTR{id}`, addressed as `CARD=<id>` | USER: the mic and speaker are permanent. The id survives replugs and cannot go ambiguous the way a `USB` substring does. CORRECTION, same day: a card id is NOT a PortAudio device name, so `resolve_device()` had to learn the `CARD=` form -- the first version of the guide told the user to use the bare id and the pipeline exited with "No output device matching 'eeveespk'". SECOND CORRECTION 2026-10-16: that form first resolved the id through /proc/asound, which is masked inside the container; it now uses libasound (see the row below) |
| 2026-10-16 | card id resolved through libasound (ctypes), not /proc/asound | /proc/asound is on the container runtime's DEFAULT MASKED PATHS, so Docker mounts an empty tmpfs over it: the host prints four cards, the container sees nothing. libasound uses ioctls on /dev/snd, already mapped in for the hardware. No new package -- libportaudio2 already links it |
| 2026-10-15 | audio devices resolved before any model loads | the same failure surfaced only after a 216 s cold SLM warmup on the Pi. A config error knowable in 50 ms must not cost minutes |
| 2026-10-04 | header name `X-API-Key` | conventional for static shared secrets |
| 2026-10-04 | flat imports in each app | container copies the app dir to /app root |
| 2026-10-04 | compose build context = repo root | Dockerfiles must reach apps/<name>/ |
| 2026-10-04 | `env_file.required: false` | spec said load .env "if present" |
| 2026-10-04 | `.env` gitignored, `.env.example` committed | keep secrets out of VCS |
| 2026-10-04 | backend python 3.13, port 8000 hardcoded | default; not externalized |
| 2026-10-04 | `network_mode: host`, no ports | Pi deploy target (user) |
| 2026-10-04 | voice talks HTTP, not in-process | independence spec forces separate containers |
| 2026-10-04 | backend composes the speech string | it owns the data; keeps wording out of the voice image; stops a small model inventing statuses |
| 2026-10-04 | intents fetched from the API at boot | kills the prompt/grammar/handler drift the prototype had |
| 2026-10-04 | voice python 3.11 | no aarch64 wheels for 3.13 |
| 2026-10-07 | pins verified against the real index, not assumed | `piper-onnx~=0.1` was a guess; the project only ever published 1.0.x, so the pin matched nothing and failed minutes into a Pi build. Full graph now verified: 63 wheels, no source builds |
| 2026-10-07 | keep the bookworm BASE IMAGE although the host is Trixie | a container brings its own userland, so host Debian/Python are irrelevant. Bookworm is the release these aarch64 wheels were built against; changing it adds risk for no gain |
| 2026-10-04 | Qwen2.5-**1.5B Q5_K_M** | USER: accuracy over latency. Supersedes the initial 0.5B/Q4 choice |
| 2026-10-04 | regex fast path before the SLM | the 1.5B costs 4-5s; keeps common commands ~2s |
| 2026-10-04 | large models bind-mounted, small ones baked | 1.3GB image is unwieldy; no first-boot network dependency either |
| 2026-10-04 | voice `restart: unless-stopped` not `always` | a missing model exits non-zero; `always` would restart-loop |
| 2026-10-04 | voice runs non-root in group AUDIO_GID | least privilege while keeping /dev/snd reachable |
| 2026-10-04 | frame-based pre-roll deque | the prototype's per-sample `tolist()` allocated 1280 Python ints every 80 ms, forever |
| 2026-10-04 | dropped per-service intents; one `system_health` | USER: only overall health is wanted. Supersedes `service_status`/`list_services` |
| 2026-10-04 | removed the minecraft placeholder | USER: not a real service yet; a declared-but-unprobed entry was noise |
| 2026-10-04 | health by **heartbeat**, not probing | USER RATIONALE: a dead pipeline cannot report itself, so the dashboard must infer it from silence |
| 2026-10-04 | never-checked-in counts as DOWN, not unknown | "unknown" would hide a failed boot |
| 2026-10-04 | heartbeat state in-memory, not persisted | heartbeats only mean anything relative to now; stale timestamps from disk would lie |
| 2026-10-04 | `time.monotonic()` for staleness | a Pi without an RTC steps its wall clock at boot, which would fake an outage |
| 2026-10-04 | `/services` unprefixed, own route module | system-wide, not voice-scoped; must serve the dashboard when voice is down |
| 2026-10-04 | heartbeat starts BEFORE model loading | loading the 1.5B takes long enough that voice would otherwise report down through its whole startup |
| 2026-10-04 | UI = Vite + React static, NOT Next.js | USER choice from options. No SSR need (one viewer, no SEO, live-polled), and a Node runtime would cost RAM next to the SLM + Chromium |
| 2026-10-04 | nginx container in front of the UI | the deciding reason: it injects X-API-Key so the browser never holds the secret. Also lets the dashboard load and report the backend down |
| 2026-10-04 | UI not served from FastAPI StaticFiles | a dead backend would mean a blank screen exactly when the dashboard is most needed |
| 2026-10-04 | hand-written CSS, no Tailwind | the theme is a token swap; tokens + a few primitives need no utility framework |
| 2026-10-04 | CSS animations only, no motion library | keyframes stay on the compositor; a JS library adds weight and main-thread work the Pi does not need |
| 2026-10-04 | no backdrop-filter / glassmorphism | per-frame blur over a large area is the worst thing for this GPU. Static gradients carry the visual weight |
| 2026-10-04 | fonts self-hosted, latin subset, hand-declared | the Pi may boot offline; the package's index.css ships ~150KB of unused scripts |
| 2026-10-04 | dev-tool aesthetic (Linear/Vercel/Raycast) | USER: "programmer dashboard, NOT hacker, but like a dev" |
| 2026-10-04 | touch-first sizing, 56px floor | USER: touchscreen, targets bigger than mouse/keyboard |
| 2026-10-04 | fluid clamp() type + auto-fit grid | USER has not measured the panel yet; avoids committing to a breakpoint |
| 2026-10-04 | heartbeat trail is client-side, labelled "since load" | the backend reports current state only; implying persisted uptime would be a lie |
| 2026-10-08 | voice activity over **WebSocket**, not MQTT | USER left the choice open. Publisher and subscriber already both speak HTTP to the backend, so this is one endpoint on the existing port behind the existing nginx. MQTT would add a broker to supervise, retained/QoS semantics and paho in two more images for the same ~1ms. The one MQTT feature that was needed - a retained message - is four lines in events.py |
| 2026-10-08 | activity events are separate from the heartbeat | different questions on different timescales: "is it alive" (45s window, polled) vs "what is it doing now" (must be pushed within a frame). Merging them would make the pill as slow as the poll |
| 2026-10-08 | no word-by-word streaming transcript | USER DECISION after being shown the cost: partials need Whisper re-run on a growing buffer every ~0.7s, and tiny.en rewrites itself visibly on short audio. The final transcript is pushed the moment STT returns, before classification |
| 2026-10-08 | dialog shows the response only | USER DECISION. The transcript lives next to the pill instead, where it is useful while thinking rather than after the answer |
| 2026-10-08 | dialog holds 7s but never cuts off speech | USER spec was 7s; hiding an answer still being read aloud would be worse, so the hold and the speaking state both have to end |
| 2026-10-08 | state events published off-thread | `listening` is published before recording starts; a blocking POST would sit between the wake word and the open microphone |
| 2026-10-08 | identical republishes refresh rather than re-event | the reporter re-sends state on a timer so the pill survives a backend restart; bumping seq for those would re-announce a months-old answer every 15s |
| 2026-10-08 | the UI ignores the retained event for the dialog, not the pill | the pill wants the replayed state; the dialog replaying it meant every kiosk reload popped up the last answer |
| 2026-10-08 | pill falls back to the heartbeat when voice is down | the event stream only reports what a live pipeline says; a pipeline that died mid-utterance would leave the pill green forever |
| 2026-10-08 | Whisper loads with `local_files_only=True` by default | the weights are baked in, and letting faster-whisper revalidate against HF turned a healthy cache into a boot failure on the real Pi. Opt back in with VOICE_WHISPER_ALLOW_DOWNLOAD |
| 2026-10-08 | SLM response re-wording BUILT AND THEN REVERTED, same day | USER tried it and the latency was worse than expected. The 2026-10-04 rule stands unchanged: the model classifies, the backend writes every word. Do not propose this again without new latency numbers from the Pi |
| 2026-10-08 | variation comes from hand-written variants, >=3 per answer | gives the thing the re-wording was wanted for at zero latency and zero risk of a model stating something it never looked up |
| 2026-10-08 | _pick() refuses to repeat back-to-back | plain random repeats about a third of the time with three options, which reads as broken. Keyed on CALL SITE, not string identity — f-string variants are new objects every call, which is how the first version silently remembered nothing |
| 2026-10-08 | nine new intents, all answered from local data except weather | everyday questions the panel can answer without an account anywhere |
| 2026-10-08 | theme + screen reach the panel over the event bus as COMMANDS | not retained and outside the state sequence: replaying "screen off" to a browser reconnecting an hour later would fight the user |
| 2026-10-08 | "screen off" is a black overlay, NOT display power-off | a browser cannot DPMS, and the backend is in a container with no compositor access. Real power-off needs a host helper; the overlay kills the light today with no new privileges |
| 2026-10-08 | weather via Open-Meteo, urllib, no key | the only intent needing the network; a provider requiring a secret would be the heaviest dependency in the project. urllib because one GET per 10 min does not justify a third HTTP client |
| 2026-10-08 | ALL automated tests deleted; none to be added | USER DECISION: single-user project, one operator, and the suites were more code than the features they guarded. Verification is manual and live - see `## testing` |

## verified

```yaml
date: 2026-10-04
environment: macOS dev host, python 3.13 venv, no Pi hardware

NOTE: the test suites referenced in this section were DELETED on 2026-10-08
(USER DECISION, see `## decisions` and `## testing`). The runs below did
happen and the behaviour they proved is still the behaviour in the code — but
they are no longer repeatable. Re-verify by hand.

passed:
  - "2026-10-16 macOS, REAL backend (uvicorn in a venv) + vite + the browser
     pane at 1024x600, light AND dark: the launcher trim, the wake app, the
     two-ring dial and second-level alarms.
     WAKE: magic packet verified byte for byte against a local UDP listener
     -- 102 bytes, 6x 0xFF then the MAC 16 times, sent 3 times; a bad or
     short MAC is refused with a sentence rather than an exception; the probe
     reports False on a closed port and None with no WOL_HOST. The Home app
     sent a real packet from the button (backend logged it) and resolved to
     'the PC is up'. Broadcast was pointed at 127.0.0.1 on purpose -- a dev
     machine should not spray magic packets across someone's network.
     VOICE: 18 wake_computer phrasings (computer/pc/desktop/machine/tower/
     brother, wake/turn on/power on/boot/start up, plus trailing filler) all
     fast-path to wake_computer, and 16 existing phrasings -- including bare
     'wake up', 'turn it back on' and 'good night' -- were unaffected.
     DIAL: wound to 0:00, then a quarter turn = 15:00, one turn = 1:00:00,
     two turns = 2:00:00, twelve turns clamped at 12:00:00, inner ring 120deg
     = 0:20, inner 270deg carried 36:10 -> 36:55. 2:07 dialled and started
     reached the backend as '2 minutes 7 seconds'; a 3-second timer was
     accepted and rang (the old floor was 5s).
     ALARMS: minute wheel is 60 rows and saved Friday 10:43 AM through the
     real API -- a time the 5-minute grid could not express.
     MUSIC: the three drift animations resolve at 7s/11s/13s, are paused by
     default, all run under .is-playing, and fade-in still runs on mount; the
     sheen keyframe is gone from the bundle.
     NOT VERIFIED: a REAL wake of the actual Windows PC (no such machine
     here, and the broadcast was deliberately looped back), real touch drags
     and flicks on the Pi, the drift against real album art (no Spotify
     credentials in this environment), and the animations' real cost on a Pi
     GPU."
  - "2026-10-16 macOS, REAL backend (uvicorn in a venv) + vite + the browser
     pane at 1024x600, light AND dark: the launcher/timers/alarms rebuild.
     Launcher showed the conditional glance strip (timer card with its
     progress hairline, next-alarm card, always-on weather card reading a
     REAL Open-Meteo response through the new GET /weather) and app tiles
     with live state. Timers: the dial drag set 8:00 and armed Start; pause
     froze a timer at 0:22, dimmed it, greyed its ring, dropped it below the
     running one, cleared ends_at and changed the subtitle to
     \"1 running - 1 paused\"; resume restored all of it; backend logged one
     pause/resume per tap. Alarms: the week strip rendered all seven,
     Friday preselected; the hour wheel moved Friday 7:00 -> 10:00 AM through
     the real API and did not fight the scroll back; Copy to Mon-Fri enabled
     five days and turned the button green. The shell RingingBanner still
     fired over the alarms app, proving the app split did not move it out of
     the shell. Weather initially returned status=unavailable with
     CERTIFICATE_VERIFY_FAILED until certifi was installed -- exactly the
     failure weather.py documents.
     NOT VERIFIED: real touch flicks and drags on the Pi (a synthetic mouse
     wheel does not move a scroll-snap wheel; the read-back was driven
     programmatically instead), the aura/sheen animations' real cost on a Pi
     GPU, and audible playback."
  - "2026-10-19 macOS: ddcutil path driven with a stand-in `ddcutil` on PATH
     and no backlight file or DISPLAY, which reproduces the user's Pi.
     Detection picks ddcutil; off sends `setvcp 10 0` then `setvcp D6 05`;
     wake sends `D6 01` then restores the brightness READ FROM THE PANEL (64
     in the test), not a guessed 100. Moving that read above the --test block
     was needed for the test path to restore correctly.
     NOT VERIFIED: a real DDC/CI panel."
  - "2026-10-19 macOS: SLM context sizing against the REAL 22-intent
     prompt -- 4022 chars, estimated 1257 tokens (vs the 1048 llama.cpp
     actually counted on the Pi, so the estimate errs high as designed),
     _fit_context keeps 2048 today and grows to 2560/3584 at +30/+60
     intents, and an explicit larger n_ctx is never shrunk.
     Agent --test verified end to end on a stand-in bl_power: writes 1,
     waits, writes 0. That test ALSO caught a real bug -- the --test block
     sat above the apply() definition, so on macOS it silently ran
     /usr/bin/apply instead; moved below the function.
     NOT VERIFIED: any of it on the Pi, and no real panel was darkened."
  - "2026-10-16 macOS, real backend + agent: a fresh install reports
     screen_timeout_min=30; voice sleep_screen drove the stand-in backlight
     to 4; a following state=listening woke it to 0 with source="wake word";
     and a full utterance (listening -> thinking -> sleep_screen -> speaking
     -> ready) left it OFF, proving the later stages do not undo the command
     they are carrying out. Fastpath: 26 phrasings including 15 screen ones,
     zero regressions."
  - "2026-10-16 macOS, real backend + the real agent script + browser: the
     whole screen-off loop. Top-bar button -> POST /screen source=button ->
     agent wrote 4 to a stand-in bl_power; tap on the veil -> source=touch
     -> wrote 0; voice sleep_screen/wake_screen did the same through
     /voice/intent. Detection picked sysfs; with no key the agent logged
     the 401 ONCE and deliberately did not touch the screen.
     screen_timeout_min round-trips and rejects junk (400), and sound
     validation still rejects a missing file.
     NOT VERIFIED: a real backlight, the wlr-randr/xset/vcgencmd paths (no
     Pi here), and the udev rule."
  - "2026-10-16 macOS, REAL backend (uvicorn) + browser at 1024x600:
     timers fire and ring and clear on stop-all; a 6s timer showed the ringing
     banner and the browser fetched the sound (206 Partial Content, i.e. the
     <audio> element really played it); alarm set for the current minute rang,
     stopped, did NOT re-ring, and recorded last_fired to disk; alarms
     persisted to alarms.json; settings rejected a sound outside the media dir
     (400) and a traversal path on /clock/sounds (404); the alarm hour stepper
     moved Wednesday 6:45 PM -> 7:45 PM through the real API; sidebar order and
     the Settings page render correctly; top bar shows the timer count and the
     alarm bell.
     NOT VERIFIED: audible playback (no speaker here), the voice path end to
     end on the Pi, and anything about Chromium's autoplay policy in kiosk
     mode."
  - "2026-10-16 macOS, real backend + browser at 1024x600: after the audio
     fix, a fired timer fetches its sound EXACTLY ONCE (206 Partial Content),
     plays without any gesture, and auto-stops when the file ends (one
     POST /clock/timers/stop-all). No Play button, no console warnings, no
     repeated fetches -- the pre-fix behaviour was a fetch and an abort per
     second. Red accent verified on the Dashboard, Settings and the sidebar.
     NOT VERIFIED: Chromium's kiosk autoplay policy on the Pi (the browser
     pane here has its own), and audible output (no speaker)."
  - "2026-10-16 macOS: music intents exercised directly against a stubbed
     spotify module -- all five succeed and each of the seven failure statuses
     (plus an unknown one) produces its own distinct sentence; 'pause' on
     already-paused music answers 'Already paused' instead of the Premium
     warning. Fastpath: 25 phrasings, 13 of them music, zero regressions on
     time/theme/health/weather/timer/repeat.
     NOT VERIFIED: against a real Spotify account or on the Pi."
  - "2026-10-16 macOS: timer intents exercised directly -- set/cancel/status
     wording, the ambiguity branch when two timers run, and fast-path regexes
     for 15 phrasings with no regressions on time/theme/health/weather."
  - "2026-10-16 macOS, browser at 1024x600 against the mock: music view
     measures exactly 0..600 vertically and 68..1024 horizontally (sidebar
     0..68), so it is genuinely full bleed with no gap; controls centred on
     the progress bar; the Systems view keeps its top bar."
  - "2026-10-16 macOS, python:3.11-slim-bookworm container with libasound2:
     voice_assistant.alsa loads libasound.so.2, every ctypes signature is
     accepted and card_index/list_cards/describe_cards run without crashing,
     returning None/[] where the VM has no sound cards.
     NOT VERIFIED: the id->number mapping against real hardware. No ALSA cards
     exist on this host; the Pi's next rebuild settles it in seconds, since
     device resolution now runs before any model loads."
  - "2026-10-16 macOS: backend via fastapi TestClient -- key required on
     /spotify/now-playing (401 without), unconfigured/unauthorized statuses
     correct, bad action 400, bad art id 404, callback with an unknown state
     400, state verified single-use (True then False), token file written
     0600 and removed by disconnect, /services still mounted."
  - "2026-10-16 macOS: UI built clean (tsc -b + vite, 254KB js / 79KB gzip)
     and driven in a browser at 1024x600 against a MOCK backend. Verified:
     sidebar switches views, music view centred with equal-width halves,
     dominant-colour background (magenta/teal from a two-colour cover, and the
     DERIVED second colour from a monochrome one), paused vs playing icons,
     progress bar + second counter advancing, the connect screen. Console
     clean apart from the mock having no WebSocket.
     NOT VERIFIED: a real Spotify account, Premium controls, the OAuth
     round trip, and anything on the Pi itself."
  - "2026-10-16 FIXED a pre-existing bug found by that run: two polls landing
     in the same millisecond produced duplicate Sparkline React keys
     (useServices.ts). StrictMode's double mount-effect triggers it every
     dev boot; a retry could do it in production."
  - "2026-10-15 macOS, simulated Pi device list (the user's real one, from
     /proc/asound/cards + PortAudio): CARD=eeveemic -> [0], CARD=eeveespk ->
     [1], hw:CARD= form, name substring and raw index all resolve correctly;
     a bare `eeveespk` raises and the message now names CARD=eeveespk as the
     fix. OPEN: not yet run on the Pi itself."
  - "2026-10-15 macOS, onnxruntime 1.31 venv: wake_heed on hey_eevee_model/
     wake.onnx -> mel tensor (1,40,101), MATCHING the shape the export's own
     README documents. Negatives behave: white noise peak prob 0.052, 440Hz
     tone 0.021, silence skipped entirely by the energy gate (prob 0.0).
     Model cost 0.26 ms/frame on a desktop CPU.
     NOT VERIFIED: a positive clip. No 'hey eevee' recording available here,
     so the unpinned mel conventions remain ESTIMATED, not measured."
  - "[suite since deleted] apps/voice logic tests -> 55 passed"
      covered: fastpath hits/misses/pruning/filler, GBNF dash-last regression
  - "[suite since deleted] apps/backend logic tests -> 13 passed"
      covered: never-seen=down, stale transition, recovery, 1/2/3-service
               phrasing, partial outage, monotonic-clock requirement
  - "all modules py_compile clean (backend + voice)"
  - "bash -n scripts/fetch-voice-models.sh"
  - "docker compose config -> both services valid"
  - "backend HTTP: every endpoint 401 unauthenticated (GET /services included)"
  - "backend HTTP: GET /voice/intents returns the 3-intent catalogue"
  - "backend HTTP: removed intents (service_status, list_services) -> unknown"
  - "backend HTTP: hallucinated intent name -> downgraded to unknown"
  - "backend HTTP: item forced to null for needs_item=false intents"
  - "backend HTTP: malformed body -> 422"
  - "LIVE heartbeat cycle with SERVICE_STALE_AFTER_S=3:
      no beat        -> 'voice is down.'
      after beat     -> 'Everything good.'
      t+3s no beats  -> 'voice is down.'
      beat again     -> 'Everything good.'
     GET /services agreed with the spoken answer at each step"
  - "api_client with API DOWN -> fallback catalogue, speakable error, no raise"
  - "api_client with WRONG KEY -> fallback catalogue, 'rejected my credentials'"
  - "api_client with API UP -> full transcript->fastpath->API->speech chain"
  - "UI: npm run build clean; tsc strict passes"
  - "UI rendered in a real browser at 1280x800 AND 1024x600, against the live
     backend, covering: healthy, down, mixed, live down->heartbeat->'Everything
     good.' transition, near-stale amber at 36s/45s, backend killed mid-session
     (retrying(n) + paused ring + stale badge + last-good retained), cold load
     with no backend ('Backend unreachable'), all 3 theme modes, auto resolving
     to dark at 8:41 PM, theme persisted across reload, detail sheet open/dismiss"
  - "UI PRODUCTION bundle served through an nginx-equivalent proxy -> works"
  - "API KEY ABSENT from every served file (grep of dist/); bundle references
     only the literal string '/api'"
  - "no browser console errors"
  - "envsubst proven BOTH ways: without NGINX_ENVSUBST_FILTER the template
     yields 'proxy_set_header Host ;' (nginx would fail to boot); with the
     filter, $host/$uri survive. The filter IS set in the Dockerfile."

date: 2026-10-08
environment: macOS dev host, python 3.13 venv, Chromium via the in-app browser

passed:
  - "[suites since deleted, same day] backend 27 passed, voice 64 passed.
     The event-hub and reporter behaviour they covered - retained event,
     bounded queue, unknown-state downgrade, identical-republish dedupe,
     non-blocking publish - was ALSO proven live below, which is why deleting
     them lost no verification."
  - "LIVE backend on :8777, real WebSocket client:
      bad API key           -> closed 1008 'Invalid or missing API key'
      no API key            -> closed 1008
      publish before connect-> retained event delivered on connect
      full utterance        -> listening/thinking/speaking/ready all pushed,
                               0.8-1.2ms from POST to client receive
      unknown state name    -> 200, delivered as 'unknown' (no 500)
      two dashboards        -> identical seq to both; subscribers=2
      disconnect            -> subscribers back to 0
      idle socket           -> {'type':'ping'} at exactly 20.0s"
  - "LIVE UI in Chromium against that backend, dev server, 1280x800 and
     1024x600, both themes:
      pill blue/green/amber/red on the real event stream
      transcript shown beside the pill during thinking
      dialog measured: appeared on the speaking event, hidden 7001ms later
      10s 'speech' -> dialog still up at 10s, hidden the instant ready arrived
      same answer twice -> dialog re-triggered, not swallowed
      backend killed -> pill dims (data-stale), keeps its last colour
      backend restarted -> reconnected by itself, subscribers=1
      heartbeat stale (SERVICE_STALE_AFTER_S=3) -> pill 'Voice offline',
        overriding the stale 'ready' event
      reload while the retained state is 'speaking' -> pill repaints red, the
        dialog does NOT replay; a genuinely new answer right after still shows
      identical republish -> no new dialog, pill unchanged"
  - "UI build clean, tsc strict passes; API key still absent from dist/"
  - "WHISPER OFFLINE LOAD, reproduced and fixed on the dev host:
      against a TCP server that ACCEPTS then hangs up (the Pi's condition),
      with a complete cache present:
        local_files_only=False -> RemoteProtocolError, identical to the Pi
        local_files_only=True  -> loaded from cache in 0.19s
      against a REFUSED port, both load fine - which is why this never
      reproduced without the hang-up server, and why a dev box with no network
      is not a valid test of it"
  - "13 INTENTS, live backend: every handler returns a sentence; set_theme
     maps synonyms (night->dark) and rejects nonsense ('purple') with help
     rather than an error; repeat_last never nests ('I said: I said:') and
     says so when there is nothing behind it; unknown still hardcoded"
  - "PHRASING VARIATION: 30 consecutive calls per intent -> 0 back-to-back
     repeats, after fixing _pick's call-site key. AST check: every _pick group
     in the module has >= 3 options"
  - "FAST PATH: 35 routing probes across all 13 intents, 35/35 as intended,
     including the four that MUST fall through to the SLM ('tell me a joke',
     'turn on the lights', 'play some music', 'hello can you turn on the
     lights'). Conflicts found and resolved: 'go dark' belongs to
     sleep_screen not set_theme, and bare 'wake up' must be wake_screen
     because sleep_screen's reply tells the user to say it"
  - "SYSINFO against a fabricated /sys tree: picks the cpu-thermal zone over
     a bogus zone0 reading 0C; hot (83C), warm (72C), cool (58C) and
     no-sensor paths all produce the right sentence; human_duration across
     30s/90s/1h/1.5h/1d/4d"
  - "WEATHER live against Open-Meteo: real reading for Toronto, spoken three
     ways. CERTIFICATE_VERIFY_FAILED found on the dev host and fixed via a
     certifi-preferring SSL context plus ca-certificates in the backend image"
  - "THEME + SCREEN in Chromium against the live backend: set_theme light/
     dark/auto all applied and persisted to localStorage; sleep_screen raised
     the veil, wake_screen cleared it, a REPEATED sleep_screen applied again
     (not swallowed), and tapping the veil dismissed it without the assistant"

NOT verified - no hardware available:
  - sysinfo.py against the REAL Pi. /proc/uptime is safe, but the thermal zone
    layout was faked on the dev host — macOS has neither path. Confirm
    `cat /sys/class/thermal/thermal_zone*/type` on the Pi shows cpu-thermal.
  - the SLM classifying the nine new intents. The grammar and prompt examples
    are in place and the fast path covers the common phrasings, but no model
    has been asked to choose between 13 intents yet; the previous catalogue
    had 3.
  - any audio path: mic capture, wake word, VAD, Whisper, Piper, playback
  - the SLM: model not downloaded, llama-cpp-python not installed
  - the nginx `location = /api/voice/events` block. No nginx binary and no
    Docker daemon on the dev host, so the WebSocket was proven through the
    Vite dev proxy instead. The directives are standard (Upgrade/Connection +
    a long proxy_read_timeout) but they are UNRUN.
  - the activity reporter in situ against the real pipeline. Its threading and
    queue behaviour were exercised by a suite that no longer exists; the
    pipeline call sites were never covered either way, because they need audio
    hardware
  - the heartbeat THREAD in situ (heartbeat.py). The endpoint and the
    staleness logic are both verified; the daemon thread that drives them has
    only been verified by inspection, because starting it requires the full
    pipeline and therefore the models and audio devices.
  - ANY Docker image actually building. The dev host has no running Docker
    daemon, so all three Dockerfiles are unbuilt. `docker compose config`
    validates, which is syntax only.
  - real touch gestures (the sheet drag was exercised with a mouse pointer;
    pointer events cover both, but no finger has touched it)
  - Chromium kiosk, i3, and actual framerate on a Pi
  - the UI at any resolution other than 1280x800 and 1024x600
  - either Docker image actually building (needs aarch64 + the model files)
  - network_mode: host reachability (impossible to test on macOS, by design)
  - every latency figure for the 1.5B model is an ESTIMATE extrapolated from
    the prototype's 0.5B measurements, not a measurement
```

## backlog

```yaml
blocking: none

next_up:
  - run on the actual Pi (USER: next task). Build all 3 images, verify audio
    end-to-end, verify the kiosk, measure framerate
  - measure the panel resolution and tune the clamp() floors/ceilings
  - verify the heartbeat thread in situ
  - measure real 1.5B/Q5 latency and correct the table in docs/VOICE_SETUP.md
  - add fastpath rules for phrasings that show up as "Classified by SLM"

unstarted:
  - no automated tests anywhere, and none wanted (USER DECISION 2026-10-08).
    Do not add a suite, a test file, or CI unless the user asks.
  - no CI
  - heartbeat history is not persisted, so the trail resets on reload. Real
    uptime history needs server-side storage.
  - "screen off" is a UI overlay, not display power-off. A host helper
    (`wlopm --off \*` under labwc) would make it real; see `## panel commands`.
  - weather has no forecast, only current conditions, and no "will it rain
    later". Open-Meteo returns both; only `current` is requested.
  - no word-by-word streaming transcript. Would need Whisper re-run on a
    growing buffer during recording; declined 2026-10-08 (see `## decisions`).
    If revisited, VOICE_STATE_EVENTS and the `thinking` transcript field are
    already the delivery path - only stt.py and recorder.py would change.
  - voice has no barge-in: it cannot be interrupted mid-response
  - single static API key; no rotation, no per-client keys, no rate limiting
  - backend port 8000 and python version hardcoded, not env-driven
```

## mqtt

```yaml
status: NOT IMPLEMENTED, and still deliberately deferred. REVISITED
        2026-10-08 when sub-second push WAS needed for the voice pill — one of
        the revisit triggers below — and rejected again in favour of a
        WebSocket on the existing backend. There is still exactly one
        publisher (the voice pipeline) and one subscriber (the panel), both
        already speaking HTTP to the backend, so a broker buys nothing a 60-
        line hub did not. See `## voice activity`. The remaining triggers
        (3+ publishers, off-box publishers, "it crashed at 3am" event history)
        are all still unmet.
context: user plans a status screen polling service health. Only `voice` is
         tracked today; more services are expected later.
recommendation: wait. Build the screen against GET /services polling first.
rationale:
  - GET /services already serves exactly what the dashboard needs
  - the heartbeat mechanism already gives push-style freshness without a broker
  - a 2-5s poll of a loopback endpoint is trivially cheap on a Pi
  - MQTT adds a broker to supervise, retained-message and QoS semantics, and
    a second transport alongside HTTP, for no present gain
revisit_when: any ONE of
  - sub-second or push-driven UI updates are needed  # MET 2026-10-08, solved
                                                     # with a WebSocket instead
  - 3+ independent publishers exist
  - something off-box needs to publish status
  - a service must emit events the API cannot synchronously answer for
    (e.g. "it crashed at 3am" rather than "it is down now" - this is the most
     likely trigger, and heartbeat staleness does not capture it)
if_adopted: keep HTTP as the request/response path and use MQTT only for
            status fan-out. Do not route voice intents over it.
```

## update_protocol

On ANY change to this repo, update the sections that change:

```yaml
always:
  - meta.last_updated -> today's date (absolute, YYYY-MM-DD)
on_new_or_changed_route:   [## routes]
on_new_env_var:            [## env, the relevant .env.example files]
on_new_file_or_dir:        [## layout]
on_dependency_change:      [## stack, the relevant requirements.txt]
on_docker_change:          [## docker]
on_architectural_choice:   [## decisions (append row, never rewrite history)]
on_manual_verify:          [## verified]   # there is no test suite; see ## testing
on_new_intent:             [## intent system, apps/backend/intents.py only]
on_voice_pipeline_change:  [## voice pipeline]
on_finishing_backlog_item: [## backlog (remove it), ## verified]
on_discovering_a_defect:   [## backlog, or an OPEN ISSUE block in the owning section]

rules:
  - NEVER add tests, a test directory, a test dependency or CI unless the user
    asks. Removed deliberately on 2026-10-08; see `## testing`
  - append to `## decisions`; do not delete or edit past rows
  - keep this file factual. no prose, no narration, no persuasion
  - state absolute dates, never "recently" or "last week"
  - distinguish VERIFIED from ESTIMATED. Never promote an estimate to a
    measurement without running it
  - if a section would become wrong, fix it rather than leaving it stale
  - if you hit something surprising that cost you time, record it so the next
    agent does not repeat it
```
