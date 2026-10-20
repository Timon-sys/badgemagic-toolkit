"""Client for the ng protocol over the badge's USB interfaces.

Frame: 'N' 'G' len_lo len_hi payload[len]
Payload: a command byte followed by that command's arguments.

Anything not starting with 'NG' is passed through to the legacy
("wang") parser by the firmware, so normal uploads still work.
"""
import struct

COLS, ROWS = 44, 11

CMD_POWER      = 1
CMD_STREAM_SET = 2
CMD_STREAM_BM  = 3
CMD_BLE        = 4
CMD_SPLASH     = 5
CMD_SAVE       = 6
CMD_FALLBACK   = 7
CMD_MISC       = 8

NUL = bytes([0])


class Badge:
    """Base class; subclasses implement _write_frame()."""

    HID_REPORT = 64

    def send(self, payload):
        frame = b'NG' + struct.pack('<H', len(payload)) + payload
        self._write_frame(frame)

    # --- commands ---
    def stream_on(self):     self.send(bytes([CMD_STREAM_SET, 0x00]))
    def stream_off(self):    self.send(bytes([CMD_STREAM_SET, 0x01]))
    def push(self, fb):      self.send(bytes([CMD_STREAM_BM]) + fb)
    def load_defaults(self): self.send(bytes([CMD_FALLBACK]))
    def save_cfg(self):      self.send(bytes([CMD_SAVE]))

    def ble_always_on(self, on=True):
        self.send(bytes([CMD_BLE, 0x00, 1 if on else 0]))

    def splash_speed(self, ms):
        self.send(bytes([CMD_MISC, 0x00]) + struct.pack('<H', ms))

    def brightness(self, lvl):
        self.send(bytes([CMD_MISC, 0x01, lvl]))

    def set_time(self, t):
        """t: datetime. Needs firmware with misc fn 2 (2026-10-17+)."""
        self.send(bytes([CMD_MISC, 0x02]) + struct.pack('<H', t.year)
                  + bytes([t.month, t.day, t.hour, t.minute, t.second]))

    def battery(self):
        """(raw_adc, millivolts, charging). HID only; firmware 2026-10-17+."""
        self.d.set_nonblocking(0)
        self.send(bytes([CMD_MISC, 0x03]))
        r = bytes(self.d.read(64, 1000))
        if r[:3] != b'BAT':
            raise RuntimeError('no battery reply (old firmware?) got %r' % r[:8])
        raw, mv = struct.unpack('<HH', r[3:7])
        return raw, mv, bool(r[7])


class HidBadge(Badge):
    """USB HID transport (VID 0416 / PID 5020, interface 0)."""

    def __init__(self, vid=0x0416, pid=0x5020, path=None):
        import hid
        if path is None:
            paths = HidBadge.paths(vid, pid)
            if not paths:
                raise RuntimeError('badge HID interface not found')
            path = paths[0]
        self.d = hid.device()
        self.d.open_path(path)

    @staticmethod
    def paths(vid=0x0416, pid=0x5020):
        """HID paths of every connected badge, in a stable (sorted) order.
        All badges report the same serial, so the path is the only handle."""
        import hid
        return sorted(d['path'] for d in hid.enumerate(vid, pid)
                      if d['interface_number'] == 0)

    def close(self):
        self.d.close()

    def _write_frame(self, frame):
        # HID OUT reports are a fixed 64 bytes; report ID 0 is prepended.
        n = self.HID_REPORT
        for i in range(0, len(frame), n):
            chunk = frame[i:i + n]
            chunk = chunk + bytes(n - len(chunk))
            self.d.write(NUL + chunk)


class SerialBadge(Badge):
    """USB CDC transport (the badge's COM port / ttyACM).

    Needs toolkit firmware 1.3.0 or later on Windows: older builds ignore
    SET_LINE_CODING, so opening the COM port fails with error 31 there
    (Linux/macOS never waited for it). The baud rate is ignored.
    """

    def __init__(self, port):
        import serial
        self.s = serial.Serial(port, 115200, timeout=1.0)

    def close(self):
        self.s.close()

    def _write_frame(self, frame):
        self.s.write(frame)
        self.s.flush()


async def ble_find(address=None, timeout=8.0):
    """BLE device of a badge: the one at `address`, else the strongest one in
    range. Matches on the advertised services (fee0 = app upload, f055 = ng)
    rather than the name, which can be changed."""
    from bleak import BleakScanner
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    badges = []
    for addr, (dev, adv) in found.items():
        uuids = [u.lower() for u in adv.service_uuids]
        if address and addr.upper() == address.upper():
            return dev
        if any(u.startswith(("0000fee0", "0000f055")) for u in uuids):
            badges.append((adv.rssi, dev))
    if address or not badges:
        return None
    return max(badges, key=lambda b: b[0])[1]


def blank():
    return [0] * COLS


def fb_bytes(cols):
    """cols: 44 ints, bit r = row r (0 = top)."""
    return b''.join(struct.pack('<H', c & 0x7FF) for c in cols)


def from_rows(rows):
    """rows: 11 strings of up to 44 chars; space, underscore and dot are off."""
    assert len(rows) == ROWS, len(rows)
    cols = blank()
    for r, line in enumerate(rows):
        line = line.ljust(COLS)[:COLS]
        for c, ch in enumerate(line):
            if ch not in (' ', '_', '.'):
                cols[c] |= (1 << r)
    return cols
