# Raspberry Pi 5 — Setup From a Fresh Clone

Everything needed to take a blank Raspberry Pi 5 to a running room panel:
system packages, Docker, the i3 window manager, and Chromium in kiosk mode.

Target: **Raspberry Pi OS Lite (64-bit, Trixie / Debian 13)**. Lite has no
desktop, which is what we want — i3 and Chromium are installed deliberately
rather than inheriting a full desktop environment.

Bookworm (Debian 12) also works; the differences are called out where they
matter.

> Deeper references: [VOICE_SETUP.md](VOICE_SETUP.md) for the audio pipeline,
> [UI.md](UI.md) for the dashboard, [PSU.md](PSU.md) for power supply
> requirements and undervoltage.

---

## 0. What you end up with

Three containers on host networking:

| Service | Port | Purpose |
|---|---|---|
| `backend` | 8000 | FastAPI. Auth, intents, service health |
| `voice` | — | Wake word -> STT -> intent -> TTS. No port; calls the backend |
| `ui` | 8080 | nginx. Serves the dashboard, proxies `/api` with the key |

Chromium opens `http://127.0.0.1:8080` fullscreen under i3.

**Hardware:** Pi 5 (8 GB recommended — the classifier model is ~1.2 GB
resident), a USB microphone, a USB speaker or headset, and the touchscreen.

**Power supply: use the official 27 W USB-C PD supply (5.1 V / 5 A).** This is
not optional padding. A Pi 5 under the load this project creates — four cores
pegged while a 1.2 GB model loads, plus two USB audio devices and a display —
draws well beyond what a typical 5 V / 3 A phone charger delivers. The failure
mode is not a graceful error: the board browns out and cuts power, usually at
the exact moment everything starts at once. With a 3 A supply the firmware also
caps total USB current at 600 mA, which two USB audio devices can exceed on
their own.

If the Pi powers off during `docker compose up`, or USB devices such as touch
input stop responding, suspect the supply before anything else. Details in
[PSU.md](PSU.md).

---

## 1. Flash the OS

Use Raspberry Pi Imager and pick **Raspberry Pi OS Lite (64-bit)**.

In the Imager's settings gear, before writing, set:

- hostname, username and password
- Wi-Fi credentials (or plan to use Ethernet)
- **Enable SSH** — Lite has no desktop, so you will want it

First boot, then:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

Confirm the architecture and release:

```bash
uname -m          # expect: aarch64
cat /etc/os-release | grep VERSION_CODENAME   # trixie (Debian 13) or bookworm
```

**`aarch64` is the one that matters.** Several Python dependencies in the voice
image only ship prebuilt wheels for 64-bit ARM; on a 32-bit install they would
compile from source, or fail.

The Debian release matters much less than you might expect. Everything runs in
containers, which bring their own userland — so the host's Debian version and
system Python are irrelevant to the services. Trixie ships Python 3.13 while
the voice image pins 3.11 (the last release with aarch64 wheels for
`llama-cpp-python`, `ctranslate2` and `onnxruntime`), and that mismatch is
fine and intentional.

The one place the host release does matter is the packages in the next two
sections.

---

## 2. System packages

```bash
sudo apt install -y \
  git curl ca-certificates \
  xserver-xorg xinit x11-xserver-utils \
  i3 \
  xterm \
  unclutter \
  alsa-utils
```

What each is for:

| Package | Why |
|---|---|
| `git curl ca-certificates` | clone the repo, fetch models and the Docker installer |
| `xserver-xorg xinit x11-xserver-utils` | Lite ships no X server; `xset` (for disabling screen blanking) is in x11-xserver-utils |
| `i3` | the window manager |
| `xterm` | a terminal under X. Pi OS Lite has none, and without one the `$mod+Return` escape hatch does nothing — which also removes your only quick way to tell whether i3 is actually running |
| `unclutter` | hides the mouse cursor |
| `alsa-utils` | `arecord` / `aplay`, for testing audio before involving Docker |

### Chromium

The package name has varied across Raspberry Pi OS releases. On Trixie it is
normally `chromium`; older Pi OS shipped `chromium-browser`. Try both:

```bash
sudo apt install -y chromium || sudo apt install -y chromium-browser
```

Then find the binary name, because the i3 config in §8 needs it exactly:

```bash
command -v chromium chromium-browser
```

Whichever path that prints is what goes in the i3 config. Getting this wrong
is the most common reason the panel boots to an empty i3 screen.

---

## 3. Docker

Use Docker's official repository, not the `docker.io` package in Debian, which
lags behind and may not include Compose v2.

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
rm get-docker.sh
```

Docker's repository carries `docker-ce` for Debian 13 (trixie) on `arm64` —
verified against `download.docker.com` — so the installer handles Trixie
without any special steps.

If it ever does report an unsupported release, check what the repo actually
offers before working around it:

```bash
curl -fsI https://download.docker.com/linux/debian/dists/trixie/Release | head -1
```

A `404` would mean the packages were pulled, in which case pointing apt at the
previous stable codename works, since those builds run fine on Debian 13:

```bash
# Only if the trixie repo is genuinely missing.
echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian bookworm stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

Avoid Debian's own `docker.io` package: it lags behind and may not pull in
Compose v2, without which none of the commands in this guide run.

Add yourself to the `docker` group so you are not typing `sudo` for every
command:

```bash
sudo usermod -aG docker "$USER"
```

**Log out and back in** (or reboot) for the group change to apply. Then verify:

```bash
docker run --rm hello-world
docker compose version      # must be v2.x — note the space, not docker-compose
```

`docker compose` (space) is the v2 plugin and is what this repo's commands use.

---

## 3b. Enable memory cgroups

Raspberry Pi OS ships with the kernel's **memory cgroup controller disabled**.
Without it Docker cannot enforce `mem_limit`, and the compose file's memory caps
are silently discarded with:

```
Your kernel does not support memory limit capabilities or the cgroup is not
mounted. Limitation discarded.
```

Those caps exist so a leak in the voice pipeline cannot drag the whole Pi — and
the API with it — down. Turn the controller on:

```bash
sudo nano /boot/firmware/cmdline.txt
```

That file is **one single line**. Append the following to the end of that line,
separated by a space — do not add a newline:

```
cgroup_enable=memory cgroup_memory=1
```

Then reboot and confirm:

```bash
sudo reboot
# after it comes back:
docker info 2>/dev/null | grep -i "limit support"
```

Expect no `WARNING: No memory limit support`. You can also check directly:

```bash
cat /sys/fs/cgroup/cgroup.controllers     # should list: memory
```

Enabling this costs a small amount of kernel memory accounting overhead, which
is the price of the limits working at all.

## 4. Audio

Plug in the microphone and speaker, then:

```bash
arecord -l      # capture devices
aplay   -l      # playback devices
```

You should see your USB devices listed with a card number. If `arecord -l`
reports nothing, the Pi is not seeing the mic and no amount of container
configuration will fix it.

Test capture before involving Docker — it is much easier to debug here.
Address the devices **explicitly** rather than relying on `default`, which is
frequently misconfigured on a Pi (see the ALSA note below):

```bash
arecord -L      # the PCM names you can actually pass to -D
```

From `arecord -l`, note the card number and the name in brackets. For
`card 2: Device [USB PnP Audio Device]` the card name is `Device`, so:

```bash
# Record 3 seconds; speak during them.
arecord -D plughw:CARD=Device,DEV=0 -d 3 -f cd test.wav

# Play it back through the USB speaker (card name from `aplay -l`).
aplay -D plughw:CARD=Device_1,DEV=0 test.wav

rm test.wav
```

Two things that trip people up here:

- **`-D` takes an ALSA PCM name, not a card number.** `-D 2` fails with
  `Unknown PCM 2`. The card-number form is `hw:2,0` or `plughw:2,0`.
- **Use `plughw:`, not `hw:`.** `plughw` inserts automatic rate, format and
  channel conversion. `hw` is raw hardware and will reject `-f cd`
  (44.1 kHz stereo) on a mic that only does, say, 48 kHz mono.

### If `default` is broken

A failure that looks like this means ALSA's `default` device is misconfigured,
not that your microphone is faulty:

```
ALSA lib pcm_asym.c:105:(_snd_pcm_asym_open) capture slave is not defined
arecord: main:850: audio open error: Invalid argument
```

`default` has been declared as an `asym` PCM with a playback half but no
capture half, so anything recording through `default` fails while the hardware
itself is fine — the explicit `plughw:` command above still works.

Find where that definition comes from:

```bash
cat /etc/asound.conf 2>/dev/null
cat ~/.asoundrc 2>/dev/null
ls /usr/share/alsa/alsa.conf.d/ 2>/dev/null
```

To fix it, define both halves. Create `/etc/asound.conf` with your own card
names substituted:

```bash
sudo tee /etc/asound.conf >/dev/null <<'EOF'
pcm.!default {
    type asym
    playback.pcm "plughw:CARD=Device_1,DEV=0"   # USB speaker
    capture.pcm  "plughw:CARD=Device,DEV=0"     # USB microphone
}
ctl.!default {
    type hw
    card Device_1
}
EOF
```

Then re-test plain `arecord -d 3 -f cd test.wav`. Card *names* are used rather
than numbers because numbers shift when devices are replugged.

This is worth fixing even though the containers do not depend on it — see
below — because every ad-hoc debugging command you run on the host will.

### Does a broken host `default` break the containers?

Usually not. The voice container installs its own ALSA userland and the host's
`/etc/asound.conf` and `~/.asoundrc` are **not** mounted into it, so a host
`default` misconfiguration does not propagate. Only `/dev/snd` is shared, which
is the hardware itself.

The pipeline also never opens `default`: it resolves `VOICE_INPUT_DEVICE` and
`VOICE_OUTPUT_DEVICE` to specific devices and opens those by index.

So fix the host config for your own debugging convenience, but do not expect it
to be the cause if the container cannot open the microphone. For that, check
`AUDIO_GID` and the device names instead.

### Audio group id

The voice container runs as a non-root user that must belong to the host's
`audio` group to open `/dev/snd`:

```bash
getent group audio
```

Output looks like `audio:x:29:pi`. **Note the number** — it goes into
`AUDIO_GID` in the next step. It is a *build argument*, so changing it later
requires rebuilding the voice image.

29 is the value Debian reserves for `audio` in `base-passwd`, so it is almost
always correct on Raspberry Pi OS. Check anyway: if the host ever differs, the
container cannot open the microphone and the failure looks like a permission
error rather than a configuration one.

---

## 5. Clone and configure

```bash
git clone <your-repo-url> ~/eevee_assistant
cd ~/eevee_assistant
```

Create the environment file:

```bash
cp infra/docker/.env.example infra/docker/.env
```

Generate a strong key:

```bash
openssl rand -base64 32
```

Edit `infra/docker/.env` and set:

| Variable | Value |
|---|---|
| `API_KEY` | the generated key. Shared by all three containers |
| `AUDIO_GID` | the number from `getent group audio` |
| `VOICE_INPUT_DEVICE` | a substring of your mic's name, e.g. `USB` |
| `VOICE_OUTPUT_DEVICE` | a substring of your speaker's name |

Device **names** beat indexes: indexes get reordered by reboots and replugs,
names do not. You can list devices as the container sees them once it is
running (§7).

Pick a substring that matches exactly one device of that direction. Candidates
are filtered by direction first, so a bare `USB` still resolves correctly when
the mic is capture-only and the speaker is playback-only. It becomes ambiguous
the moment one device does both — a USB headset — and then the pipeline takes
whichever enumerates first.

Being specific costs nothing, so prefer it. For a `USB PnP Audio Device` mic
and a `USB2.0 Device` speaker, use `USB PnP` and `USB2.0`. The pipeline logs a
warning whenever a spec matches more than one device; if you see it, narrow the
substring.

`infra/docker/.env` is gitignored. Never commit it.

---

## 6. Download the models

```bash
./scripts/fetch-voice-models.sh
```

Pulls about 1.3 GB into `models/` at the repo root, bind-mounted read-only into
the voice container:

| File | Size |
|---|---|
| `silero_vad.onnx` | 2 MB |
| `qwen2.5-1.5b-instruct-q5_k_m.gguf` | 1.2 GB |
| `en_US-amy-medium.onnx` + `.json` | 60 MB |

The script skips files that already exist, so it is safe to re-run after an
interrupted download.

openWakeWord and Whisper `tiny.en` are **not** here — they are baked into the
voice image so first boot needs no network.

---

## 7. Build and run

```bash
cd infra/docker
docker compose up --build -d
```

First build takes **10–20 minutes** on a Pi 5, mostly downloading Python wheels
and baking the small models. Later builds are cached.

Check all three are up:

```bash
docker compose ps
docker compose logs -f voice     # Ctrl-C to stop following
```

Verify the stack:

```bash
# from the repo root, with API_KEY exported or pasted inline
curl -H "X-API-Key: $API_KEY" http://127.0.0.1:8000/services

# the dashboard, through nginx (no key needed — nginx adds it)
curl -s http://127.0.0.1:8080/ -o /dev/null -w '%{http_code}\n'
```

`/services` should report `backend` healthy. `voice` shows healthy once the
pipeline has started checking in — it sends a heartbeat every 15s and is marked
down after 45s of silence, so allow a moment after startup while the models
load.

List audio devices as the container sees them, and fix `VOICE_*_DEVICE` in
`.env` if the names do not match:

```bash
docker compose exec voice python -m voice_assistant.devices
```

Then say **"hey jarvis"**, followed by **"is everything ok"**.

---

## 8. Display session and kiosk

Raspberry Pi OS Lite boots to a text console. Something has to start a display
session and put Chromium on screen fullscreen.

**On Trixie there are two paths, and they are not equal:**

| | Option A: labwc (Wayland) | Option B: i3 (X11) |
|---|---|---|
| Status on Trixie | the OS default, officially documented for kiosks | non-default, needs the whole X stack |
| Moving parts | compositor + autostart file | X server, xinit, `.xinitrc`, i3, i3 config |
| Chromium | built and shipped for Wayland on Pi OS | runs via XWayland/X11, less tested here |
| Good for | one fullscreen app | tiling several windows |

**Option A is recommended.** This panel runs exactly one fullscreen browser, so
i3's tiling buys nothing, and labwc is the configuration Raspberry Pi actually
ships and tests. Option B is kept below for anyone who wants i3 anyway.

### 8.1 Console autologin

Needed for both options.

```bash
sudo raspi-config
```

`System Options` → `Boot / Auto Login` → **Console Autologin**. Finish, and
decline the reboot for now.

### 8.2 The kiosk launcher

Used by both options. Keeping the browser in a script rather than inline means
you can run it by hand and read the error instead of staring at a black screen.

```bash
cat > ~/kiosk.sh <<'EOF'
#!/usr/bin/env bash
# Launch the dashboard fullscreen. Run directly to debug.
set -euo pipefail

URL="${KIOSK_URL:-http://127.0.0.1:8080}"

# Trixie ships `chromium`. Older Raspberry Pi OS shipped `chromium-browser`.
# Checking both means this script works on either.
BROWSER="$(command -v chromium || command -v chromium-browser || true)"
if [ -z "$BROWSER" ]; then
  echo "No chromium binary found. Run: sudo apt install -y chromium" >&2
  exit 1
fi

exec "$BROWSER" \
  --kiosk "$URL" \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --no-first-run \
  --check-for-update-interval=31536000 \
  --password-store=basic \
  --use-mock-keychain \
  --autoplay-policy=no-user-gesture-required
EOF
chmod +x ~/kiosk.sh
```

`--password-store=basic` and `--use-mock-keychain` stop Chromium looking for a
keyring that does not exist on Lite — a common cause of it failing to start
with no obvious message.

---

### 8.3 Option A — labwc (recommended)

labwc is a Wayland compositor. No X server, no `.xinitrc`, no `startx`.

```bash
sudo apt install -y labwc chromium
```

Start it automatically on the first console, and only there, so SSH logins are
unaffected:

```bash
cat >> ~/.bash_profile <<'EOF'
# Start the Wayland session on tty1 only.
if [ -z "${WAYLAND_DISPLAY:-}" ] && [ "$(tty)" = "/dev/tty1" ]; then
  exec labwc
fi
EOF
```

Then tell labwc what to launch. The `&` matters — without it labwc waits for
the browser and the session never finishes starting:

```bash
mkdir -p ~/.config/labwc
cat > ~/.config/labwc/autostart <<EOF
$HOME/kiosk.sh &
EOF
```

Note this heredoc is unquoted (`<<EOF`, not `<<'EOF'`), so `$HOME` expands to a
real path when the file is written.

Test without rebooting — from the console on tty1, not over SSH:

```bash
labwc
```

Chromium should come up fullscreen. `Ctrl+Alt+F2` gets you to another console
if you need to escape.

Screen blanking is not an issue here: nothing idles the display unless you
install something like `swayidle`. The cursor is already hidden by the
dashboard's own CSS.

---

### 8.4 Option B — i3 on X11

Only if you specifically want i3.

```bash
sudo apt install -y xserver-xorg xinit x11-xserver-utils i3 xterm unclutter chromium
```

`xterm` is not optional: without a terminal, the `$mod+Return` escape hatch
does nothing, and you lose the quickest way to tell whether i3 is running at
all.

```bash
echo "exec i3" > ~/.xinitrc
chmod +x ~/.xinitrc
```

```bash
cat >> ~/.bash_profile <<'EOF'
# Start X on tty1 only, so SSH sessions are unaffected.
if [ -z "${DISPLAY:-}" ] && [ "$(tty)" = "/dev/tty1" ]; then
  exec startx
fi
EOF
```

The i3 config. **Two rules that are easy to get wrong and fail silently:**
i3 parses this file line by line with **no backslash continuation**, and it
**does not expand `~` or `$HOME`** in an `exec` path.

```bash
mkdir -p ~/.config/i3
cat > ~/.config/i3/config <<EOF
# Minimal i3 for a single-application kiosk.
#
# i3 parses line by line: a command may NOT be split with a trailing
# backslash, which is why the browser lives in kiosk.sh.
# i3 also does not expand ~ or \$HOME, so exec paths are absolute.

set \$mod Mod4
font pango:monospace 8

default_border none
default_floating_border none
hide_edge_borders both

exec --no-startup-id xset s off
exec --no-startup-id xset -dpms
exec --no-startup-id xset s noblank
exec --no-startup-id unclutter -idle 0

exec --no-startup-id $HOME/kiosk.sh

# Escape hatches. A kiosk with no way out means pulling the SD card.
bindsym \$mod+Return exec xterm
bindsym \$mod+Shift+q kill
bindsym \$mod+Shift+e exec i3-msg exit
bindsym \$mod+Shift+r restart
EOF
```

That heredoc is unquoted so `$HOME` expands, with `\$mod` escaped so i3's own
variables survive. Check the result:

```bash
grep exec ~/.config/i3/config      # the kiosk path must be absolute
i3 -C -c ~/.config/i3/config && echo "config OK"
```

`i3 -C` parses the config without starting a session. A config error makes i3
start, show an error bar, and launch nothing — which looks exactly like i3 not
starting.

### 8.5 Reboot

```bash
sudo reboot
```

It should come up straight into the dashboard.

### 8.6 When the screen stays black

**Capture the real error.** This is the single most useful command, because
`Xorg.0.log` records only X server activity and says nothing about a client
that failed to launch:

```bash
startx > ~/startx.log 2>&1
cat ~/startx.log
```

For labwc:

```bash
labwc > ~/labwc.log 2>&1
cat ~/labwc.log
```

`Server terminated successfully` at the end means X started, the client exited
immediately, and X shut down cleanly after it. That is a client problem, not a
display problem — look further up the log for the real error, typically a
"not found".

**Is the browser the problem?** Run it on its own:

```bash
~/kiosk.sh
```

The most common failure on Trixie is the binary name: **`chromium-browser`
does not exist on Trixie, only `chromium`.** Check with:

```bash
command -v chromium chromium-browser
```

**Is i3 running but empty?** An i3 session with no window and no status bar is
a completely black screen, indistinguishable from i3 never starting. Press
`Super+Return`: an xterm means i3 is alive and only the browser exec is broken.
From another console (`Ctrl+Alt+F2`) or SSH:

```bash
pgrep -a i3
pgrep -a X
```

To make a live-but-empty i3 visible while debugging:

```bash
sudo apt install -y i3status
printf '\nbar {\n    status_command i3status\n}\n' >> ~/.config/i3/config
```

Reload with `Super+Shift+r`. Remove it once the panel works.

**Is the dashboard even up?** Chromium on an unreachable URL shows an error
page, not a black screen — so a truly black screen points at the session or the
exec, not the server. Still worth confirming:

```bash
curl -sI http://127.0.0.1:8080 | head -1
```

**Still stuck on X11?** Switch to Option A. On Trixie, X11 is the non-default
path and Chromium is shipped for Wayland; labwc removes the X server,
`.xinitrc` and i3 config from the picture entirely, which is three fewer things
that can fail silently.

## 9. Start on boot

Docker's own restart policies already handle this: `backend` and `ui` are
`restart: always`, `voice` is `restart: unless-stopped`. Provided the Docker
service is enabled — which the official installer does — the containers come
back after a power cut without any extra unit files.

Confirm:

```bash
systemctl is-enabled docker     # expect: enabled
```

`voice` uses `unless-stopped` rather than `always` deliberately: a missing
model file makes it exit non-zero, and `always` would restart-loop it forever.
That also means `docker compose stop voice` stays stopped across reboots while
you debug, which is what you want.

---

## 10. Everyday commands

```bash
cd ~/eevee_assistant/infra/docker

docker compose ps                  # what is running
docker compose logs -f voice       # follow the pipeline
docker compose logs -f backend
docker compose restart voice       # after changing .env
docker compose up -d --build       # after pulling new code
docker compose down                # stop everything
```

Updating:

```bash
cd ~/eevee_assistant
git pull
cd infra/docker && docker compose up -d --build
```

Most `.env` changes only need a `restart`. `AUDIO_GID` is a build argument, so
changing it needs `--build`.

---

## 11. Troubleshooting

### Black screen after startx, no i3

An i3 session with no windows and no status bar is a **completely black
screen** — visually identical to i3 failing to start. Establish which it is
before changing anything.

**Is i3 running?** Press `Super+Return`. If an xterm appears, i3 is fine and
the problem is only that the browser did not launch — skip to the next part.
If nothing happens, check that `xterm` is installed; without it that binding
does nothing even when i3 is healthy. From an SSH session or `Ctrl+Alt+F2`:

```bash
pgrep -a i3
pgrep -a X
```

**If i3 is not running**, read the actual error rather than guessing. Stop the
autologin session first (`Ctrl+Alt+F2`, log in there), then:

```bash
cat ~/.xsession-errors 2>/dev/null | tail -40
startx 2>&1 | tail -40        # run it in the foreground and watch
```

Then work through:

```bash
command -v i3                             # installed at all?
i3 -C -c ~/.config/i3/config              # config parse errors
cat ~/.xinitrc                            # should be exactly: exec i3
chmod +x ~/.xinitrc                       # some xinit builds require this
```

A config parse error is the most common cause. i3 starts, puts up an error
bar, and launches nothing.

**If i3 is running but the dashboard is not**, the browser exec is the problem.
Run the launcher by hand from an xterm (`Super+Return`) and read the error:

```bash
~/kiosk.sh
```

Likely causes, in order:

1. **A multi-line `exec` in the i3 config.** i3 parses line by line and has no
   backslash continuation; a command split across lines is silently broken.
   Keep the browser in `~/kiosk.sh` and exec that in one line.
2. **`~` or `$HOME` in the exec path.** i3 does not expand either. Use the
   full literal path, e.g. `/home/tako/kiosk.sh`.
3. **Wrong binary name.** `chromium` on Trixie, `chromium-browser` on older Pi
   OS. `~/kiosk.sh` handles both; check with
   `command -v chromium chromium-browser`.
4. **The dashboard is not up.** `curl -sI http://127.0.0.1:8080` should return
   a 200. Chromium in `--kiosk` on an unreachable URL shows an error page, not
   a black screen, so a truly black screen points at the exec rather than the
   server.

**Temporarily add a status bar** to make an otherwise-blank i3 obviously alive:

```bash
printf '\nbar {\n    status_command i3status\n}\n' >> ~/.config/i3/config
```

Reload with `Super+Shift+r`. A bar appearing proves i3 is running and shifts
the investigation to the browser. Remove it once the panel works —
`sudo apt install -y i3status` if the bar stays empty.

### The Pi powers off during startup or under load

Nothing in this stack can power a Pi off — there is no shutdown call anywhere.
An out-of-memory condition kills a process, a kernel panic reboots. A hard
power-off is a hardware event, and on a Pi 5 it is nearly always the supply
browning out under a current spike.

Starting all three containers at once is the worst moment: four cores saturate
while a 1.2 GB model is read off the SD card, with USB audio attached.

**First, after it comes back up, check whether the firmware saw undervoltage:**

```bash
vcgencmd get_throttled
```

`throttled=0x0` means no power problem was recorded. Otherwise the bits are:

| Bit | Meaning |
|---|---|
| 0 (`0x1`) | undervoltage **right now** |
| 1 (`0x2`) | ARM frequency capped now |
| 2 (`0x4`) | currently throttled |
| 16 (`0x10000`) | undervoltage **has occurred** since boot |
| 18 (`0x40000`) | throttling has occurred since boot |

Anything with bit 0 or bit 16 set means the supply is inadequate. So
`0x50005` is a board that is browning out.

**Then check what the kernel saw, and whether the previous boot ended cleanly:**

```bash
dmesg | grep -iE "under.?voltage|hwmon"
journalctl --list-boots | tail -3
journalctl -b -1 -e --no-pager | tail -40      # tail of the boot that died
vcgencmd measure_temp                           # throttles ~85C
free -h
```

A previous boot whose log simply stops mid-sentence, with no shutdown messages
and no oops, is the signature of the power being cut. If instead you find
`Out of memory: Killed process`, it is a memory problem, not power — see below.

**Fixes, in order of likelihood:**

1. **Use the official 27 W (5.1 V / 5 A) USB-C PD supply.** A 5 V / 3 A phone
   charger is the single most common cause. Powered USB hubs for the audio
   devices help too, by moving their draw off the Pi's budget.
2. **Stop everything starting simultaneously.** Bring the services up one at a
   time to confirm which one triggers it:
   ```bash
   docker compose up -d backend
   docker compose up -d ui
   docker compose up -d voice      # the heavy one
   ```
3. **Leave a core idle** so the load is less spiky. In `infra/docker/.env`:
   ```
   VOICE_SLM_THREADS=3
   VOICE_WHISPER_THREADS=3
   ```
   This costs some latency and buys headroom. The stages run sequentially, so
   neither model is competing with the other anyway.
4. **Rule out the display and peripherals** by booting headless over SSH with
   the touchscreen unplugged and starting the stack. If it survives that, the
   problem is total draw rather than any one service.

### If it was memory, not power

If the logs show an OOM kill rather than a clean cut, check which:

```bash
journalctl -b -1 | grep -i "out of memory"
free -h
```

On a 4 GB Pi the 1.5 B model is tight next to Chromium. Either switch to the
smaller classifier in `infra/docker/.env`:

```
VOICE_SLM_MODEL=models/qwen2.5-0.5b-instruct-q4_k_m.gguf
```

(fetch it first — it is about 470 MB and roughly 3x faster, at some accuracy
cost), or drop the model entirely with `VOICE_SLM_ENABLED=false` and rely on
the regex fast path.

Make sure memory cgroups are actually enabled (§3b) so the compose `mem_limit`
caps are enforced — without them a runaway container has nothing stopping it
from taking the whole board down.

### Nothing on the screen after boot

Check in order:

```bash
systemctl status docker
docker compose -f ~/eevee_assistant/infra/docker/docker-compose.yml ps
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/
```

If curl returns 200 the stack is fine and the problem is X, i3 or Chromium —
switch to a console with `Ctrl+Alt+F2`, log in and read `~/.xsession-errors`.

### The dashboard says "Backend unreachable"

The UI container is up (it rendered) but cannot reach the API. Check the
backend is running and that both are on host networking:

```bash
docker compose logs backend | tail -30
curl -H "X-API-Key: $API_KEY" http://127.0.0.1:8000/voice/health
```

### The dashboard says "voice is down"

That may be correct. The backend marks voice down after 45s without a
heartbeat. Check the pipeline is alive:

```bash
docker compose logs voice | tail -40
```

`Heartbeat failing` in the log means it is running but cannot reach the API.
Nothing at all usually means it crashed on startup — most often a missing model
file or an audio device it could not open.

### Permission denied on /dev/snd

`AUDIO_GID` does not match the host. Re-check `getent group audio`, fix
`infra/docker/.env`, and rebuild — it is a build argument:

```bash
docker compose up -d --build voice
```

### Wake word never fires, or fires constantly

Never: lower `VOICE_WW_THRESHOLD` toward `0.4`. Confirm the mic actually
captures with `arecord` first.

Constantly: raise it, and check the speaker is not feeding back into the mic.
Increasing `VOICE_POST_TTS_GRACE_MS` helps if it retriggers on its own replies.

### "No input device matching ..."

The device name in `.env` does not match. The error prints the full device
list; copy a substring from it:

```bash
docker compose exec voice python -m voice_assistant.devices
```

### Build runs out of memory or disk

Check space with `df -h`. The images plus models need roughly 4–5 GB. Clear
Docker leftovers:

```bash
docker system prune -a
```

### Debian 13 (Trixie) specifics

**System Python is 3.13.** This does not affect the containers at all — the
voice image pins 3.11 internally. It only matters if you try to run the
pipeline bare metal, outside Docker, which needs a 3.11 interpreter you would
have to supply yourself (pyenv, uv, or a 3.11 container). Use Docker instead.

**`pip install` into the system Python is blocked** by PEP 668, with an
`externally-managed-environment` error. That is correct behaviour, not a fault.
Use a virtualenv if you need host-side Python at all. Nothing in the normal
setup path requires it.

**i3 is X11, not Wayland.** Raspberry Pi OS Desktop defaults to a Wayland
compositor on recent releases, but this guide starts X explicitly via `startx`
on Lite, so i3 runs on X11 as intended. If you later switch to Pi OS Desktop,
i3 will not run under its Wayland session.

### Theme is wrong right after boot

Expected, briefly. The Pi has no real-time clock, so until NTP syncs, the
dashboard cannot trust the hour. In `auto` mode it holds dark and shows
"clock not synced" under the theme switch, then corrects itself within seconds
of the network coming up.

---

## 12. Security note

Everything here assumes a trusted home LAN. The API key protects the backend
from casual access on that network — it is not an authentication system, there
is one static key with no rotation, and nothing is encrypted in transit.

Do not expose port 8000 or 8080 to the internet. If you want the dashboard off
the LAN, put it behind a VPN such as Tailscale or WireGuard rather than
forwarding a port.
