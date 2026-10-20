#!/usr/bin/env python3
"""Rebuild the two self-subset woff2 faces in src/fonts/.

Lexend comes from npm (@fontsource-variable/lexend) and needs nothing here.
These two do:

  mono    JetBrains Mono variable, upstream release rather than the Google
          subset, because the Google latin subset drops U+2500 box drawing
          and the whole UI is built out of box characters.
  symbols Symbols Nerd Font, subset to the ~140 glyphs listed below. The full
          face is 2.4 MB for 3500 glyphs nothing references.

Usage: python3 scripts/fonts.py <JetBrainsMono[wght].ttf> <SymbolsNerdFontMono-Regular.ttf>
  JetBrains Mono: github.com/JetBrains/JetBrainsMono/releases (fonts/variable/)
  Symbols:        github.com/ryanoasis/nerd-fonts/releases (NerdFontsSymbolsOnly.zip)
Needs: pip install fonttools brotli
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

OUT = Path(__file__).resolve().parent.parent / "src" / "fonts"

# Latin, punctuation, arrows, box drawing, block elements, geometric shapes.
# Everything the terminal chrome draws with. JetBrains Mono has no braille.
MONO_RANGES = (
    "U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,"
    "U+2000-206F,U+20AC,U+2122,U+2190-21FF,U+2212,U+2215,U+2248,U+2260,"
    "U+25A0-25FF,U+2500-259F"
)

# Nerd glyphs by upstream glyph name -> the key used in the UI's icon map.
# Codicons wherever one exists: one designer, one grid, one stroke weight.
SYMBOLS: dict[str, str] = {
    # navigation
    "cod-dashboard": "dashboard",
    "cod-music": "music",
    "cod-server": "server",
    "cod-settings_gear": "settings",
    "cod-terminal": "terminal",
    "cod-terminal_bash": "shell",
    "cod-bracket_dot": "bracket",
    # time
    "cod-watch": "timer",
    "fa-stopwatch": "stopwatch",
    "fa-hourglass": "hourglass",
    "oct-clock": "clock",
    "cod-history": "uptime",
    "cod-calendar": "calendar",
    # alarms
    "cod-bell": "bell",
    "cod-bell_dot": "bell_active",
    "cod-bell_slash": "bell_off",
    # voice
    "cod-mic": "mic",
    "cod-mic_filled": "mic_live",
    "cod-unmute": "speaking",
    "cod-mute": "muted",
    # screen + power
    "fa-power_off": "power",
    "cod-screen_full": "screen",
    "fa-desktop": "display",
    "oct-device_desktop": "pc",
    # machine
    "cod-pulse": "pulse",
    "cod-chip": "cpu",
    "fa-microchip": "soc",
    "fa-memory": "memory",
    "fa-hdd_o": "disk",
    "cod-database": "database",
    "cod-vm": "container",
    "cod-vm_running": "container_up",
    "cod-flame": "load",
    "fa-thermometer_half": "temp",
    "fa-wifi": "wifi",
    "fa-signal": "signal",
    # state
    "cod-check": "ok",
    "cod-check_all": "all_ok",
    "cod-close": "close",
    "cod-warning": "warn",
    "cod-circle_small_filled": "dot",
    "cod-circle_small": "dot_hollow",
    "cod-graph_line": "graph",
    # controls
    "cod-chevron_up": "up",
    "cod-chevron_down": "down",
    "cod-chevron_left": "left",
    "cod-chevron_right": "right",
    "cod-triangle_right": "caret_right",
    "cod-triangle_down": "caret_down",
    "cod-add": "add",
    "cod-dash": "remove",
    "cod-trash": "trash",
    "cod-edit": "edit",
    "cod-refresh": "refresh",
    "cod-sync": "sync",
    "cod-debug_start": "start",
    "cod-debug_stop": "halt",
    "cod-ellipsis": "more",
    "cod-list_unordered": "list",
    "cod-tasklist": "tasks",
    "cod-lock": "lock",
    "cod-arrow_right": "arrow_right",
    "cod-arrow_left": "arrow_left",
    # playback
    "cod-play": "play",
    "cod-debug_pause": "pause",
    "fa-step_forward": "next",
    "fa-step_backward": "prev",
    "fa-stop": "stop_square",
    "fa-volume_up": "volume",
    "fa-volume_off": "volume_off",
    # weather, matching lib/useWeather.ts icon keys x day/night
    "weather-day_sunny": "clear_day",
    "oct-moon": "clear_night",
    "weather-day_cloudy": "partly_day",
    "weather-night_alt_cloudy": "partly_night",
    "weather-cloudy": "cloud",
    "weather-day_fog": "fog_day",
    "weather-night_fog": "fog_night",
    "weather-raindrops": "drizzle",
    "weather-day_rain": "rain_day",
    "weather-night_alt_rain": "rain_night",
    "weather-day_snow": "snow_day",
    "weather-night_alt_snow": "snow_night",
    "weather-day_thunderstorm": "storm_day",
    "weather-night_alt_thunderstorm": "storm_night",
    "weather-strong_wind": "wind",
    "weather-thermometer": "thermometer",
    "weather-sunrise": "sunrise",
    "weather-sunset": "sunset",
    # powerline, for the segment chrome
    "pl-left_hard_divider": "pl_left",
    "pl-right_hard_divider": "pl_right",
    "ple-lower_right_triangle": "pl_corner",
    "ple-upper_left_triangle": "pl_corner_alt",
}


def subset(src: Path, dest: Path, unicodes: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "fontTools.subset", str(src),
         f"--unicodes={unicodes.replace('U+', '')}",
         "--flavor=woff2", "--no-hinting", f"--output-file={dest}",
         "--layout-features=kern,liga,calt,tnum"],
        check=True,
    )
    print(f"{dest.name}: {dest.stat().st_size // 1024} KB")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    mono_src, sym_src = Path(sys.argv[1]), Path(sys.argv[2])
    OUT.mkdir(parents=True, exist_ok=True)

    subset(mono_src, OUT / "jetbrains-mono.woff2", MONO_RANGES)

    # Resolve the nerd glyphs by NAME. Hand-written codepoints in the
    # thousands-range PUA are unverifiable by eye, and a wrong one is a blank
    # box on the panel rather than an error anywhere.
    cmap = TTFont(sym_src).getBestCmap()
    by_name = {}
    for code, name in cmap.items():
        by_name.setdefault(name, code)

    picked: dict[str, int] = {}
    for name, key in SYMBOLS.items():
        code = by_name.get(name)
        if code is None:
            print(f"MISSING in source font: {name}", file=sys.stderr)
            return 1
        picked[key] = code

    subset(sym_src, OUT / "symbols-nerd.woff2",
           ",".join(f"U+{c:04X}" for c in picked.values()))

    ts = OUT / "glyphs.ts"
    body = ",\n".join(
        f"  {k}: '\\u{{{c:X}}}'" for k, c in sorted(picked.items())
    )
    ts.write_text(
        "// Generated by scripts/fonts.py. Keys are defined in SYMBOLS there.\n"
        "export const GLYPH = {\n" + body + ",\n} as const\n\n"
        "export type GlyphName = keyof typeof GLYPH\n"
    )
    print(f"glyphs.ts: {len(picked)} glyphs")
    print(json.dumps({"glyphs": len(picked)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
