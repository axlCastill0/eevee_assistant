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
  name, not an index. Names survive reboots and replugs; indexes do not.

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

Logic tests, no hardware or models needed:

```bash
python -m pytest apps/voice/tests -q
```

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

### Why the backend composes the speech

The backend owns the data, so it owns the sentence. The pipeline only decides
*what was asked*. This also keeps the response wording changeable without
touching the voice container, and keeps a 1.5B model from inventing statuses it
never looked up.

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
   than reporting the error. `-` must be last: `[a-zA-Z0-9 _-]`. Guarded by
   `tests/test_grammar.py`.

5. **Whisper hallucinates on silence** — 8 s of room noise becomes "this." or
   "thank you." STT is skipped entirely unless the recorder's VAD saw speech.

6. **Never let the model compose responses.** A small model states inventory
   and statuses it never looked up. It returns structured data only.

7. **USB mics usually refuse 16 kHz** via PortAudio. Capture at 48 kHz and
   decimate by 3. Naive decimation is fine for speech-band content.

8. **`/dev/snd` needs a matching group.** The container runs as a non-root
   user in group `AUDIO_GID`. Wrong GID means a permission error on the mic.

9. **`docker compose exec voice` device indexes differ from the host's.** Match
   by name instead.

10. **Verify a dependency pin before committing it.** `piper-onnx` was pinned
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

## 13. Changing the wake word

`hey_jarvis` is an openWakeWord bundled model. To use a custom-trained one:

1. Train with openWakeWord's notebook; you get a `.onnx` file.
2. Drop it in `models/`.
3. Set `VOICE_WAKE_WORD=models/my_word.onnx` in `infra/docker/.env`.
4. `docker compose restart voice`.

`wake_word.py` treats a value containing a path separator or ending in `.onnx`
as a file and checks it exists; anything else is treated as a bundled name.
