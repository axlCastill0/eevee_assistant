# AGENT_CONTEXT

Machine-oriented state file for coding agents. Read fully before any change.
UPDATE THIS FILE IN THE SAME COMMIT AS ANY CHANGE IT DESCRIBES. See `## update_protocol`.

```yaml
meta:
  project: eevee_assistant
  root: /Users/tako/root/eevee_assistant
  last_updated: 2026-10-04
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
    intents.py        INTENT REGISTRY - single source of truth; handlers
    services.py       SERVICE HEALTH - heartbeat registry + summarize()
    conftest.py       Puts apps/backend on sys.path for pytest
    routes/
      __init__.py     Empty, marks package
      voice.py        /voice/health, /voice/heartbeat, /voice/intents, /voice/intent
      status.py       GET /services - the dashboard's data source
    tests/
      test_services.py   13 tests: heartbeat staleness, phrasing, monotonic clock
    requirements.txt
    .env.example
  voice/              Voice pipeline. Separate container, separate lifecycle.
    run.py            Entrypoint; loads .env BEFORE importing config
    conftest.py       Puts apps/voice on sys.path for pytest
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
      api_client.py   httpx client; failure-tolerant, never raises upward
      heartbeat.py    Daemon thread posting /voice/heartbeat every 15s
      tts.py          Piper TTS + output resampling
      pipeline.py     Main loop wiring every stage
      devices.py      `python -m voice_assistant.devices` audio device lister
    tests/
      test_fastpath.py   44 tests total, no models/hardware needed
      test_grammar.py
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
        useTheme.ts   light/dark/auto, boundary timer, RTC guard
        useClock.ts   second-aligned tick (plain intervals drift)
        format.ts     durations, clock, labels
      components/
        TopBar/ThemeToggle/PollRing      header, 3-state toggle, poll sweep
        Overview                         hero; reuses backend's speech string
        ServiceTile/Sparkline/StatusDot  per-service tile
        DetailSheet                      drag-to-dismiss bottom sheet
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

`/services` is unprefixed because it is system-wide, not scoped to a
subsystem. It is the dashboard's data source and must work when voice is down.

`POST /voice/intent` body: `{intent, item?, transcript?}`. Unknown intent names
are downgraded to `"unknown"` rather than rejected — the classifier is not
trusted to be correct. `item` is forced to null for intents with
`needs_item: false`.

## voice pipeline

```yaml
flow: wake_word -> record(VAD) -> STT -> fastpath|SLM -> HTTP -> TTS

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
  2. add a handler branch in intents.handle()
  3. add a row to `## routes` only if a new endpoint was added
  4. restart the voice container (it refetches on boot)
  5. optionally add fastpath.py rules once the real phrasings are known
  NOTHING in apps/voice/ needs to change for a new intent.

current_intents: [system_health, get_time, unknown]

system_health:
  scope: ALL services at once. There is deliberately NO per-service intent -
         "is the voice pipeline up" is still system_health with item null.
  speech: "Everything good." when all healthy, else the down services named
          ("voice is down." / "a and b are down." / "a, b, and c are down.")
  composed_by: services.summarize()
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
  user: non-root `voice`, supplementary group AUDIO_GID
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

## verified

```yaml
date: 2026-10-04
environment: macOS dev host, python 3.13 venv, no Pi hardware

passed:
  - "pytest apps/voice/tests -q    -> 55 passed"
      covers: fastpath hits/misses/pruning/filler, GBNF dash-last regression
  - "pytest apps/backend/tests -q  -> 13 passed"
      covers: never-seen=down, stale transition, recovery, 1/2/3-service
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

NOT verified - no hardware available:
  - any audio path: mic capture, wake word, VAD, Whisper, Piper, playback
  - the SLM: model not downloaded, llama-cpp-python not installed
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
  - no UI tests (the logic worth testing is useTheme's boundary/RTC handling
    and format.ts; neither needs a DOM)
  - no backend route tests (services.py is covered; the routes are not)
  - no CI
  - heartbeat history is not persisted, so the trail resets on reload. Real
    uptime history needs server-side storage.
  - no MQTT / status bus (see `## mqtt` below)
  - voice has no barge-in: it cannot be interrupted mid-response
  - single static API key; no rotation, no per-client keys, no rate limiting
  - backend port 8000 and python version hardcoded, not env-driven
```

## mqtt

```yaml
status: NOT IMPLEMENTED, and deliberately deferred as of 2026-10-04
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
  - sub-second or push-driven UI updates are needed
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
on_test_or_manual_verify:  [## verified]
on_new_intent:             [## intent system, apps/backend/intents.py only]
on_voice_pipeline_change:  [## voice pipeline]
on_finishing_backlog_item: [## backlog (remove it), ## verified]
on_discovering_a_defect:   [## backlog, or an OPEN ISSUE block in the owning section]

rules:
  - append to `## decisions`; do not delete or edit past rows
  - keep this file factual. no prose, no narration, no persuasion
  - state absolute dates, never "recently" or "last week"
  - distinguish VERIFIED from ESTIMATED. Never promote an estimate to a
    measurement without running it
  - if a section would become wrong, fix it rather than leaving it stale
  - if you hit something surprising that cost you time, record it so the next
    agent does not repeat it
```
