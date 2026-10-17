"""Upload a static 11-row image to the old LS32 badge (stock firmware, USB HID).

Usage:
    python ls32_image.py                 # built-in test pattern
    python ls32_image.py picture.png     # any image; scaled to 11 px high, thresholded
    python ls32_image.py pic.png --invert --brightness 0

The stock protocol has no live framebuffer: this writes message slot 0 to flash
in "fixed" mode (4). Images narrower than 44 px are centred; wider ones scroll.
"""
import argparse
import sys
import time

import hid
from PIL import Image, ImageDraw

VID, PID = 0x0416, 0x5020
ROWS, COLS = 11, 44


def test_pattern():
    img = Image.new("1", (COLS, ROWS), 0)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, COLS - 1, ROWS - 1], outline=1)          # full border
    d.line([(4, 5), (30, 5)], fill=1)                          # arrow shaft
    d.polygon([(31, 1), (39, 5), (31, 9)], fill=1)              # arrow head -> right
    d.point([(2, 2), (2, 8)], fill=1)                          # corner markers, left side only
    return img


def load_image(path, invert):
    img = Image.open(path).convert("L")
    if img.height != ROWS:
        w = max(1, round(img.width * ROWS / img.height))
        img = img.resize((w, ROWS), Image.LANCZOS)
    img = img.point(lambda p: 255 if (p < 128) == invert else 0).convert("1")
    return img


def to_columns_bytes(img):
    """11 bytes per 8-pixel-wide column group, MSB = leftmost pixel."""
    w = img.width
    if w < COLS:                       # centre on the 44-px display
        canvas = Image.new("1", (COLS, ROWS), 0)
        canvas.paste(img, ((COLS - w) // 2, 0))
        img, w = canvas, COLS
    groups = (w + 7) // 8
    px = img.load()
    out = bytearray()
    for g in range(groups):
        for r in range(ROWS):
            b = 0
            for bit in range(8):
                x = g * 8 + bit
                if x < w and px[x, r]:
                    b |= 0x80 >> bit
            out.append(b)
    return out, groups


def build_packet(data, groups, mode=4, speed=4, brightness=0):
    hdr = bytearray(64)
    hdr[0:4] = b"wang"
    hdr[5] = {0: 0x00, 1: 0x10, 2: 0x20, 3: 0x40}[brightness]  # 0 = brightest
    for i in range(8):
        hdr[8 + i] = (speed << 4) | mode if i == 0 else 0x40
    hdr[16] = groups >> 8
    hdr[17] = groups & 0xFF
    t = time.localtime()
    hdr[38:44] = bytes([t.tm_year % 100, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec])
    pkt = hdr + data
    pkt += bytes(-len(pkt) % 64)
    return pkt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", nargs="?")
    ap.add_argument("--invert", action="store_true", help="light pixels become LEDs on")
    ap.add_argument("--brightness", type=int, default=0, choices=range(4), help="0 = brightest")
    ap.add_argument("--preview", action="store_true", help="print ASCII preview, don't upload")
    a = ap.parse_args()

    img = load_image(a.image, a.invert) if a.image else test_pattern()
    data, groups = to_columns_bytes(img)

    w = groups * 8
    for r in range(ROWS):
        print("".join("#" if data[(x // 8) * ROWS + r] & (0x80 >> (x % 8)) else "." for x in range(w)))
    if a.preview:
        return

    devs = hid.enumerate(VID, PID)
    devs = [d for d in devs if d["product_string"] == "LS32 Custm HID"]
    if not devs:
        sys.exit("LS32 badge not found (plug in only the old badge)")
    pkt = build_packet(data, groups, brightness=a.brightness)

    dev = hid.device()
    dev.open_path(devs[0]["path"])
    t0 = time.perf_counter()
    for i in range(0, len(pkt), 64):
        dev.write(b"\x00" + pkt[i:i + 64])
    dt = time.perf_counter() - t0
    dev.close()
    print(f"sent {len(pkt)} bytes ({len(pkt)//64} reports) in {dt*1000:.0f} ms")


if __name__ == "__main__":
    main()
