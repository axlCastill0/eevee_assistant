# AGENT_CONTEXT

Machine-oriented state file for coding agents. Read fully before any change.
UPDATE THIS FILE IN THE SAME COMMIT AS ANY CHANGE IT DESCRIBES. See `## update_protocol`.

```yaml
meta:
  project: eevee_assistant
  root: /Users/tako/root/eevee_assistant
  last_updated: 2026-10-08
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
    weather.py        Open-Meteo lookup, cached, no API key
    services.py       SERVICE HEALTH - heartbeat registry + summarize()
    routes/
      __init__.py     Empty, marks package
      voice.py        /voice/health, /voice/heartbeat, /voice/intents,
                      /voice/intent, /voice/state, WS /voice/events
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
      wake_word.py    openWakeWord wrapper + cooldown + thread caps
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
  ui/                 Dashboard. Vite + React + TS, static build, nginx-served.
    index.html        Inline bg style prevents a white flash on cold boot
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
  VOICE_SETUP.md      Pi setup, architecture, latency, gotchas, troubleshooting
  UI.md               dashboard stack rationale, theme, touch, Pi perf, kiosk
scripts/
  fetch-voice-models.sh      Downloads ~1.3GB into models/ (gitignored)
models/                      GITIGNORED. Bind-mounted read-only into voice.
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
  payload: 239KB js / 74KB gzip, 18KB css, 89KB fonts
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
  bind_mounted_from_models_dir:   # too large to bake
    - silero_vad.onnx (2MB)
    - qwen2.5-1.5b-instruct-q5_k_m.gguf (1.2GB)
    - en_US-amy-medium.onnx + .onnx.json (60MB)

wake_word: hey_jarvis (openWakeWord bundled)
  custom: set VOICE_WAKE_WORD to a .onnx path in models/; wake_word.py treats
          a value with a path separator or .onnx suffix as a file

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
| `VOICE_INPUT_DEVICE` | no | voice `config.py` | index or name substring; default `0` |
| `VOICE_OUTPUT_DEVICE` | no | voice `config.py` | index or name substring; default `1` |
| `VOICE_API_BASE_URL` | no | voice `api_client.py` | default `http://127.0.0.1:8000` |
| `VOICE_SLM_MODEL` | no | voice `config.py` | default 1.5B Q5; swap for 0.5B Q4 to trade accuracy for speed |
| `VOICE_WAKE_WORD` | no | voice `wake_word.py` | bundled name or `.onnx` path |
| `VOICE_FASTPATH` | no | voice `fastpath.py` | default true; false forces every utterance through the SLM |
| `VOICE_SLM_ENABLED` | no | voice `pipeline.py` | default true; false saves ~1.2GB RSS |
| `VOICE_VERBOSE` | no | voice `config.py` | DEBUG logs with per-stage timings |
| `VOICE_HEARTBEAT_INTERVAL_S` | no | voice `heartbeat.py` | default 15.0; 0 disables |
| `VOICE_STATE_EVENTS` | no | voice `activity.py` | default true; false stops publishing and the pill reads "unknown" |
| `VOICE_STATE_EVENT_TIMEOUT_S` | no | voice `api_client.py` | default 1.0; deliberately shorter than `VOICE_API_TIMEOUT_S` |
| `VOICE_WHISPER_ALLOW_DOWNLOAD` | no | voice `config.py` | default false. True lets Whisper fetch from HuggingFace; see the boot gotcha below |
| `WEATHER_LAT` | no | backend `weather.py` | required for get_weather; without it the intent says so |
| `WEATHER_LON` | no | backend `weather.py` | as above |
| `WEATHER_PLACE` | no | backend `weather.py` | spoken aloud ("12 degrees in Toronto"); empty omits it |
| `WEATHER_UNITS` | no | backend `weather.py` | `celsius` (default) or `fahrenheit` |
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
