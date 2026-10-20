# Voice Pipeline — Raspberry Pi 5 Setup

Wake word → record → transcribe → classify intent → call the API → speak the reply.
Fully local. No cloud, no API keys beyond the project's own shared secret.

The pipeline runs in its own container, independent of the backend. If the
pipeline dies the API is unaffected; if the API is down the pipeline still
boots and says so out loud.

---

## 1. Hardware

- Raspberry Pi 5. **8 GB recommended.** The 1.5B/Q5 classifier is ~1.2 GB
  resident; with Whisper, Piper and the OS, 4 GB is tight but workable.
- USB microphone. Native sample rate does not matter — 48 kHz is downsampled
  to 16 kHz in software.
- USB speaker or headset for TTS output.
- Raspberry Pi OS Lite (64-bit, Trixie / Debian 13). Bookworm works too.

## 2. Host packages

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git curl
sudo usermod -aG docker "$USER"   # log out and back in
```

Audio libraries are inside the container; the host only needs working ALSA,
which Pi OS Lite has by default.

## 3. Check the microphone on the host

```bash
arecord -l
getent group audio   # note the GID — usually 29
```

If the audio GID is not 29, set `AUDIO_GID` in `infra/docker/.env`. The
container cannot open `/dev/snd` without a matching group.

## 4. Configure

```bash
cp infra/docker/.env.example infra/docker/.env
openssl rand -base64 32   # paste as API_KEY
```

Edit `infra/docker/.env`:
- `API_KEY` — shared secret, used by both containers
- `AUDIO_GID` — from step 3
- `VOICE_INPUT_DEVICE` / `VOICE_OUTPUT_DEVICE` — a substring of the device
  name, not an index. Names survive reboots and replugs; indexes do not. For
  permanently attached hardware, pin the card names first: see "Lock the
  devices in place" in `docs/README_PI.md`.

## 5. Download the models

```bash
./scripts/fetch-voice-models.sh
```

Fetches ~1.3 GB into `models/` at the repo root, bind-mounted read-only into
the container at `/app/models`:

| File | Size | Purpose |
|---|---|---|
| `silero_vad.onnx` | 2 MB | voice activity detection |
| `qwen2.5-1.5b-instruct-q5_k_m.gguf` | 1.2 GB | intent classification |
| `en_US-amy-medium.onnx` + `.json` | 60 MB | Piper TTS voice |

openWakeWord (~50 MB) and Whisper `tiny.en` (~75 MB) are **baked into the
image** instead, so first boot needs no network.

The wake word itself is not downloaded either — it ships in the repo. Install
it into the same directory:

```bash
./scripts/install-wake-model.sh
```

| File | Size | Purpose |
|---|---|---|
| `hey_eevee.onnx` | 44 KB | "hey eevee" wake word |
| `hey_eevee.json` | 2 KB | its threshold + preprocessing constants (**required**) |

See section 13.

## 6. Run

```bash
cd infra/docker
docker compose up --build          # both services
docker compose up -d backend       # API only
docker compose logs -f voice       # follow the pipeline
```

The first build compiles nothing but does download wheels and bake models —
allow 10–15 minutes on a Pi 5.

## 7. Find the audio device indexes

Indexes inside the container differ from the host's:

```bash
docker compose exec voice python -m voice_assistant.devices
```

Prefer a name substring in `VOICE_INPUT_DEVICE` over an index.

## 8. Verify

```bash
# API reachable and authenticated
curl -H "X-API-Key: $API_KEY" http://127.0.0.1:8000/voice/health

# Intent catalogue (the pipeline builds its grammar from this)
curl -H "X-API-Key: $API_KEY" http://127.0.0.1:8000/voice/intents

# Simulate what the pipeline posts after classifying
curl -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
     -X POST -d '{"intent":"system_health","item":null}' \
     http://127.0.0.1:8000/voice/intent

# System health as the dashboard sees it
curl -H "X-API-Key: $API_KEY" http://127.0.0.1:8000/services
```

Then say: **"hey jarvis"** → *"is everything ok"*.

Expected: *"Everything good."* If the voice container has not been running for
45 s, or stops, the answer becomes *"voice is down."* — see §9.1.

---

## 8b. What you can ask

| intent | say | answered from |
|---|---|---|
| `system_health` | "is everything ok" | heartbeat registry |
| `get_time` | "what time is it" | system clock |
| `get_date` | "what's the date", "what day is it" | system clock |
| `greeting` | "hello", "good morning" | time of day + health |
| `repeat_last` | "say that again", "what was that" | last spoken line |
| `set_theme` | "dark mode", "switch to auto" | pushes to the dashboard |
| `show_page` | "go to music", "check systems", "take me back to the dashboard" | pushes to the dashboard |
| `sleep_screen` | "turn the screen off", "good night" | pushes to the dashboard |
| `wake_screen` | "wake up", "screen on" | pushes to the dashboard |
| `get_weather` | "what's the weather", "do I need a jacket" | Open-Meteo |
| `list_capabilities` | "what can you do", "help" | the registry itself |
| `get_uptime` | "how long have you been running" | `/proc/uptime` |
| `cpu_temp` | "how hot is it" | `/sys/class/thermal` |
| `unknown` | anything else | — |

Every one has at least three phrasings and never repeats itself back-to-back.
Four intents take an item: `set_theme` (`dark`/`light`/`auto`), `show_page`
(`dashboard`/`music`/`systems`, and `timers`/`alarms` if you name them),
`set_timer` and `cancel_timer`.

**"check systems" navigates, it does not report.** That phrase belongs to
`show_page` (USER 2026-10-19) because the systems page answers the question by
showing it. Every other health phrasing — "is everything ok", "is anything
down", "check the services" — is still `system_health` and still answers out
loud. Settings has no voice route on purpose.

**Weather needs a location.** Open-Meteo needs no account and no key, but it
does need coordinates — set `WEATHER_LAT`, `WEATHER_LON` and optionally
`WEATHER_PLACE` (spoken aloud) in the backend's environment. Without them the
assistant says it has no location rather than guessing. Readings are cached for
10 minutes, and a failed refresh falls back to the last good one rather than
going mute when the wifi hiccups.

**Uptime and temperature need no mounts.** `/proc/uptime` is the host's inside a
container, and `/sys/class/thermal` is passed through read-only by default.
`cpu_temp` checks the zone's `type` before trusting it, so it reports the SoC
rather than whichever sensor happens to be `thermal_zone0`.

**"Screen off" dims the panel, it does not power the display down.** A browser
cannot do DPMS and the backend has no access to the host's compositor, so the
dashboard paints itself black and stays tappable. Real power-off would need a
helper on the host (`wlopm --off \*` under labwc).

---

## 9. Architecture

```
┌─ voice container ───────────────────────────┐
│  mic 48kHz ──decimate──> 16kHz              │
│      │                                      │
│      ├─> openWakeWord  "hey jarvis"         │  always on, ~12% of one core
│      │                                      │
│      └─> Silero VAD ──> record until silence│
│                 │                           │
│                 v                           │
│          Whisper tiny.en  (0.9-1.3 s)       │
│                 │                           │
│                 v                           │
│          fast path (regex)  ──hit──┐        │  skips the model entirely
│                 │ miss             │        │
│                 v                  │        │
│          Qwen2.5-1.5B-Q5 + GBNF    │        │  4-5 s
│                 │                  │        │
│                 └────> (intent, item) <─────┘
│                            │                │
└────────────────────────────┼────────────────┘
                             │  HTTP + X-API-Key
                             v
┌─ backend container ─────────────────────────┐
│  POST /voice/intent                         │
│    intents.handle() -> speech string        │  response text composed here
└─────────────────────────────────────────────┘
                             │
                             v
                     Piper TTS -> speaker
```

### 9.0 Activity is pushed to the dashboard

Every stage transition above is also POSTed to `/voice/state`, and the backend
fans it out over a WebSocket to the panel, which shows it as a coloured pill:
blue ready, green listening, amber thinking, red speaking. That is how you know
to start talking after the wake word fires, and the answer appears on screen in
large type for 7 seconds.

Two details worth knowing before changing anything here:

- **It is published off the pipeline thread** (`voice_assistant/activity.py`).
  `listening` has to be sent *before* recording begins, so a synchronous POST
  would put an HTTP round trip — and with a dead backend a full connect
  timeout — between the wake word and the microphone opening. Events are
  queued and the queue drops the oldest when full.
- **It is not the heartbeat.** The heartbeat answers "is this alive" on a 45 s
  window; these events answer "what is it doing right now" and have to arrive
  in milliseconds. Measured at 0.8–1.2 ms from POST to the browser.

Set `VOICE_STATE_EVENTS=false` to stop publishing. The pipeline is unaffected;
the pill just reads "unknown".

Drive the dashboard with no audio hardware:

```bash
for s in listening thinking speaking ready; do
  curl -s -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
    -d "{\"state\":\"$s\",\"speech\":\"Everything good.\"}" \
    -X POST http://127.0.0.1:8000/voice/state; sleep 1
done
```

### 9.1 Health is inferred from heartbeats

The voice container POSTs `/voice/heartbeat` every 15 s. The backend marks it
down after 45 s of silence.

```
voice container ──POST /voice/heartbeat every 15s──> backend
                                                       │
                                            records last-seen time
                                                       │
                        ┌──────────────────────────────┴────────────┐
                        v                                            v
           "is everything ok"  ──> system_health              GET /services
                        │                                            │
                        └────────> services.summarize() <────────────┘
                                "Everything good." / "voice is down."
```

**Why heartbeats and not probing.** A crashed or hung service cannot answer a
probe and cannot report its own failure. Silence is the signal. This is the
whole reason the dashboard can show *"voice is down"* — the voice pipeline is
precisely the component that cannot tell you it died.

Details that matter:

- **Never checked in counts as down**, not "unknown". A service that has not
  started is not running; "unknown" would hide a failed boot.
- **Monotonic clock.** A Pi without an RTC can step its wall clock by hours at
  boot. Using wall time would fake an outage.
- **Not persisted.** Heartbeats only mean something relative to now. A
  restarted backend starts from "nobody has checked in yet".
- **The heartbeat starts before the models load.** Loading the 1.5B takes long
  enough that voice would otherwise report down through its entire startup.
- **Single process only.** `uvicorn --workers > 1` would give each worker its
  own registry. Moving to workers means moving this state to Redis.

Keep `SERVICE_STALE_AFTER_S` (backend) a comfortable multiple of
`VOICE_HEARTBEAT_INTERVAL_S` (voice). The 45/15 default tolerates two dropped
beats before flapping.

### Why HTTP and not an in-process call

The requirement is that the API survives a broken pipeline. That means separate
containers, which means separate processes, which leaves HTTP. The two share
the host's loopback via `network_mode: host`, so the call is cheap.

### How the answer is worded

Every spoken word is written in Python, in `apps/backend/intents.py`. The model
classifies and nothing else.

Variation comes from `_pick()`, which chooses between at least three
hand-written phrasings per answer and never picks the same one twice running.
So "what time is it" cycles through *"It is 9:04 pm"*, *"9:04 pm"*, *"Right now
it's 9:04 pm"* — without a second model pass, and without any chance of being
told something that was never looked up.

> A second SLM pass that re-worded answers was built and reverted on
> 2026-10-08: it worked, but the added latency was not worth it. Don't
> re-propose it without latency measured on the Pi.

### Why the backend still composes the canonical sentence

The backend owns the data, so it owns the sentence. The pipeline only decides
*what was asked*. This keeps response wording changeable without touching the
voice container, and keeps a 1.5B model from inventing statuses it never looked
up.

### Why intents are fetched from the API

`GET /voice/intents` is the single source of truth. The pipeline builds its
system prompt **and** its GBNF grammar from the response at startup, so the
classifier can never emit an intent that has no handler. Adding an intent is a
backend-only change plus a voice restart.

If the API is unreachable at boot, a baked-in fallback catalogue is used so the
pipeline still starts and can report the outage.

---

## 10. Latency

Measured on a Pi 5 unless noted.

| Stage | Time |
|---|---|
| Wake word (always on) | ~12% of one core |
| Whisper `tiny.en` int8 | 0.9–1.3 s |
| Fast-path classify | <1 ms |
| Qwen2.5-1.5B-Q5 classify | ~4–5 s (est.) |
| API round trip | <10 ms (loopback) |
| Piper TTS | <0.5 s |
| **End-to-end, fast-path hit** | **~2 s** |
| **End-to-end, SLM fallback** | **~6–7 s** |

The 1.5B/Q5 model was chosen for classification accuracy over latency. The fast
path is what keeps common commands usable: a regex hit skips the model
completely. Expect most everyday phrasings to be fast-path hits and only
unusual wording to pay the model cost.

Levers if you want the latency back:
- `VOICE_SLM_MODEL=models/qwen2.5-0.5b-instruct-q4_k_m.gguf` — ~3x faster,
  less accurate, ~470 MB
- Add patterns to `apps/voice/voice_assistant/fastpath.py` for phrasings you
  actually use. Check the logs for `Classified by SLM` lines; each one is a
  missing fast-path rule.
- `VOICE_SLM_ENABLED=false` — drop the model entirely, ~1.2 GB RSS back,
  unmatched utterances become "unknown"

---

## 11. Gotchas

Carried over from the prototype, all learned the hard way:

1. **Python 3.11, not 3.13.** `llama-cpp-python`, `ctranslate2` and
   `onnxruntime` have no aarch64 wheels for 3.13. The voice image pins 3.11.

   This is independent of the host. Raspberry Pi OS Trixie ships Python 3.13,
   and that is fine — the container brings its own userland, so the host's
   Debian release and interpreter never come into it. The pin only constrains
   a bare-metal run, which would need its own 3.11 from pyenv or uv.

2. **Silero VAD v5 needs 64 samples of context** from the previous chunk
   prepended to each 512-sample chunk. Without it scores never exceed ~0.03
   even on clear speech. The ONNX schema does not show this — input shape is
   `[None, None]`. See `vad.py`.

3. **NumPy slices are views.** `chunk[::3]` shares memory with sounddevice's
   input buffer, which is reused between reads, so a view can be overwritten
   mid-inference. `downsample_mic()` returns a contiguous copy.

4. **GBNF rejects `\-` in a character class** and llama.cpp *segfaults* rather
   than reporting the error. `-` must be last: `[a-zA-Z0-9 _-]`. The grammar is
   built at runtime in `slm.py`; if you touch that builder, check this first —
   a segfault is all the feedback you get.

5. **Whisper must never be allowed to phone home.** The weights are baked into
   the image, but faster-whisper will still call HuggingFace to *revalidate* a
   complete cache unless `local_files_only=True`. On a Pi that has just
   rebooted the connection gets made and then dropped, and the resulting
   `RemoteProtocolError` is not one of the exceptions huggingface_hub falls
   back to the cache on — so the container dies at startup with a stack trace
   that looks like a network problem. `VOICE_WHISPER_ALLOW_DOWNLOAD=false` is
   the default for this reason. A *refused* port is handled gracefully, which
   is why this only ever appears on a real boot.

6. **Whisper hallucinates on silence** — 8 s of room noise becomes "this." or
   "thank you." STT is skipped entirely unless the recorder's VAD saw speech.

7. **Never let the model compose responses.** A small model states inventory
   and statuses it never looked up. It returns structured data only.

8. **USB mics usually refuse 16 kHz** via PortAudio. Capture at 48 kHz and
   decimate by 3. Naive decimation is fine for speech-band content.

9. **`/dev/snd` needs a matching group.** The container runs as a non-root
   user in group `AUDIO_GID`. Wrong GID means a permission error on the mic.

10. **`docker compose exec voice` device indexes differ from the host's.** Match
    by name instead.

11. **Verify a dependency pin before committing it.** `piper-onnx` was pinned
    `~=0.1` on the assumption it followed a 0.x line; it never published one,
    so the pin resolved to nothing and the failure only surfaced minutes into
    a Pi build. Check against the real index and the real target platform:

    ```bash
    pip download --only-binary :all: --python-version 311 \
      --platform manylinux2014_aarch64 --platform manylinux_2_28_aarch64 \
      --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu \
      -r apps/voice/requirements.txt -d /tmp/resolve-check
    ```

    Passing several `--platform` flags matters: wheels carry different
    manylinux tags (numpy 1.26 is `manylinux2014`, onnxruntime is
    `manylinux_2_28`), and a single tag wrongly rejects half of them. The full
    set currently resolves to 63 wheels with no source builds.

---

## 12. Troubleshooting

| Symptom | Cause |
|---|---|
| `Missing file: .../qwen2.5-...gguf` | `scripts/fetch-voice-models.sh` not run, or `models/` not mounted |
| `No input device matching ...` | Run `python -m voice_assistant.devices` and fix `VOICE_INPUT_DEVICE`; the error prints the full device list |
| Permission error on the mic | `AUDIO_GID` does not match `getent group audio`; rebuild after changing it (it is a build arg) |
| `Backend rejected API_KEY (401)` | `API_KEY` differs between the containers, or is unset |
| `I can't reach the backend` | API is down, or `VOICE_API_BASE_URL` is wrong. Both services need `network_mode: host` to share loopback |
| Says `voice is down` while voice is clearly running | Heartbeats are not landing. Check `docker compose logs voice` for `Heartbeat failing`, and that `SERVICE_STALE_AFTER_S` > `VOICE_HEARTBEAT_INTERVAL_S` |
| Health flaps between good and down | Stale window too close to the send interval. Keep the 3x ratio |
| Wake word never fires | Lower `VOICE_WW_THRESHOLD` to ~0.4; check mic peak amplitude with `arecord` |
| Wake word fires constantly | Raise `VOICE_WW_THRESHOLD`; check the speaker is not feeding back into the mic, and raise `VOICE_POST_TTS_GRACE_MS` |
| Recordings cut off early | Raise `VOICE_SILENCE_TIMEOUT_MS` |
| `input overflow` warnings | The Pi is falling behind the mic. Check for another CPU hog |
| Everything is slow | Check logs for `Classified by SLM` — add fast-path rules, or switch to the 0.5B model |

---

## 13. The wake word

The default is **`hey_jarvis`**, an openWakeWord model baked into the image.
It needs no files in `models/` and no configuration.

**It was "hey eevee" between 2026-10-15 and 2026-10-16.** That model is a
`heed` export and it works, but on this Pi it fired on non-speech room noise
even with the threshold raised to 0.9, so the default went back (USER
DECISION). To try it again:

```bash
./scripts/install-wake-model.sh          # copies both files into models/
# then in infra/docker/.env:
#   VOICE_WAKE_WORD=models/hey_eevee.onnx
cd infra/docker && docker compose restart voice
```

That copies `wake.onnx` -> `models/hey_eevee.onnx` and `wake.json` ->
`models/hey_eevee.json`. No image rebuild: `models/` is a bind mount.

**If you switch back, clear `VOICE_WW_THRESHOLD`.** A threshold tuned for one
model means nothing to the other: 0.9 is a sensible tightening for the heed
model and leaves `hey_jarvis` effectively deaf.

**Both files are required.** The `.json` is not documentation -- it carries the
calibrated threshold (0.603), the mel parameters, the filter cut-offs and the
trigger/energy-gate constants that `wake_heed.py` reads at startup. The model
without its sidecar refuses to load.

`wake.int8.onnx` is also in the export. It is half the size but *slower* on the
Pi 5: INT8 pays off on an NPU, and quantize/dequantize overhead is a net loss
on an A76 CPU. Install it only to compare (`WAKE_VARIANT=int8
./scripts/install-wake-model.sh`).

### Why it is not loaded through openWakeWord

openWakeWord models consume the output of openWakeWord's own
melspectrogram+embedding frontend. A heed export consumes log-mel features
directly -- input `mel`, shape `(1, 40, 101)` -- so the two formats are not
interchangeable and pointing `VOICE_WAKE_WORD` at a heed `.onnx` under the old
code would have failed to load.

`wake_word.make_detector()` therefore picks the engine by looking for the
sidecar: a `.onnx` with a matching `.json` beside it goes to
`wake_heed.HeedWakeWordDetector`, anything else to the openWakeWord wrapper.
Both are driven identically by the pipeline, so switching costs one env var:

| `VOICE_WAKE_WORD` | Engine |
|---|---|
| `models/hey_eevee.onnx` (+ `.json`) | heed — the default |
| `hey_jarvis` | openWakeWord, bundled in the image |
| `models/my_word.onnx` (no `.json`) | openWakeWord, custom export |

### Preprocessing, and the one risk in it

`wake_heed.py` reimplements the chain `wake.json` mandates, in order:
causal high-pass (100 Hz, 8th-order Butterworth) plus 50/60 Hz mains notches
with biquad state retained across frames; peak normalise to -3 dBFS; log-mel
(40 bins, 400-sample Hann window in a 512-point FFT, hop 160, centred and
reflect-padded, giving exactly the 101 frames the graph expects); then CMN.
**Skipping CMN makes the model wildly inaccurate**, which is the trap worth
knowing about if this is ever ported.

Four conventions are *not* pinned down by the sidecar: the mel scale, the
filterbank normalisation, the log base and the notch Q. The defaults here are
what torchaudio does (HTK mel, unnormalised triangles, natural log) because the
export is a torch 2.11 graph, and they produce the documented tensor shape and
near-zero scores on noise, tones and silence. They are not proof of a match on
a *positive* clip. Confirm that with a recording of the phrase:

```bash
docker compose exec voice python -m voice_assistant.wake_check /app/clip.wav
```

It prints the peak probability against the threshold. If a clip the trainer
scored high comes back low, flip one convention at a time in
`infra/docker/.env` — `VOICE_WW_MEL_SCALE=slaney`, `VOICE_WW_MEL_NORM=slaney`,
`VOICE_WW_LOG_BASE=10` — and re-run.

### Tuning

- `VOICE_WW_THRESHOLD` overrides the sidecar's 0.603. Leave it unset to use
  the calibrated value; raise it if the word fires on other speech, lower it if
  it misses. **On the real Pi 2026-10-16 the calibrated value fired on
  non-speech room noise**, and `VOICE_WW_THRESHOLD=0.9` settled it. No rebuild
  is needed — it is read from `infra/docker/.env` at startup:

  ```bash
  docker compose up -d --force-recreate voice
  ```

  If 0.9 starts missing real "hey eevee"s, 0.8 is the middle ground. If it
  still fires on noise at 0.9, the next lever is `consecutive_frames` in
  `models/hey_eevee.json` (2 -> 3): that demands the word hold up across
  240 ms instead of 160 ms, which room noise rarely does, at the cost of
  about 80 ms of latency. Turning the mic's capture gain down in
  `alsamixer -c eeveemic` attacks the same problem at the source — a hot mic
  is what pushes noise past the energy gate in the first place.
- The trigger needs 2 consecutive frames over threshold and then suppresses for
  0.7 s. Both come from `wake.json`, not from the environment.
- The energy gate (RMS below -55 dBFS, or under 15 % of energy in 100–7000 Hz)
  skips the model entirely, so a quiet room costs one FFT per 80 ms instead of
  an inference. It is measured on unfiltered audio, deliberately: the high-pass
  has already removed the rumble that would prove the energy is not speech.

Cost on the model itself is ~0.26 ms per 80 ms frame on a desktop CPU, so this
stays far inside the always-on budget on a Pi 5.
