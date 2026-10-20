"""
Mirror the screen to one or more CH582M LED badges (44x11 each) over USB HID.

With several badges plugged in, they are stacked on top of each other and
act as one taller screen: 2 badges = 44x22, 3 = 44x33, ...

Every setting lives in CONFIG below; each one can also be overridden
on the command line, e.g.

    python screen_mirror.py                          # defaults, all badges
    python screen_mirror.py --identify               # show which badge is which
    python screen_mirror.py --order 2,1              # swap top and bottom
    python screen_mirror.py --badges 1               # only the first badge
    python screen_mirror.py --region mouse --zoom 400
    python screen_mirror.py --threshold auto --invert --fps 30 --seconds 10
    python screen_mirror.py --dither --preview

Ctrl+C (or --seconds running out) stops it and hands the badges back to
their normal animations.

Requires: pip install hidapi Pillow
"""
import argparse
import ctypes
import ctypes.wintypes
import time

from PIL import Image, ImageDraw, ImageGrab, ImageOps

from badge_ng import HidBadge, COLS, ROWS, fb_bytes

CONFIG = {
    # which badges, top to bottom
    "badges": 0,            # how many to use; 0 = every connected badge
    "order": None,          # e.g. "2,1" to swap; numbers as shown by --identify

    # what to capture:
    #   "screen"   primary monitor
    #   "all"      every monitor as one big image
    #   "mouse"    a window centred on the cursor, `zoom` px wide,
    #              same aspect ratio as the badge canvas
    #   "x,y,w,h"  a fixed rectangle in screen pixels
    "region": "screen",
    "zoom": 440,            # width of the "mouse" window in screen pixels

    # how to squeeze it onto the canvas:
    #   "stretch"  fill the canvas, distort the aspect ratio
    #   "crop"     keep aspect, cut off the excess (centre crop)
    #   "fit"      keep aspect, black bars
    "fit": "stretch",

    # turning grey into on/off LEDs
    "threshold": "auto",    # 0-255, or "auto" = average brightness of the frame
    "dither": False,        # Floyd-Steinberg instead of a hard threshold
    "invert": False,        # light-on-dark <-> dark-on-light
    "contrast": True,       # stretch the histogram before thresholding

    "fps": 20,              # frames per second (the badge itself manages ~60+)
    "seconds": 0,           # stop after this long; 0 = run until Ctrl+C
    "brightness": None,     # 0-3, or None to leave the badges as they are
    "preview": False,       # also print each frame to the terminal
    "identify": False,      # show each badge's number for 3 s, then quit
}


def open_badges(cfg):
    paths = HidBadge.paths()
    if not paths:
        raise SystemExit("no badge found -- plugged in?")
    if cfg["order"]:
        paths = [paths[int(n) - 1] for n in cfg["order"].split(",")]
    if cfg["badges"]:
        paths = paths[:cfg["badges"]]
    return [HidBadge(path=p) for p in paths]


def cursor_pos():
    pt = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def grab(cfg, size):
    region = cfg["region"]
    if region == "screen":
        return ImageGrab.grab()
    if region == "all":
        return ImageGrab.grab(all_screens=True)
    if region == "mouse":
        w = cfg["zoom"]
        h = max(1, w * size[1] // size[0])
        x, y = cursor_pos()
        return ImageGrab.grab(bbox=(x - w // 2, y - h // 2, x + w // 2, y + h // 2),
                              all_screens=True)
    x, y, w, h = (int(v) for v in region.split(","))
    return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)


def to_canvas(img, cfg, size):
    """Screen image -> 1-bit image of the whole canvas."""
    img = img.convert("L")
    if cfg["fit"] == "crop":
        img = ImageOps.fit(img, size, Image.BOX)
    elif cfg["fit"] == "fit":
        img = ImageOps.pad(img, size, Image.BOX, color=0)
    else:
        img = img.resize(size, Image.BOX)

    if cfg["contrast"]:
        img = ImageOps.autocontrast(img)
    if cfg["invert"]:
        img = ImageOps.invert(img)

    if cfg["dither"]:
        return img.convert("1")     # Floyd-Steinberg is PIL's default
    t = cfg["threshold"]
    if t == "auto":
        hist = img.histogram()
        t = sum(i * n for i, n in enumerate(hist)) / max(1, sum(hist))
    t = int(t)
    return img.point(lambda p: 255 if p > t else 0, "1")


def to_columns(img, top=0):
    """The 44x11 strip starting at row `top` -> 44 column ints for one badge."""
    px = img.load()
    return [sum(1 << r for r in range(ROWS) if px[c, top + r]) for c in range(COLS)]


def show_in_terminal(img):
    px = img.load()
    w, h = img.size
    lines = []
    for y in range(h):
        if y and y % ROWS == 0:
            lines.append("-" * w)     # seam between badges
        lines.append("".join("#" if px[x, y] else "." for x in range(w)))
    print("\033[H" + "\n".join(lines), flush=True)


def identify(badges):
    for i, b in enumerate(badges, 1):
        img = Image.new("1", (COLS, ROWS), 0)
        ImageDraw.Draw(img).text((2, 0), "BADGE %d" % i, fill=1)
        b.push(fb_bytes(to_columns(img)))
    time.sleep(3)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--badges", type=int, help="how many badges, 0 = all")
    p.add_argument("--order", help='top-to-bottom order, e.g. "2,1"')
    p.add_argument("--region", help='screen | all | mouse | "x,y,w,h"')
    p.add_argument("--zoom", type=int, help="mouse window width in px")
    p.add_argument("--fit", choices=["stretch", "crop", "fit"])
    p.add_argument("--threshold", help='0-255 or "auto"')
    p.add_argument("--dither", action="store_true", default=None)
    p.add_argument("--invert", action="store_true", default=None)
    p.add_argument("--no-contrast", dest="contrast", action="store_false", default=None)
    p.add_argument("--fps", type=float)
    p.add_argument("--seconds", type=float, help="stop after this long")
    p.add_argument("--brightness", type=int, choices=range(4))
    p.add_argument("--preview", action="store_true", default=None)
    p.add_argument("--identify", action="store_true", default=None)
    cfg = dict(CONFIG)
    cfg.update({k: v for k, v in vars(p.parse_args()).items() if v is not None})
    if cfg["threshold"] != "auto":
        cfg["threshold"] = int(cfg["threshold"])
    return cfg


def main():
    cfg = parse_args()
    # without this, ImageGrab and GetCursorPos disagree on scaled displays
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

    badges = open_badges(cfg)
    size = (COLS, ROWS * len(badges))
    for b in badges:
        if cfg["brightness"] is not None:
            b.brightness(cfg["brightness"])
        b.stream_on()
    time.sleep(0.3)

    try:
        if cfg["identify"]:
            identify(badges)
            return
        print("mirroring to %d badge(s), %dx%d at %g fps, Ctrl+C to stop"
              % (len(badges), size[0], size[1], cfg["fps"]))
        if cfg["preview"]:
            print("\033[2J", end="")

        delay = 1.0 / cfg["fps"]
        end = time.perf_counter() + cfg["seconds"] if cfg["seconds"] else None
        while end is None or time.perf_counter() < end:
            t0 = time.perf_counter()
            canvas = to_canvas(grab(cfg, size), cfg, size)
            for i, b in enumerate(badges):
                b.push(fb_bytes(to_columns(canvas, top=i * ROWS)))
            if cfg["preview"]:
                show_in_terminal(canvas)
            time.sleep(max(0, delay - (time.perf_counter() - t0)))
    except KeyboardInterrupt:
        pass
    finally:
        for b in badges:
            b.stream_off()
            b.close()
        print("\nstopped; badges back to normal mode")


if __name__ == "__main__":
    main()
