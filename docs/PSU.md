# Powering the Pi 5

Short version: **use the official 27 W USB-C supply (5.1 V / 5 A).** Anything
less and the Pi caps USB peripherals at 600 mA, which this build will exceed.

---

## Why 5 A specifically

The USB current budget depends on what the supply advertises:

| Supply | Total current for USB peripherals |
|---|---|
| 5 V / 5 A (25 W) | **1.6 A** |
| Anything else, including 5 V / 3 A | **600 mA** |

This is a firmware decision, not a fuse. A 3 A supply gets 600 mA whether or
not it could physically deliver more.

**That 600 mA is the likely cause of touch cutting out.** On this panel the USB
budget is shared by the touchscreen's touch interface, the USB microphone and
the USB speaker. Three devices on a 600 mA ceiling is tight, and when it is
exceeded devices drop off the bus one at a time rather than failing loudly —
which looks exactly like "touch worked for a bit and then stopped".

## What to buy

- **Raspberry Pi 27 W USB-C Power Supply** (SC1153 white / SC1152 black). It
  has a captive cable, so there is no cable to get wrong.
- A third-party supply must advertise **5 V / 5 A** over USB-PD — not just
  "27 W". Many 27 W chargers only offer 5 V/3 A plus higher-voltage profiles
  the Pi cannot use, and those land you back on 600 mA.
- With a third-party supply you also need a USB-C cable rated for 5 A. Thin or
  long cables cause voltage drop; the official docs name thin wires as a direct
  cause of undervoltage, storage corruption and erratic behaviour.

## Sharing the wall outlet with the screen

Sharing a socket or power strip is fine. Each device draws independently; a
normal strip is nowhere near its limit with a Pi and a 10" display.

Two things to avoid:

- **Do not power the Pi from the screen's USB port.** Monitor USB ports supply
  500 mA–1 A, far below the Pi 5's requirement, and the Pi will brown out under
  load. Official guidance also warns against back-powering the Pi through a
  hub, since it bypasses the board's protection circuitry.
- **Do not power the screen from the Pi.** A display drawing from the Pi's USB
  eats the same 600 mA / 1.6 A budget your input devices need.

Give the Pi and the screen their own adapters into the shared strip.

If the touchscreen's touch interface is USB and plugs into the Pi — which is
normal for HDMI + USB-touch panels — that draw counts against the Pi's USB
budget. It cannot be avoided, only budgeted for.

## Checking for a power problem

```bash
vcgencmd get_throttled
```

`throttled=0x0` is clean. Otherwise:

| Bit | Hex | Meaning |
|---|---|---|
| 0 | `0x1` | undervoltage **right now** |
| 1 | `0x2` | ARM frequency capped now |
| 2 | `0x4` | throttled now |
| 3 | `0x8` | soft temperature limit now |
| 16 | `0x10000` | undervoltage **has occurred** since boot |
| 17 | `0x20000` | frequency capping has occurred |
| 18 | `0x40000` | throttling has occurred |
| 19 | `0x80000` | soft temperature limit has occurred |

Bits 0–3 are now; bits 16–19 are history. So `0x50000` means it happened
earlier and has recovered, `0x50005` means it is happening right now.

The Pi 5 flags undervoltage when the supply drops below roughly **4.63 V**.

Also useful:

```bash
dmesg | grep -iE "under.?voltage|over.?current|usb .*disconnect"
vcgencmd get_config usb_max_current_enable    # 1 = higher USB limit allowed
```

If touch disappears, check `dmesg` immediately — a USB disconnect line at the
moment it stopped confirms the current limit rather than a driver fault.

## If you are stuck on a 3 A supply

Two options, in order of preference:

1. **A powered USB hub.** Move the microphone, speaker and touch input onto a
   hub with its own adapter. This takes them off the Pi's budget entirely and
   is the correct fix for a permanent installation, official supply or not.

2. **`usb_max_current_enable=1`** in `/boot/firmware/config.txt` lifts the cap
   to 1.6 A. Understand what this does: it **raises the limit, it does not add
   power.** If the supply cannot deliver, you trade clean USB dropouts for
   brownouts and hard power-offs — which is worse, because an SD card being
   written during a brownout can be corrupted. Only use this with a supply you
   know has headroom.

## Related

- Power-off and undervoltage troubleshooting: [README_PI.md](README_PI.md) §11
- `mem_limit` needs memory cgroups enabled: [README_PI.md](README_PI.md) §3b

Sources: [Raspberry Pi power supply documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#power-supply),
[power-supplies.adoc](https://github.com/raspberrypi/documentation/blob/master/documentation/asciidoc/computers/raspberry-pi/power-supplies.adoc),
[USB PD on Raspberry Pi 5 (whitepaper)](https://pip-assets.raspberrypi.com/categories/685-app-notes-guides-whitepapers/documents/RP-009856-WP-1-USB%20Power%20delivery%20on%20Raspberry%20Pi%205.pdf)
