"""
Audio spectrum of whatever the PC is playing, live on one or more CH582M
LED badges (44x11 each) over USB HID. Windows only (WASAPI loopback).

One column per frequency band, log-spaced, bass on the left. With several
badges plugged in they stack into taller bars: 2 badges = 22 rows.

Every setting lives in CONFIG below; each one can also be overridden
on the command line, e.g.

    python audio_viz.py                        # defaults
    python audio_viz.py --fps 30 --fall 40     # faster, bars drop quicker
    python audio_viz.py --fmin 30 --fmax 8000  # more room for bass and mids
    python audio_viz.py --range 40 --peaks     # punchier, with falling peak dots
    python audio_viz.py --device Speakers      # capture another output (part of its name)
    python audio_viz.py --identify / --order 2,1 / --badges 1

Ctrl+C (or --seconds running out) stops it and hands the badges back to
their normal animations.

Requires: pip install hidapi numpy soundcard pillow
"""
import argparse
import time
import warnings

import numpy as np
import soundcard as sc
from PIL import Image, ImageDraw

from badge_ng import HidBadge, COLS, ROWS, fb_bytes

CONFIG = {
    "fps": 55,              # frames per second; each frame records 1/fps s of audio
    "fmin": 40,             # lowest band in Hz (left column)
    "fmax": 16000,          # highest band in Hz (right column)
    "fft": 4096,            # FFT window in samples (~85 ms at 48 kHz)
    "range": 50,            # dB shown from the top of the bars down to empty
    "fall": 200,            # rows per second a bar sinks when the sound drops
    "peaks": False,         # falling peak dot above each bar
    "device": None,         # output to capture (part of its name); None = default
    "badges": 0,            # how many to use; 0 = every connected badge
    "order": None,          # e.g. "2,1" to swap; numbers as shown by --identify
    "seconds": 0,           # stop after this long; 0 = run until Ctrl+C
    "brightness": None,     # 0-3, or None to leave the badges as they are
    "preview": False,       # also print each frame to the terminal
    "identify": False,      # show each badge's number for 3 s, then quit
}

RATE = 48000


def open_badges(cfg):
    paths = HidBadge.paths()
    if not paths:
        raise SystemExit("no badge found -- plugged in?")
    if cfg["order"]:
        paths = [paths[int(n) - 1] for n in cfg["order"].split(",")]
    if cfg["badges"]:
        paths = paths[:cfg["badges"]]
    return [HidBadge(path=p) for p in paths]


def open_loopback(name):
    spk = sc.default_speaker() if name is None else next(
        (s for s in sc.all_speakers() if name.lower() in s.name.lower()), None)
    if spk is None:
        raise SystemExit("no output matching %r; outputs: %s"
                         % (name, ", ".join(s.name for s in sc.all_speakers())))
    # By id, not name: a headset's mic can have exactly the same name as its
    # output, and the name lookup then opens the mic. On Bluetooth that also
    # drops the headset into its low-quality hands-free profile.
    mic = sc.get_microphone(spk.id, include_loopback=True)
    if not mic.isloopback:
        raise SystemExit("%r is not a loopback device; not recording from a microphone" % mic.name)
    print("capturing what plays on", spk.name)
    return mic


def band_edges(cfg):
    """FFT bin ranges for COLS log-spaced bands; every band gets >= 1 bin."""
    hz = np.geomspace(cfg["fmin"], cfg["fmax"], COLS + 1)
    bins = np.round(hz * cfg["fft"] / RATE).astype(int)
    lo = bins[:-1]
    hi = np.maximum(bins[1:], lo + 1)
    return lo, hi


def to_columns(heights, top, rows):
    """Bar heights (rows, from the bottom of the whole canvas) -> 44 column
    ints for the badge whose first row is `top`."""
    cols = []
    for h in heights:
        c = 0
        for r in range(ROWS):
            if rows - (top + r) <= h:  # this row counted from the bottom
                c |= 1 << r
        cols.append(c)
    return cols


def show_in_terminal(heights, peaks, rows):
    lines = []
    for y in range(rows):
        if y and y % ROWS == 0:
            lines.append("-" * COLS)  # seam between badges
        level = rows - y
        lines.append("".join("#" if h >= level else "o" if p is not None and int(p) == level else "."
                             for h, p in zip(heights, peaks)))
    print("\033[H" + "\n".join(lines), flush=True)


def identify(badges):
    for i, b in enumerate(badges, 1):
        img = Image.new("1", (COLS, ROWS), 0)
        ImageDraw.Draw(img).text((2, 0), "BADGE %d" % i, fill=1)
        px = img.load()
        b.push(fb_bytes([sum(1 << r for r in range(ROWS) if px[c, r]) for c in range(COLS)]))
    time.sleep(3)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--fps", type=float)
    p.add_argument("--fmin", type=float)
    p.add_argument("--fmax", type=float)
    p.add_argument("--fft", type=int)
    p.add_argument("--range", type=float, help="dB from full bar to empty")
    p.add_argument("--fall", type=float, help="rows per second a bar sinks")
    p.add_argument("--peaks", action="store_true", default=None)
    p.add_argument("--device", help="part of the output's name")
    p.add_argument("--badges", type=int, help="how many badges, 0 = all")
    p.add_argument("--order", help='top-to-bottom order, e.g. "2,1"')
    p.add_argument("--seconds", type=float, help="stop after this long")
    p.add_argument("--brightness", type=int, choices=range(4))
    p.add_argument("--preview", action="store_true", default=None)
    p.add_argument("--identify", action="store_true", default=None)
    cfg = dict(CONFIG)
    cfg.update({k: v for k, v in vars(p.parse_args()).items() if v is not None})
    return cfg


def main():
    cfg = parse_args()
    badges = open_badges(cfg)
    rows = ROWS * len(badges)
    for b in badges:
        if cfg["brightness"] is not None:
            b.brightness(cfg["brightness"])
        b.stream_on()
    time.sleep(0.3)

    try:
        if cfg["identify"]:
            identify(badges)
            return

        mic = open_loopback(cfg["device"])
        lo, hi = band_edges(cfg)
        window = np.hanning(cfg["fft"])
        buf = np.zeros(cfg["fft"])
        step = int(RATE / cfg["fps"])
        shown = np.zeros(COLS)            # bar heights as displayed, in rows
        peak = np.zeros(COLS)
        ref = -40.0                       # loudest band lately, in dB (auto gain)
        fall = cfg["fall"] / cfg["fps"]
        print("%d badge(s), %d rows, %g fps, Ctrl+C to stop" % (len(badges), rows, cfg["fps"]))
        if cfg["preview"]:
            print("\033[2J", end="")

        end = time.time() + cfg["seconds"] if cfg["seconds"] else None
        # soundcard warns about "data discontinuity" whenever nothing plays
        with warnings.catch_warnings(), mic.recorder(samplerate=RATE, blocksize=step) as rec:
            warnings.simplefilter("ignore")
            while end is None or time.time() < end:
                new = rec.record(numframes=step).mean(axis=1)  # paces the loop
                buf = np.concatenate((buf, new))[-cfg["fft"]:]

                mag = np.abs(np.fft.rfft(buf * window))
                bands = np.array([mag[a:b].max() for a, b in zip(lo, hi)])
                db = 20 * np.log10(bands + 1e-9)
                # follow the loudest band: up at once, down by 6 dB per second
                ref = max(db.max(), ref - 6 / cfg["fps"], -80)
                target = np.clip((db - (ref - cfg["range"])) / cfg["range"], 0, 1) * rows

                shown = np.maximum(target, shown - fall)
                peak = np.maximum(shown, peak - fall / 3)
                heights = np.round(shown).astype(int)
                peaks = [int(round(p)) if cfg["peaks"] and round(p) > h else None
                         for p, h in zip(peak, heights)]

                for i, b in enumerate(badges):
                    cols = to_columns(heights, i * ROWS, rows)
                    if cfg["peaks"]:
                        for c, p in enumerate(peaks):
                            if p is None:
                                continue
                            r = rows - p - i * ROWS  # peak row inside this badge
                            if 0 <= r < ROWS:
                                cols[c] |= 1 << r
                    b.push(fb_bytes(cols))
                if cfg["preview"]:
                    show_in_terminal(heights, peaks, rows)
    except KeyboardInterrupt:
        pass
    finally:
        for b in badges:
            b.stream_off()
            b.close()
        print("\nstopped; badges back to normal mode")


if __name__ == "__main__":
    main()
