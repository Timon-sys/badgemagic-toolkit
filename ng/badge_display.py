"""
Minimal HID display driver for the CH582M LED badge (44x11)
running the patched FOSSASIA badgemagic firmware.

    from badge_display import BadgeDisplay, text_image

    with BadgeDisplay() as badge:          # init() + streaming on
        badge.push(text_image("HI"))      # push a PIL image
                                           # deinit() on exit

Wire format (the 'ng' protocol, USB variant):

    'N' 'G' len_lo len_hi  payload[len]

Payload is a command byte plus its arguments. Frames are split across
64-byte HID OUT reports and reassembled by the firmware. Anything not
starting with 'NG' falls through to the legacy "wang" parser, so normal
badgemagic.exe uploads keep working.

Framebuffer: 44 little-endian uint16, one per column, bit r = row r.

Requires: pip install hidapi Pillow
"""
import struct
import time

from PIL import Image, ImageDraw, ImageFont

VID, PID = 0x0416, 0x5020
WIDTH, HEIGHT = 44, 11

# ng command bytes
CMD_POWER, CMD_STREAM_SET, CMD_STREAM_BM = 1, 2, 3
CMD_BLE, CMD_SPLASH, CMD_SAVE, CMD_FALLBACK, CMD_MISC = 4, 5, 6, 7, 8

HID_REPORT = 64          # fixed OUT report size
REPORT_ID = bytes([0])   # device uses no report IDs, so 0


class BadgeError(RuntimeError):
    pass


class BadgeDisplay:
    """A 44x11 1-bit display you push PIL images to.

    init() opens the HID device and puts the badge into streaming mode,
    which stops its own animations and hands the framebuffer to us.
    deinit() gives it back. Usable as a context manager.
    """

    def __init__(self, vid=VID, pid=PID):
        self.vid, self.pid = vid, pid
        self._dev = None

    # --- lifecycle ---------------------------------------------------

    def init(self):
        import hid
        infos = [d for d in hid.enumerate(self.vid, self.pid)
                 if d["interface_number"] == 0]
        if not infos:
            raise BadgeError(
                "badge not found (%04x:%04x interface 0) -- plugged in?"
                % (self.vid, self.pid))
        self._dev = hid.device()
        self._dev.open_path(infos[0]["path"])
        self._cmd(CMD_STREAM_SET, 0x00)   # enter streaming mode
        time.sleep(0.2)                   # let it stop its animations
        return self

    def deinit(self):
        if self._dev is None:
            return
        try:
            self._cmd(CMD_STREAM_SET, 0x01)   # back to normal mode
            time.sleep(0.1)
        finally:
            self._dev.close()
            self._dev = None

    def __enter__(self):
        return self.init()

    def __exit__(self, *exc):
        self.deinit()
        return False

    # --- drawing -----------------------------------------------------

    def push(self, img, x=0, y=0, threshold=128):
        """Blit a PIL image to the display and show it immediately.

        Anything outside 44x11 is cropped. Grayscale/RGB is thresholded;
        mode "1" images are used as-is.
        """
        self.push_columns(self.image_to_columns(img, x, y, threshold))

    def push_columns(self, cols):
        """cols: 44 ints, bit r = row r (row 0 is the top)."""
        if len(cols) != WIDTH:
            raise ValueError("expected %d columns, got %d" % (WIDTH, len(cols)))
        fb = b"".join(struct.pack("<H", c & 0x7FF) for c in cols)
        self._cmd(CMD_STREAM_BM, *fb)

    def clear(self):
        self.push_columns([0] * WIDTH)

    # --- a few config commands, handy to have ------------------------

    def brightness(self, level):
        """0-3. Persist with save_config()."""
        if not 0 <= level <= 3:
            raise ValueError("brightness is 0-3")
        self._cmd(CMD_MISC, 0x01, level)

    def save_config(self):
        self._cmd(CMD_SAVE)

    def reboot(self):
        self._cmd(CMD_POWER, 2)
        self._dev = None      # it will drop off USB for ~15s

    # --- helpers ------------------------------------------------------

    @staticmethod
    def image_to_columns(img, x=0, y=0, threshold=128):
        if img.mode != "1":
            img = img.convert("L").point(lambda p: 255 if p >= threshold else 0, "1")
        px = img.load()
        w, h = img.size
        cols = [0] * WIDTH
        for cx in range(WIDTH):
            sx = cx - x
            if not 0 <= sx < w:
                continue
            for cy in range(HEIGHT):
                sy = cy - y
                if 0 <= sy < h and px[sx, sy]:
                    cols[cx] |= 1 << cy
        return cols

    # --- wire ---------------------------------------------------------

    def _cmd(self, *payload):
        if self._dev is None:
            raise BadgeError("not open -- call init() first")
        body = bytes(payload)
        frame = b"NG" + struct.pack("<H", len(body)) + body
        for i in range(0, len(frame), HID_REPORT):
            chunk = frame[i:i + HID_REPORT]
            self._dev.write(REPORT_ID + chunk + bytes(HID_REPORT - len(chunk)))


# --- PIL text helpers ---------------------------------------------------

def _font(size):
    try:
        return ImageFont.load_default(size)      # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()

def text_image(text, size=11, pad=0):
    """Render text to a 1-bit image exactly HEIGHT tall, as wide as needed."""
    font = _font(size)
    probe = ImageDraw.Draw(Image.new("1", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), text, font=font)
    img = Image.new("1", (max(1, right - left) + 2 * pad, HEIGHT), 0)
    d = ImageDraw.Draw(img)
    # centre vertically, and strip the font's own bearing so it sits flush
    d.text((pad - left, (HEIGHT - (bottom - top)) // 2 - top), text,
           font=font, fill=1)
    return img


def scroll(badge, img, fps=30, gap=WIDTH):
    """Scroll an image right-to-left across the display, once."""
    delay = 1.0 / fps
    for x in range(gap, -(img.size[0] + 1), -1):
        badge.push(img, x=x)
        time.sleep(delay)


# --- demo ----------------------------------------------------------------

if __name__ == "__main__":
    import sys

    message = " ".join(sys.argv[1:]) or "HELLO WORLD"

    with BadgeDisplay() as badge:
        # 1. a static frame drawn by hand
        img = Image.new("1", (WIDTH, HEIGHT), 0)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, WIDTH - 1, HEIGHT - 1], outline=1)
        d.line([0, 0, WIDTH - 1, HEIGHT - 1], fill=1)
        d.line([0, HEIGHT - 1, WIDTH - 1, 0], fill=1)
        badge.push(img)
        time.sleep(1.5)

        # 2. text, static if it fits, scrolled if it does not
        txt = text_image(message)
        print("rendered %r -> %dx%d" % (message, txt.size[0], txt.size[1]))
        if txt.size[0] <= WIDTH:
            badge.push(txt, x=(WIDTH - txt.size[0]) // 2)   # centred!
            time.sleep(2.0)
        else:
            scroll(badge, txt, fps=30)

        badge.clear()
