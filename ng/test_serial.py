"""test_stream.py over USB serial (CDC) instead of HID. Linux/macOS only.

    python3 test_serial.py              # first badge found
    python3 test_serial.py /dev/ttyACM1
"""
import sys
import time

from serial.tools import list_ports

from badge_ng import *


def find_ports():
    return sorted(p.device for p in list_ports.comports()
                  if (p.vid, p.pid) == (0x0416, 0x5020))


ports = find_ports()
print("badge serial ports:", ports or "none")
port = sys.argv[1] if len(sys.argv) > 1 else (ports or [None])[0]
if port is None:
    sys.exit("no badge serial port found -- plugged in?")

b = SerialBadge(port)
print("opened", port)

b.stream_on(); time.sleep(0.3)

print("1) all pixels on")
b.push(fb_bytes([0x7FF] * COLS)); time.sleep(1.5)

print("2) checkerboard")
b.push(fb_bytes([0x555 if c % 2 == 0 else 0x2AA for c in range(COLS)])); time.sleep(1.5)

print("3) border box")
cols = blank()
for c in range(COLS):
    cols[c] |= (1 << 0) | (1 << (ROWS - 1))
cols[0] = cols[COLS - 1] = 0x7FF
b.push(fb_bytes(cols)); time.sleep(1.5)

print("4) sweeping bar, timing 2000 frames")
t0 = time.time(); n = 2000
for i in range(n):
    cols = blank()
    cols[i % COLS] = 0x7FF
    cols[(i + 1) % COLS] = 0x7FF
    b.push(fb_bytes(cols))
dt = time.time() - t0
print("   %d frames in %.2fs = %.1f fps" % (n, dt, n / dt))

time.sleep(0.5)
b.stream_off()
b.close()
print("done; streaming off, back to normal mode")
