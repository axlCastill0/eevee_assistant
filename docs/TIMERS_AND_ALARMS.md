# Timers and alarms

**Timers** and **Alarms** are two apps, opened from the tiles on the
**Dashboard** — the panel's home screen, which is a launcher. Timers can also
be set by voice; alarms are screen-only, by design.

---

## 1. Put some sounds where the Pi can find them

Both features play a file you choose. They live in `media/` at the repo root,
which is bind-mounted read-only into the backend at `/app/media`:

```bash
mkdir -p ~/eevee_assistant/media
scp ~/Music/wake-up.mp3 tako@<pi-address>:~/eevee_assistant/media/
```

`.mp3`, `.wav`, `.ogg`, `.m4a` and `.flac` are all accepted. They appear in the
Settings page's dropdowns **immediately** — the directory is read per request,
so there is no rebuild and no restart. The folder is gitignored: these are
whole songs, personal, and nothing to do with the code.

Then open **Settings** and pick one for `timer_sound`, one for `alarm_sound`
and one for `training_sound`. Until you do, a timer still fires and still
shows its banner — it just does so silently, which the banner says.

**`training_sound` wants a very short file** — a beep, 100–300ms. It is the
interval timer's cue and plays four times per phase (at the start and at 3, 2
and 1 seconds remaining), so anything with a tail will still be sounding when
the next cue lands. Drop it in the same folder as the rest:

```bash
scp ~/Sounds/beep.wav tako@<pi-address>:~/eevee_assistant/media/
```

---

## 2. Let Chromium play audio without a tap

A kiosk browser will refuse to autoplay audio unless it is told not to. Add
the flag to the Chromium line in `~/kiosk.sh`:

```
--autoplay-policy=no-user-gesture-required
```

so it reads something like:

```bash
exec "$BROWSER" --kiosk --noerrdialogs --disable-infobars \
     --autoplay-policy=no-user-gesture-required \
     "$URL"
```

Restart the session to pick it up:

```bash
sudo systemctl restart getty@tty1
```

**Without the flag nothing is lost silently**: the banner appears, says "tap to
play the sound", and a tap starts it. The flag just removes the tap.

---

## 3. Timers

### From the screen

**Drag the dial.** It has two rings:

- the **outer** ring is minutes — one full turn is 60 of them, so a quarter
  turn is fifteen. Keep turning past the top and it keeps counting up, to a
  12-hour ceiling.
- the **inner** ring is seconds — one full turn is 60, and it carries into
  the minutes when it passes the top.

Which ring you get is decided by where your finger lands, once, when you
touch down — so a sloppy circle never switches you from minutes to seconds
halfway round. The ring you are turning brightens; the other dims.

The presets (30s, 1, 3, 5, 10, 15, 30, 45) **arm** the dial rather than
starting straight away — so a mis-tap is not a timer you then have to cancel,
and "10 minutes, actually 12" is a tap and a nudge. **Start** is always in the
same place.

Several can run at once; each gets a card with its countdown, a progress ring,
and the wall-clock time it ends at.

**Pause** holds a timer where it is — the ring greys, the card dims, it drops
below anything still counting, and it will not fire until you press play
again. A ringing timer has no pause; the only thing to do with one is clear
it.

### By voice

| Say | Does |
|---|---|
| "set a timer for ten minutes" | starts one |
| "set a 5 minute timer" | same |
| "timer for an hour and a half" | same |
| "remind me in 15 minutes" | same |
| "cancel the timer" | cancels it, if exactly one is running |
| "stop the 10 minute timer" | cancels that one |
| "how much time is left" | reads the remaining time back |

All of those hit the regex fast path, so they answer in about a second rather
than paying the ~4 s the SLM costs. Anything phrased differently still works —
it just goes through the model.

Durations are parsed on the **backend** (`timers.parse_duration`), which also
handles "half an hour", "ninety seconds" and a bare "set a timer for ten"
(ten minutes — what it means in every kitchen).

**New intents need the voice container restarted**, because it fetches the
intent catalogue once at startup:

```bash
cd infra/docker && docker compose restart voice
```

### What a timer does when it ends

The card turns and says `done`, a banner slides up from the bottom of
whatever page you are on, and the timer sound plays once. It stops when you
press **Stop** or when the song finishes — nothing else ends it. An ignored
timer is not a dealt-with timer.

Timers are deliberately **not persisted**. A countdown only means anything
relative to now, so a backend restart forgets them rather than resurrecting
one that should have gone off two minutes ago.

---

## 4. Alarms

Seven slots, Monday to Sunday, each with a time and a switch.

The **week strip** across the top is both the navigation and the overview:
every day shows its time, and a filled dot means it is armed. Tap a day to
edit it below.

The time is set with **wheels** — flick the hour, the minutes (every minute,
0–59) and AM/PM. The big switch arms the day.

There is no seconds wheel, deliberately: an alarm fires within a two-minute
window of its time, so a seconds value would not be honoured. Timers are the
control that goes to the second.

**Copy this time to** `Mon–Fri`, `Sat–Sun` or `All 7` writes the selected
day's time across that group *and turns those days on*, which is the fast way
out of setting the same alarm five times.

Everything saves as you tap — there is no save button to forget.

Alarms **are** persisted, to `state/alarms.json`. A schedule is still true
after a reboot.

An alarm rings when its minute arrives, plays the alarm sound once, and stops
on **Stop** or when the song ends. It fires at most once per day: stopping it
records the date, which is also what stops a backend restart at 7:31 from
re-ringing an alarm already dealt with. If the Pi is off at 7:30 and boots at
7:45, that alarm does not fire — it is 15 minutes late and you already know
what time it is.

There is no voice control for alarms (USER DECISION 2026-10-16): setting a
recurring weekly commitment from a transcript is where a misheard word costs
the most, and the screen is right there.

---

## 4b. Fingers training

A third app behind the launcher, at `#/training`. A fixed hangboard session:

| | |
|---|---|
| Sections | **4 finger half crimp**, **three fingers**, **two fingers** |
| Each section | 6 rounds of 10s work and 20s rest |
| Total | 9:00, ending on the sixth rest |

It makes a sound at every phase start and at 3, 2 and 1 seconds remaining —
`training_sound` in Settings — plus one when the session finishes. The only
controls are in the container's top right: pause/resume, restart, and stop.

Two things that are different from Timers and Alarms, both on purpose:

- **It runs in the browser, not the backend.** This is a session you stand in
  front of: it needs cue accuracy the backend's 1Hz polling cannot give, and
  it is meaningless if you walk away. The schedule is absolute — every phase
  and every cue is an offset from one start instant — so a late tick never
  accumulates drift.
- **Leaving the page ends the session.** There is no server-side state behind
  it, so switching to another view stops it. Pause is the control for
  stepping away.

Nothing about the session is configurable, because nothing was asked to be:
the shape of it is the point. `WORK_S`, `REST_S`, `REPS` and `SECTIONS` at the
top of `apps/ui/src/views/Training.tsx` are the only source of truth — change
one and the plan, the cues, the round pips and the clock all follow.

---

## 5. The top bar

Two static icons, and no countdowns:

| Icon | Means |
|---|---|
| stopwatch | at least one timer is running (with a count when there are several) |
| bell | an alarm is set to go off within 24 hours |

They are status, not buttons. A ticking number up there would pull the eye
every second on every page, and the Dashboard already answers "how long".

The theme control used to live here and moved to **Settings** to make the
room.

---

## 6. How it fits together

```
 Dashboard / Settings / top bar
        ▲
        │  GET /api/clock/state   (polled 1x/sec by the app SHELL)
        │  POST/DELETE /api/clock/timers...
        │  PUT /api/clock/alarms/<weekday>
        │  GET /api/clock/sounds/<file>
        │
   nginx (adds X-API-Key)
        ▲
   backend: timers.py (memory) · alarms.py (state/) · settings.py (state/ + media/)
        ▲
        │  POST /voice/intent
   voice pipeline — fastpath or SLM → set_timer / cancel_timer / timer_status
```

Two decisions worth knowing:

- **The poll lives in the app shell, not in the Dashboard view.** An alarm has
  to ring whatever page is on screen; if the Dashboard owned the poll, an
  alarm set for 7am would be silent whenever the panel was left on Music.
- **Audio plays in the browser, not the backend.** The voice container owns
  the speaker through ALSA and its loop is single-threaded, so a three-minute
  song played there would deafen the wake word for its whole duration.
  Chromium mixes alongside it instead.

---

## 7. Troubleshooting

### The banner appears but nothing plays

Either no sound is chosen in Settings (the banner says so), or Chromium
blocked autoplay (the banner says "tap to play the sound" — add the flag from
section 2).

### The Settings dropdowns are empty

The backend cannot see the media folder. It should be `media/` at the repo
root on the Pi:

```bash
ls ~/eevee_assistant/media
docker compose exec backend ls /app/media
```

If the second is empty, the container predates the volume — recreate it:

```bash
docker compose up -d --force-recreate backend
```

### An alarm went off at the wrong time (hours out)

The backend container is on a different timezone from the host. Alarms are
wall-clock by design, so they follow the container's local clock:

```bash
date                                 # on the Pi
docker compose exec backend date     # must match
```

`/etc/localtime` is mounted into the container to keep these in step. If they
disagree, recreate the container — a restart does not pick up a new mount:

```bash
docker compose up -d --force-recreate backend
```

See "The clock is hours out" in `README_PI.md` for the host side.

### An alarm did not go off

Check it is enabled, and that the Pi was awake. Then:

```bash
docker compose logs backend | grep -i alarm
```

`Alarm ringing:` means the backend fired it, which points at the browser or
the sound file; no line at all means it never came due.

### Voice says it does not know how to set a timer

The voice container is running an older intent catalogue. Restart it:

```bash
docker compose restart voice
```

### Alarms reset on every restart

`state/` is not writable. The backend logs `Could not persist alarms`. Check
the `../../state:/app/state` volume is present and the directory exists.
