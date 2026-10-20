"""badgetool - one tool for CH582 / LS32 LED name badges.

Run without arguments for an interactive menu, or use a command:

  python badgetool.py list                      what is plugged in
  python badgetool.py status                    everything the badge reports
  python badgetool.py battery [-w 5]            voltage / raw ADC / charging
  python badgetool.py time                      set the clock to the PC time
  python badgetool.py brightness 0-3            3 = brightest
  python badgetool.py ble on|off                always-on Bluetooth (reboots)
  python badgetool.py name "My Badge"           Bluetooth name, max 20 chars (reboots)
  python badgetool.py splash on|off             startup animation
  python badgetool.py text "Hi" "Second slot"   one message per slot (USB or BLE)
  python badgetool.py upload config.toml        full badgemagic config file
  python badgetool.py image pic.png [--invert]  static image into slot 1 (dark = lit)
  python badgetool.py stream white|off|pic.png  live picture (custom firmware)
  python badgetool.py reset | off               reboot / power off (custom firmware)
  python badgetool.py flash pb6|normal|X.bin    flash the custom firmware (ISP mode; -fastble variants too)

Channel (default USB HID):
  --ble                 scan and pick a badge over Bluetooth
  --ble AA:BB:CC:DD:EE:FF   or a chip UID like 11-22-33-44-55-66-77-88
  --serial              not supported yet (see SerialBadge)
Over BLE everything works except flash; status and battery show only the
battery % + device info (no voltage, clock or settings yet).

Badges it knows:
  custom  CH582 with our patched FOSSASIA firmware ("FOSSASIA WAS HERE")
  stock   CH582 with factory firmware ("wch.cn" / "CH583") - text/image only
  ls32    older USB-only badge ("LS32 Custm HID")          - text/image only
Settings commands save to the badge's EEPROM. With several badges on USB, pick
one with -i N (see 'list').
"""
import argparse
import asyncio
import datetime
import os
import shutil
import struct
import subprocess
import sys
import tomllib
import time

import hid

HERE = os.path.dirname(os.path.abspath(__file__))
# wchisp: tools/wchisp-win-x64/ or tools/ next to this file, else PATH; None = not installed
WCHISP = next((c for c in (os.path.join(HERE, "tools", "wchisp-win-x64", "wchisp.exe"),
                           os.path.join(HERE, "tools", "wchisp.exe"),
                           os.path.join(HERE, "tools", "wchisp")) if os.path.isfile(c)),
              None) or shutil.which("wchisp")
# prebuilt firmware: pb6 = boards with LED line T on PB6 (dead columns and a
# flickering row on the normal build), normal = everything else; -fastble =
# 15-30 ms BLE interval + MTU 96 for ~20 fps streaming (more battery while connected)
FIRMWARE = {v: os.path.join(HERE, "firmware", f"badgemagic-ch582-2key{s}.bin")
            for v, s in (("normal", ""), ("pb6", "-pb6"),
                         ("normal-fastble", "-fastble"), ("pb6-fastble", "-pb6-fastble"))}

VID, PID = 0x0416, 0x5020
COLS, ROWS = 44, 11

# ng protocol (custom firmware only)
CMD_POWER, CMD_STREAM_SET, CMD_STREAM_BM, CMD_BLE = 1, 2, 3, 4
CMD_SAVE, CMD_MISC = 6, 8
MISC_SPLASH, MISC_BRIGHTNESS, MISC_TIME, MISC_BATTERY, MISC_STATUS = 0, 1, 2, 3, 4
MODES = ["menu", "slots", "BT download", "clock", "game", "power off"]


# 8x11 font of the FOSSASIA Badge Magic app (lib/others/data_to_bytearray_converter.dart):
# one character = one 8-column block = 11 row bytes, MSB = leftmost pixel.
APP_FONT = {
    '0': "007CC6CEDEF6E6C6C67C00", '1': "0018387818181818187E00", '2': "007CC6060C183060C6FE00",
    '3': "007CC606063C0606C67C00", '4': "000C1C3C6CCCFE0C0C1E00", '5': "00FEC0C0FC060606C67C00",
    '6': "007CC6C0C0FCC6C6C67C00", '7': "00FEC6060C183030303000", '8': "007CC6C6C67CC6C6C67C00",
    '9': "007CC6C6C67E0606C67C00", '#': "006C6CFE6C6CFE6C6C0000", '&': "00386C6C3876DCCCCC7600",
    '_': "00000000000000000000FF", '-': "0000000000FE0000000000", '?': "007CC6C60C181800181800",
    '@': "00003C429DA5ADB6403C00", '(': "000C183030303030180C00", ')': "0030180C0C0C0C0C183000",
    '=': "0000007E00007E00000000", '+': "00000018187E1818000000", '!': "00183C3C3C181800181800",
    "'": "1818081000000000000000", ':': "0000001818000018180000", '%': "006092966C106CD2920C00",
    '/': "000002060C183060C08000", '"': "6666222200000000000000", '[': "003C303030303030303C00",
    ']': "003C0C0C0C0C0C0C0C3C00", ' ': "0000000000000000000000", '*': "000000663CFF3C66000000",
    ',': "0000000000000030301020", '.': "0000000000000000303000", '$': "107CD6D6701CD6D67C1010",
    '~': "0076DC0000000000000000", '{': "000E181818701818180E00", '}': "00701818180E1818187000",
    '<': "00060C18306030180C0600", '>': "006030180C060C18306000", '^': "386CC60000000000000000",
    '`': "1818100800000000000000", ';': "0000001818000018180810", '\\': "0080C06030180C06020000",
    '|': "0018181818001818181800", 'a': "00000000780C7CCCCC7600", 'b': "00E060607C666666667C00",
    'c': "000000007CC6C0C0C67C00", 'd': "001C0C0C7CCCCCCCCC7600", 'e': "000000007CC6FEC0C67C00",
    'f': "001C363078303030307800", 'g': "00000076CCCCCC7C0CCC78", 'h': "00E060606C76666666E600",
    'i': "0018180038181818183C00", 'j': "0C0C001C0C0C0C0CCCCC78", 'k': "00E06060666C78786CE600",
    'l': "0038181818181818183C00", 'm': "00000000ECFED6D6D6C600", 'n': "00000000DC666666666600",
    'o': "000000007CC6C6C6C67C00", 'p': "000000DC6666667C6060F0", 'q': "0000007CCCCCCC7C0C0C1E",
    'r': "00000000DE76606060F000", 's': "000000007CC6701CC67C00", 't': "00103030FC303030341800",
    'u': "00000000CCCCCCCCCC7600", 'v': "00000000C6C6C66C381000", 'w': "00000000C6D6D6D6FE6C00",
    'x': "00000000C66C38386CC600", 'y': "000000C6C6C6C67E060CF8", 'z': "00000000FE8C183062FE00",
    'A': "00386CC6C6FEC6C6C6C600", 'B': "00FC6666667C666666FC00", 'C': "007CC6C6C0C0C0C6C67C00",
    'D': "00FC66666666666666FC00", 'E': "00FE66626878686266FE00", 'F': "00FE66626878686060F000",
    'G': "007CC6C6C0C0CEC6C67E00", 'H': "00C6C6C6C6FEC6C6C6C600", 'I': "003C181818181818183C00",
    'J': "001E0C0C0C0C0CCCCC7800", 'K': "00E6666C6C786C6C66E600", 'L': "00F060606060606266FE00",
    'M': "0082C6EEFED6C6C6C6C600", 'N': "0086C6E6F6DECEC6C6C600", 'O': "007CC6C6C6C6C6C6C67C00",
    'P': "00FC6666667C606060F000", 'Q': "007CC6C6C6C6C6D6DE7C06", 'R': "00FC6666667C6C6666E600",
    'S': "007CC6C660380CC6C67C00", 'T': "007E7E5A18181818183C00", 'U': "00C6C6C6C6C6C6C6C67C00",
    'V': "00C6C6C6C6C6C66C381000", 'W': "00C6C6C6C6D6FEEEC68200", 'X': "00C6C66C7C387C6CC6C600",
    'Y': "00666666663C1818183C00", 'Z': "00FEC6860C183062C6FE00", 'Á': "0810386CC6C6FEC6C6C600",
    'À': "2010386CC6C6FEC6C6C600", 'Â': "1028386CC6C6FEC6C6C600", 'Ä': "2800386CC6C6FEC6C6C600",
    'Å': "1028107CC6C6FEC6C6C600", 'É': "0810FE626878686266FE00", 'È': "2010FE626878686266FE00",
    'Ê': "1028FE626878686266FE00", 'Ë': "2800FE626878686266FE00", 'Ě': "2810FE626878686266FE00",
    'Í': "04083C1818181818183C00", 'Ì': "10083C1818181818183C00", 'Î': "08143C1818181818183C00",
    'Ï': "14003C1818181818183C00", 'Ó': "08107CC6C6C6C6C6C67C00", 'Ò': "20107CC6C6C6C6C6C67C00",
    'Ô': "10287CC6C6C6C6C6C67C00", 'Ö': "28007CC6C6C6C6C6C67C00", 'Ő': "14287CC6C6C6C6C6C67C00",
    'Ú': "0810C6C6C6C6C6C6C67C00", 'Ù': "2010C6C6C6C6C6C6C67C00", 'Û': "1028C6C6C6C6C6C6C67C00",
    'Ü': "2800C6C6C6C6C6C6C67C00", 'Ű': "1428C6C6C6C6C6C6C67C00", 'Ů': "102810C6C6C6C6C6C67C00",
    'Ý': "04086666663C1818183C00", 'Ÿ': "14006666663C1818183C00", 'á': "00000810780C7CCCCC7600",
    'à': "00002010780C7CCCCC7600", 'â': "00102800780C7CCCCC7600", 'ä': "00002800780C7CCCCC7600",
    'å': "00102810780C7CCCCC7600", 'é': "000008107CC6FEC0C67C00", 'è': "000020107CC6FEC0C67C00",
    'ê': "001028007CC6FEC0C67C00", 'ë': "000028007CC6FEC0C67C00", 'ě': "000028107CC6FEC0C67C00",
    'í': "0000081038181818183C00", 'ì': "0000201038181818183C00", 'î': "0008140038181818183C00",
    'ï': "0000140038181818183C00", 'ó': "000008107CC6C6C6C67C00", 'ò': "000020107CC6C6C6C67C00",
    'ô': "001028007CC6C6C6C67C00", 'ö': "000028007CC6C6C6C67C00", 'ő': "000014287CC6C6C6C67C00",
    'ú': "00000810CCCCCCCCCC7600", 'ù': "00002010CCCCCCCCCC7600", 'û': "00102800CCCCCCCCCC7600",
    'ü': "00002800CCCCCCCCCC7600", 'ű': "00001428CCCCCCCCCC7600", 'ů': "00102810CCCCCCCCCC7600",
    'ý': "000810C6C6C6C67E060CF8", 'ÿ': "002800C6C6C6C67E060CF8", 'Ç': "007CC6C6C0C0C0C67C1030",
    'ç': "000000007CC6C0467C1030", 'Ñ': "342CC6E6F6DECEC6C6C600", 'ñ': "00342C00DC666666666600",
    'Č': "28107CC6C6C0C0C6C67C00", 'č': "000028107CC6C0C0C67C00", 'Ď': "2810FC666666666666FC00",
    'ď': "02061C0C7CCCCCCCCC7600", 'Ň': "2810C6E6F6DECEC6C6C600", 'ň': "00002810DC666666666600",
    'Ř': "2810FC66667C6C6666E600", 'ř': "00002810DE76606060F000", 'Š': "28107CC6E0380CC6C67C00",
    'š': "000028107CC6701CC67C00", 'Ť': "14087E7E5A181818183C00", 'ť': "00143430FC303030341800",
    'Ž': "2810FE860C183062C6FE00",
}

# u8g2_font_lucasfont_alternate_tf (u8g2, olikraus) - the font badgemagic.exe uses.
# Lucasfont Alternate (c) Patrick Lauke 2012. Decoded by U8g2Font below.
LUCASFONT_U8G2 = bytes.fromhex(
    "a40003020404020405090b00ff07ff0700013a026806a62005002205210771a2c4100522073332456209230e75a24d29"
    "4906a53228a52401240c75a25536888338681100250a77227692a5dd9218260d76e28d16b56951a2454b00270631b2c4"
    "00280873225552aa15290973224556aa94002a0d57264e568986214ab20a002b0a55a655180d5218012c0732de4ca200"
    "2d0616eec5012e0621a284002f08772276da6700300a75a2cd92794b1600310975a25526761a04320a75a2cd928559db"
    "20330c75a2c59086c910868302340c75a25d2625a564d0c204350a75a2c5750db56401360c75a2cd9289439269c90237"
    "0a75a2c52066c52600380c75a2cd9269c99269c902390c75a2cd9269c9106ac9023a0641a644143b0862de4c9a28003c"
    "0874625dd4d8003d0835aac5a00e023e08746245d8d4063f0b75a2cd9285591d8a00400f7722cea0a492a25494611f14"
    "00410b75a2cd9269c390d902420d75a2c59064daa064daa000430975a2cd20761d02440a75a2c59064de0605450b75a2"
    "c5311c92301c04460a75a2c5311c92b008470c75a2cd9289c99069c902480a75a245661b86cc16490671a2c4214a0975"
    "a265472d59004b0d75a2452625252d892a59004c0875a245d8e3204d0c772246ba2d152952ad014e0c76e245b8299194"
    "68a3184f0a75a2cd92794b1600500c75a2c59064daa0844500510b75a2cd92b92452a404520d75a2c59064daa0942a59"
    "00530b75a2cd92a9ab962c00540975a2c520853d01550975a245e65bb200560a75a245e62da94500570b772246ea1429"
    "956d0d580b75a245a625b54a4d0b590a75a245664b6a61095a0a75a2c520661d07015b087322c510751a5c07772246de"
    "075d087322c5d469085f061722c621610a55a2cd9a0c5a3204620c65a245180e49a60d0a0063085462cd901507640a65"
    "a26565d0b46408650a55a2cd920d4a3a04660a646295120d495602670c659ecd9269c910260b00680a65a245180e4966"
    "0b690761a24432046a09731e551a9516006b0a646245561a92a6006c0762e284d2036d0c5722c6258aa4488aa4026e09"
    "55a2c590646e016f0955a2cd92d99205700c659ec59064daa0842100710a659ecda069c91016720955a2c59064621173"
    "0955a2cda01e1400740a65a2553448613501750955a245e6960c01760a55a245664b6a1100770c572246144991144995"
    "61780a55a24596d42ab500790b659e45664b863059007a0955a2c5a0b50d027b0a746295924561160a7c0671a2c4217d"
    "0b7462859885519648007e0726ee8d6401a10771a2443404a20d75a255b6549428a96c1100a30c75a2d5126643146683"
    "00a50c75a245a625b56890c208a60671a2c432a912885ed6908549640995509292301b2200ab0c56e655254aa22ccaa2"
    "00ac0735a6c52016ad0615aec520b10b75a255180d52980f02b60f76e2cd70199464c9922cc99200b70611ae4400bb0d"
    "56e6459445599444491401bf0b75a2550e65c52c5900c00da5a24d9a234ba60d43660bc10da5a25d1d59326d18325b00"
    "c20da5a25596e44ba60d43660bc30da5a28d295f326d18325b00c40c95a24d7dc9b461c86c01c50ea5a2559664d99269"
    "c390d902c61079a2ce410bb37018942cccc26c10c80da5a24d9a0f633824613808c90ca5a25d7d18c32109c341ca0ea5"
    "a25596c4c3180e49180e02cb0c95a24d7918c32109c341cc08a2e24494257dcd08a2238d96f405ce09a3224d63d41700"
    "cf0993224512467d01d00f76e2cd1065493628b5244b8604d10ea6e28d640f372592126d1403d20ca5a24d9a234be62d"
    "5900d30ba5a25d1d59326fc902d40ca5a25596e44be62d5900d50ba5a28d295f326fc902d60b85a245962c99b76401d7"
    "0a55a64596d42ab500d90ba5a24d9a67be250b00da0aa5a25d3df32d5900db0ba5a25596c4996fc902dc0a85a2459666"
    "de9205dd0ba5a25d3db325b5b004df0b845e8d12594a961a00e00c85a24d9a236b3268c910e10c85a25d1d5993414b86"
    "00e20c85a25596e46b3268c910e30c85a28d295f93414b8600e40b75a24d7d4d062d1902e50e95a255966439b2268396"
    "0c01e60d59a2ce354b8621c9d26508e80c85a24d9a234b3628e910e90c85a25d1d59b241498700ea0c85a25596e44b36"
    "28e910eb0b75a24d7dc906251d02ec0872e24494250ded0872e28c96b400ee0873224d63d402ef0963224512462d00f1"
    "0a85a28d291e92cc2df20c85a24d9a234b664b1600f30b85a25d1d59325bb200f40c85a25596e44b664b1600f50b85a2"
    "8d295f325bb200f60a75a24d7dc96cc902f70955a6553ee81100f90a85a24d9a676ec910fa0a85a25d3d734b8600fb0b"
    "85a25596c4995b3204fc0a75a24d39734b8600fd0c959e5d3db32543982c00ff0c859e4d39b32543982c0000000004ff"
    "ff00"
)


class U8g2Font:
    """Minimal decoder for u8g2's compressed font format (8-bit glyph table).

    Header (23 bytes): glyph count, bbx mode, bits per 0-run, bits per 1-run,
    bits for width/height/x/y/delta-x, ... Each glyph: [encoding][size] then a
    little-endian bit stream: w, h, x, y (signed), dx (signed), then RLE runs of
    0s and 1s, each run pair followed by a repeat bit.
    """

    def __init__(self, data):
        self.d = data
        (self.b0, self.b1, self.bw, self.bh, self.bx, self.by, self.bd) = data[2:9]
        self.glyphs = {}
        p = 23
        while p < len(data) and data[p + 1]:
            self.glyphs[data[p]] = p + 2
            p += data[p + 1]

    def _bits(self, pos):
        d = self.d
        bitpos = 0

        def get(n):
            nonlocal pos, bitpos
            v = 0
            for i in range(n):
                v |= ((d[pos] >> bitpos) & 1) << i
                bitpos += 1
                if bitpos == 8:
                    bitpos, pos = 0, pos + 1
            return v
        return get

    def glyph(self, ch):
        """-> (w, h, x_off, y_off, advance, pixels row-major) or None."""
        code = ord(ch)
        if code not in self.glyphs:
            return None
        get = self._bits(self.glyphs[code])
        sgn = lambda n: get(n) - (1 << (n - 1))
        w, h = get(self.bw), get(self.bh)
        x, y, dx = sgn(self.bx), sgn(self.by), sgn(self.bd)
        px = []
        while len(px) < w * h:
            a, b = get(self.b0), get(self.b1)
            while True:
                px += [0] * a + [1] * b
                if get(1) == 0:
                    break
        return w, h, x, y, dx, px[:w * h]

    def render(self, text, baseline=8, rows=11):
        """Like the badgemagic CLI: start at x=0, baseline row 8, advance per glyph."""
        pen = 0
        canvas = {}
        for ch in text:
            g = self.glyph(ch) or self.glyph("?")
            w, h, xo, yo, dx, px = g
            top = baseline + 1 - (h + yo)  # glyph bottom (y offset 0) lands ON the baseline row
            for r in range(h):
                for c in range(w):
                    if px[r * w + c]:
                        canvas[(pen + xo + c, top + r)] = True
            pen += dx
        width = max(pen, max((x + 1 for x, _ in canvas), default=0))
        return [[canvas.get((x, y), False) for x in range(width)] for y in range(rows)]


THIN_FONT = U8g2Font(LUCASFONT_U8G2)

# ---------------------------------------------------------------- discovery

def find_badges():
    out = []
    for d in hid.enumerate(VID, PID):
        if d.get("interface_number", 0) not in (0, -1):
            continue
        man, prod = d["manufacturer_string"] or "", d["product_string"] or ""
        if man == "FOSSASIA WAS HERE":
            kind = "custom"
        elif prod == "LS32 Custm HID":
            kind = "ls32"
        elif man == "wch.cn" or "CH583" in prod:
            kind = "stock"
        else:
            kind = "unknown"
        out.append({"kind": kind, "path": d["path"], "man": man, "prod": prod})
    return out


class Badge:
    def __init__(self, info):
        self.kind = info["kind"]
        self.info = info
        self.d = hid.device()
        self.d.open_path(info["path"])

    def close(self):
        try:
            self.d.close()
        except Exception:
            pass

    # raw 64-byte HID OUT reports, report ID 0 in front
    def write_reports(self, data):
        for i in range(0, len(data), 64):
            chunk = data[i:i + 64]
            self.d.write(b"\x00" + chunk + bytes(64 - len(chunk)))

    # --- ng (custom firmware) ---
    def need_custom(self):
        if self.kind != "custom":
            sys.exit(f"this needs the custom firmware; this badge is '{self.kind}'")

    def ng(self, payload):
        self.need_custom()
        self.write_reports(b"NG" + struct.pack("<H", len(payload)) + payload)

    def ng_query(self, payload, magic):
        self.d.set_nonblocking(0)
        self.ng(payload)
        r = bytes(self.d.read(64, 1000))
        if r[:3] != magic:
            raise RuntimeError("no reply from the badge; this needs the patched firmware "
                               "from this repo (try 'badgetool.py flash')")
        return r

    def status(self):
        r = self.ng_query(bytes([CMD_MISC, MISC_STATUS]), b"STA")
        y = struct.unpack_from("<H", r, 30)[0]
        return {
            "firmware": r[44:64].split(b"\0")[0].decode(errors="replace"),
            "ble_always_on": bool(r[4]),
            "brightness": r[5],
            "splash_ms": struct.unpack_from("<H", r, 6)[0],
            "reset_after_upload": bool(r[8]),
            "ble_security": bool(r[9]),
            "ble_name": r[10:30].split(b"\0")[0].decode(errors="replace"),
            "time": f"{y:04d}-{r[32]:02d}-{r[33]:02d} {r[34]:02d}:{r[35]:02d}:{r[36]:02d}",
            "batt_raw": struct.unpack_from("<H", r, 37)[0],
            "batt_mv": struct.unpack_from("<H", r, 39)[0],
            "charging": bool(r[41]),
            "mode": MODES[r[42]] if r[42] < len(MODES) else str(r[42]),
            "streaming": bool(r[43] & 1),
            "charging_screen": bool(r[43] & 2),
        }

    def battery(self):
        r = self.ng_query(bytes([CMD_MISC, MISC_BATTERY]), b"BAT")
        raw, mv = struct.unpack_from("<HH", r, 3)
        return raw, mv, bool(r[7])

    def set_time(self, t=None):
        t = t or datetime.datetime.now()
        self.ng(bytes([CMD_MISC, MISC_TIME]) + struct.pack("<H", t.year)
                + bytes([t.month, t.day, t.hour, t.minute, t.second]))

    def save(self):
        self.ng(bytes([CMD_SAVE]))
        time.sleep(1.0)

    def reset(self):
        self.ng(bytes([CMD_POWER, 2]))

    # --- legacy "wang" upload (works on every badge kind) ---
    def upload_slots(self, slots):
        pkt = legacy_packet(slots)
        self.write_reports(pkt + bytes(-len(pkt) % 64))

    def upload_bitmap(self, img, mode="center", speed=4):
        self.upload_slots([make_slot(to_column_groups(img)[0], mode, speed)])


SLOT_MODES = ["left", "right", "up", "down", "center", "fast", "drop", "curtain", "laser"]
TEXT_SUBST = {"ß": "ss", "„": '"', "“": '"', "”": '"', "’": "'", "–": "-"}


FONTS = ["thin", "app"]  # thin = badgemagic.exe's Lucasfont, app = Badge Magic app's 8x11


def text_blocks(text, font="thin"):
    """Text -> 11-byte blocks. 'thin' renders proportionally like badgemagic.exe
    (baseline row 8, width rounded up to 8); 'app' uses one 8x11 block per
    character like the phone app."""
    if font == "thin":
        return to_column_groups(THIN_FONT.render(text), center=False)[0]
    for k, v in TEXT_SUBST.items():
        text = text.replace(k, v)
    out = bytearray()
    for ch in text:
        out += bytes.fromhex(APP_FONT.get(ch, APP_FONT["?"]))
    return bytes(out)


def make_slot(data, mode="left", speed=4, blink=False, border=False):
    """data: 11 bytes per 8-column block (from text_blocks or to_column_groups)."""
    if mode not in SLOT_MODES:
        raise ValueError(f"mode must be one of {', '.join(SLOT_MODES)}")
    return {"data": data, "groups": len(data) // 11, "mode": SLOT_MODES.index(mode),
            "speed": speed, "blink": blink, "border": border}


def legacy_packet(slots, year_byte=None):
    """The 'wang' upload the Badge Magic app sends (data_to_bytearray_converter.dart):
    0 'wang' 0 0 | 6 blink bits | 7 border bits | 8..15 speed<<4|mode per slot |
    16..31 slot lengths in 8-col blocks, big endian | 38..43 time | 64.. block data.
    year_byte: the CH582 firmware sets its clock from a BLE upload and decodes the
    year as (year & 0xFF)."""
    if not 1 <= len(slots) <= 8:
        raise ValueError("1 to 8 slots")
    hdr = bytearray(64)
    hdr[0:4] = b"wang"
    for i, sl in enumerate(slots):
        hdr[6] |= (1 << i) if sl["blink"] else 0
        hdr[7] |= (1 << i) if sl["border"] else 0
        hdr[8 + i] = (sl["speed"] << 4) | sl["mode"]
        hdr[16 + 2 * i], hdr[17 + 2 * i] = sl["groups"] >> 8, sl["groups"] & 0xFF
    t = time.localtime()
    y = t.tm_year % 100 if year_byte is None else year_byte
    hdr[38:44] = bytes([y, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec])
    return bytes(hdr) + b"".join(sl["data"] for sl in slots)


# ---------------------------------------------------------------- BLE

UUID = "0000{:04x}-0000-1000-8000-00805f9b34fb".format
NG_WRITE, NG_NOTIFY, LEGACY_WRITE = UUID(0xF057), UUID(0xF056), UUID(0xFEE1)
BATT_LEVEL = UUID(0x2A19)
DEVINFO = {"model": UUID(0x2A24), "firmware": UUID(0x2A26), "hardware": UUID(0x2A27)}


def ble_address(s):
    """Accept a BLE address or a chip UID (first 6 UID bytes reversed = address)."""
    parts = [p for p in s.replace("-", ":").split(":") if p]
    if len(parts) == 8:
        parts = parts[:6][::-1]
    if len(parts) != 6:
        sys.exit(f"'{s}' is neither a BLE address nor a chip UID")
    return ":".join(p.upper().zfill(2) for p in parts)


def ble_scan(seconds=6):
    from bleak import BleakScanner

    async def run():
        return await BleakScanner.discover(timeout=seconds, return_adv=True)
    found = []
    for addr, (dev, adv) in asyncio.run(run()).items():
        name = adv.local_name or dev.name or ""
        uuids = [u.lower() for u in adv.service_uuids]
        if (name in ("LED Badge Magic", "LSLED")
                or any(u.startswith(("0000f055", "0000fee0")) for u in uuids)):
            found.append((addr.upper(), name, adv.rssi))
    return sorted(found, key=lambda f: -f[2])


class BleBadge:
    """Same interface as Badge, over Bluetooth (bleak). keep=True leaves the
    connection open between commands (menu); close() then does nothing."""

    def __init__(self, address, keep=False):
        from bleak import BleakClient
        self.address, self.keep = address, keep
        self.loop = asyncio.new_event_loop()
        self.client = BleakClient(address, timeout=15)
        print(f"connecting to {address} over Bluetooth ...")
        for attempt in (1, 2):  # WinRT connects fail now and then; one retry fixes it
            try:
                self._run(self.client.connect())
                break
            except Exception:
                if attempt == 2:
                    raise
                print("  no luck, trying once more ...")
                time.sleep(2)
        uuids = {c.uuid for s in self.client.services for c in s.characteristics}
        self.kind = "custom" if NG_WRITE in uuids else "stock"
        self.info = {"man": "BLE", "prod": address}

    def _run(self, coro):
        return self.loop.run_until_complete(coro)

    def close(self, force=False):
        if self.keep and not force:
            return
        try:
            self._run(self.client.disconnect())
        except Exception:
            pass
        self.loop.close()

    need_custom = Badge.need_custom

    def ng(self, payload):
        # BLE carries the raw [cmd, args...] payload; the 'NG' len framing is USB-only
        self.need_custom()
        self._run(self.client.write_gatt_char(NG_WRITE, payload, response=True))

    def status(self):
        s = {k: self._run(self.client.read_gatt_char(u)).split(b"\0")[0].decode(errors="replace")
             for k, u in DEVINFO.items()}
        s["battery_pct"] = self.battery_pct()
        return s

    def battery_pct(self):
        return self._run(self.client.read_gatt_char(BATT_LEVEL))[0]

    def battery(self):
        raise RuntimeError("voltage over BLE not implemented yet (firmware TODO); "
                           "use 'status' for the battery percentage")

    set_time = Badge.set_time
    save = Badge.save
    reset = Badge.reset

    def upload_slots(self, slots):
        pkt = legacy_packet(slots, year_byte=time.localtime().tm_year & 0xFF)
        pkt += bytes(-len(pkt) % 16)
        for i in range(0, len(pkt), 16):  # the legacy service takes 16-byte writes, like the app
            self._run(self.client.write_gatt_char(LEGACY_WRITE, pkt[i:i + 16], response=True))
        if self.kind == "custom":
            # the firmware sets its clock from the header timestamp only when the
            # transfer completes, so a slow BLE upload leaves it that far behind
            self.set_time()

    upload_bitmap = Badge.upload_bitmap


class SerialBadge:
    """CDC serial (the badge's second USB interface, a COM port).

    Not implemented yet. The firmware already feeds CDC writes into the same
    ng parser as HID, but Windows cannot open the port: cdc_request_handler()
    in src/usb/composite/cdc-serial.c ignores SET_LINE_CODING /
    GET_LINE_CODING / SET_CONTROL_LINE_STATE, so opening the COM port fails
    with error 31 (pyserial: "A device attached to the system is not
    functioning"). The CDC OUT handler also has the zero-length-IN toggle bug
    that was fixed for HID, and status/battery replies only go out over HID.
    """

    def __init__(self, *a, **kw):
        sys.exit("serial is not supported yet (firmware can't be opened as a COM port on Windows)")


# channel picked in the menu / by --ble; None = USB HID
SESSION = {"ble": None}


def open_one(args=None):
    ble = getattr(args, "ble", None)
    if getattr(args, "serial", False):
        return SerialBadge()
    if SESSION["ble"] is not None and ble is None:
        return SESSION["ble"]
    if ble:
        if ble == "scan":
            found = ble_scan()
            if not found:
                sys.exit("no badge found over Bluetooth (switched on? Bluetooth always-on or BT mode?)")
            for i, (addr, name, rssi) in enumerate(found):
                print(f"#{i}  {addr}  {name or '(no name)'}  {rssi} dBm")
            pick = int(input("which one? ")) if len(found) > 1 else 0
            ble = found[pick][0]
        return BleBadge(ble_address(ble))
    badges = find_badges()
    if not badges:
        sys.exit("no badge found on USB (is it plugged in and switched on?)")
    idx = getattr(args, "index", 0) or 0
    if not 0 <= idx < len(badges):
        sys.exit(f"no badge #{idx} on USB; there {'is' if len(badges) == 1 else 'are'} "
                 f"{len(badges)} (see 'list')")
    if len(badges) > 1 and not getattr(args, "index", None):
        print(f"note: {len(badges)} badges connected, using #0 (pick one with -i N)")
    return Badge(badges[idx])


def wait_for_custom(timeout=30):
    time.sleep(3)  # let the old USB instance disappear first
    end = time.time() + timeout
    while time.time() < end:
        if any(b["kind"] == "custom" for b in find_badges()):
            time.sleep(1)
            return True
        time.sleep(1)
    return False


def reboot_and_restore_time(b):
    """Reboot. The RTC keeps running across the reset, but it drifts (internal RC
    oscillator), so set it to the PC time while we're at it."""
    if isinstance(b, BleBadge):
        addr, keep = b.address, b.keep
        try:
            b.reset()
        except Exception:
            pass  # the link drops as the badge resets
        b.close(force=True)
        print("badge rebooting ...")
        time.sleep(6)
        try:
            b2 = BleBadge(addr, keep=keep)
        except Exception as e:
            print("could not reconnect:", e, "- set the time later with 'time'")
            SESSION["ble"] = None
            return
        b2.set_time()
        print("back up, clock restored")
        if keep:
            SESSION["ble"] = b2
        else:
            b2.close()
        return
    b.reset()
    b.close()
    print("badge rebooting ...")
    if wait_for_custom():
        b2 = Badge(next(x for x in find_badges() if x["kind"] == "custom"))
        b2.set_time()
        b2.close()
        print("back up, clock restored")
    else:
        print("badge did not come back within 30 s; run 'badgetool.py time' later")


# ---------------------------------------------------------------- images

def load_image(path, invert=False):
    from PIL import Image
    img = Image.open(path).convert("L")
    if img.height != ROWS:
        w = max(1, round(img.width * ROWS / img.height))
        img = img.resize((w, ROWS), Image.LANCZOS)
    return [[(img.getpixel((x, y)) >= 128) == invert for x in range(img.width)]
            for y in range(ROWS)]


def to_column_groups(img, center=True):
    """rows of bools -> (11 bytes per 8-px group, MSB left; group count)."""
    w = len(img[0])
    if w == 0:
        img, w = [[False] for _ in range(ROWS)], 1
    if center and w < COLS:  # centre on the display
        pad = (COLS - w) // 2
        img = [[False] * pad + r + [False] * (COLS - w - pad) for r in img]
        w = COLS
    groups = (w + 7) // 8
    out = bytearray()
    for g in range(groups):
        for r in range(ROWS):
            b = 0
            for bit in range(8):
                x = g * 8 + bit
                if x < w and img[r][x]:
                    b |= 0x80 >> bit
            out.append(b)
    return bytes(out), groups


def preview(img):
    for row in img:
        print("".join("#" if p else "." for p in row))


def cols_from_image(img):
    """rows of bools (cropped/padded to 44) -> 44 column words for streaming."""
    w = len(img[0])
    off = (w - COLS) // 2 if w > COLS else 0
    pad = (COLS - w) // 2 if w < COLS else 0
    cols = [0] * COLS
    for c in range(COLS):
        x = c - pad + off
        if 0 <= x < w:
            for r in range(ROWS):
                if img[r][x]:
                    cols[c] |= 1 << r
    return cols


# ---------------------------------------------------------------- commands

def cmd_list(a):
    if getattr(a, "ble", None):
        found = ble_scan()
        if not found:
            print("no badge found over Bluetooth")
        for i, (addr, name, rssi) in enumerate(found):
            print(f"#{i}  {addr}  {name or '(no name)'}  {rssi} dBm")
        return
    badges = find_badges()
    if not badges:
        print("no badge on USB")
    for i, b in enumerate(badges):
        what = {"custom": "CH582, custom firmware (full control)",
                "stock": "CH582, factory firmware (text/image only)",
                "ls32": "LS32 badge, factory firmware (text/image only)",
                "unknown": "unknown 0416:5020 device"}[b["kind"]]
        extra = ""
        if b["kind"] == "unknown":
            extra = f'  (manufacturer "{b["man"]}", product "{b["prod"]}")'
        if b["kind"] == "custom":
            try:
                bd = Badge(b)
                extra = f'  "{bd.status()["ble_name"]}"'
                bd.close()
            except Exception:
                pass
        print(f"#{i}  {what}{extra}")
    if WCHISP:
        r = subprocess.run([WCHISP, "probe"], capture_output=True, text=True)
        if "Found 0" not in (r.stdout + r.stderr) and "Device #" in (r.stdout + r.stderr):
            print("plus a badge in ISP (flash) mode")


def cmd_status(a):
    b = open_one(a)
    if isinstance(b, BleBadge):
        s = b.status()
        b.close()
        print(f"""address        {b.address}
firmware       {s['firmware']}   ({s['model']}, hardware {s['hardware']})
battery        {s['battery_pct']} %
(clock, voltage and settings need USB until the BLE status reply exists)""")
        return
    if b.kind != "custom":
        print(f"badge kind: {b.kind} ({b.info['man']} / {b.info['prod']})")
        print("factory firmware cannot report anything back; text/image upload works")
        return
    s = b.status()
    b.close()
    print(f"""firmware       {s['firmware']}
mode           {'charging screen - press a button to finish booting (Bluetooth is off until then)' if s['charging_screen'] else s['mode']}{'  (streaming)' if s['streaming'] else ''}
clock          {s['time']}{'   <- not set' if s['time'].startswith('2020') else ''}
battery        {s['batt_mv']/1000:.3f} V  raw {s['batt_raw']}  {'charging' if s['charging'] else 'on battery'}
brightness     {s['brightness']} / 3
bluetooth      name "{s['ble_name']}", always-on {'yes' if s['ble_always_on'] else 'no'}, PIN {'on' if s['ble_security'] else 'off'}
startup anim   {'off' if s['splash_ms'] == 0 else str(s['splash_ms']) + ' ms/frame'}
reset on rx    {'yes' if s['reset_after_upload'] else 'no'}""")


def cmd_battery(a):
    b = open_one(a)
    try:
        while True:
            if isinstance(b, BleBadge):  # no voltage reply over BLE yet, only the 0x180F level
                print(f"{time.strftime('%H:%M:%S')}  {b.battery_pct()} %  (voltage needs USB)")
            else:
                raw, mv, chg = b.battery()
                print(f"{time.strftime('%H:%M:%S')}  {mv/1000:.3f} V  raw {raw:4d}  "
                      f"{'charging' if chg else 'on battery'}")
            if not a.watch:
                break
            time.sleep(a.watch)
    except KeyboardInterrupt:
        pass
    finally:
        b.close()


def cmd_time(a):
    b = open_one(a)
    now = datetime.datetime.now()
    time.sleep(1 - now.microsecond / 1e6)  # land on a full second
    now = datetime.datetime.now().replace(microsecond=0)
    b.set_time(now)
    b.close()
    print("clock set to", now.strftime("%Y-%m-%d %H:%M:%S"))


def cmd_brightness(a):
    b = open_one(a)
    b.ng(bytes([CMD_MISC, MISC_BRIGHTNESS, a.level]))
    time.sleep(0.2)
    b.save()
    b.close()
    print(f"brightness {a.level} saved")


def cmd_ble(a):
    b = open_one(a)
    b.ng(bytes([CMD_BLE, 0, 1 if a.state == "on" else 0]))
    time.sleep(0.2)
    b.save()
    print(f"always-on Bluetooth {a.state}, saved")
    reboot_and_restore_time(b)


def cmd_name(a):
    raw = a.name.encode("ascii", "replace")
    if len(raw) > 20:
        sys.exit("name too long (max 20 characters)")
    b = open_one(a)
    b.ng(bytes([CMD_BLE, 1]) + raw)
    time.sleep(0.2)
    b.save()
    print(f'Bluetooth name "{a.name}" saved')
    reboot_and_restore_time(b)


def cmd_splash(a):
    b = open_one(a)
    ms = 0 if a.state == "off" else 50
    b.ng(bytes([CMD_MISC, MISC_SPLASH]) + struct.pack("<H", ms))
    time.sleep(0.2)
    b.save()
    b.close()
    print(f"startup animation {a.state}, saved")


def preview_blocks(data, width=None):
    """ASCII preview of 11-byte blocks (first `width` columns)."""
    n = len(data) // 11
    cols = n * 8 if width is None else min(width, n * 8)
    for r in range(ROWS):
        print("".join("#" if data[(x // 8) * 11 + r] & (0x80 >> (x % 8)) else "."
                      for x in range(cols)))


def cmd_text(a):
    """Render with the Badge Magic app font and upload, like the app does.
    Works over USB HID and Bluetooth; replaces all slots."""
    if not 1 <= len(a.messages) <= 8:
        sys.exit("1 to 8 messages")
    slots = [make_slot(text_blocks(m, a.font), a.mode, a.speed, a.blink, a.border)
             for m in a.messages]
    preview_blocks(slots[0]["data"], 88)
    if getattr(a, "preview", False):
        return
    b = open_one(a)
    b.upload_slots(slots)
    b.close()
    via = "Bluetooth" if isinstance(b, BleBadge) else "USB"
    print(f"uploaded {len(slots)} message(s) over {via} "
          f"({sum(sl['groups'] for sl in slots) * 8} px wide in total, mode {a.mode}, speed {a.speed})")


def toml_speed(m, path):
    sp = m.get("speed", 4)
    if not isinstance(sp, int) or not 0 <= sp <= 7:
        raise ValueError(f"{path}: speed must be 0-7, got {sp!r} (message {m.get('text', '')!r})")
    return sp


def cmd_upload(a):
    """badgemagic-style config.toml: [[message]] text/mode/speed/blink/border.
    Rendered like 'text' (thin font by default), so it works over USB and BLE."""
    # utf-8-sig: PowerShell writes UTF-8 with a BOM, which tomllib rejects
    with open(a.file, encoding="utf-8-sig") as f:
        cfg = tomllib.loads(f.read())
    msgs = cfg.get("message", [])
    if not 1 <= len(msgs) <= 8:
        sys.exit(f"{a.file}: needs 1 to 8 [[message]] blocks")
    slots = [make_slot(text_blocks(m.get("text", ""), getattr(a, "font", "thin")),
                       m.get("mode", "left"),
                       toml_speed(m, a.file), bool(m.get("blink", False)),
                       bool(m.get("border", False))) for m in msgs]
    b = open_one(a)
    b.upload_slots(slots)
    b.close()
    via = "Bluetooth" if isinstance(b, BleBadge) else "USB"
    print(f"uploaded {len(slots)} slot(s) from {os.path.basename(a.file)} over {via}")


def cmd_image(a):
    img = load_image(a.file, a.invert)
    preview(img)
    if a.preview:
        return
    b = open_one(a)
    b.upload_bitmap(img)
    b.close()
    print("image uploaded to slot 1 (replaces all slots)")


def cmd_stream(a):
    b = open_one(a)
    if a.what == "off":
        b.ng(bytes([CMD_STREAM_SET, 1]))
        print("streaming off")
    else:
        if a.what == "white":
            cols = [0x7FF] * COLS
        else:
            img = load_image(a.what, a.invert)
            preview(img)
            cols = cols_from_image(img)
        b.ng(bytes([CMD_STREAM_SET, 0]))
        time.sleep(0.05)
        b.ng(bytes([CMD_STREAM_BM]) + b"".join(struct.pack("<H", c & 0x7FF) for c in cols))
        print("showing it now; 'badgetool.py stream off' goes back")
    b.close()


def cmd_reset(a):
    b = open_one(a)
    reboot_and_restore_time(b)


def cmd_off(a):
    b = open_one(a)
    b.ng(bytes([CMD_POWER, 0]))
    b.close()
    print("badge switched off (top button switches it on)")


def cmd_flash(a):
    fw = FIRMWARE.get(a.firmware, a.firmware)
    if not os.path.exists(fw):
        sys.exit("firmware not found: " + fw)
    if not WCHISP:
        sys.exit("wchisp not found: get it from https://github.com/ch32-rs/wchisp/releases "
                 "and put it in tools/ or on your PATH")
    print("Put the badge in ISP mode: unplug, hold the button nearest USB, plug in.")
    print("Waiting up to 5 minutes ...")
    end = time.time() + 300
    while time.time() < end:
        r = subprocess.run([WCHISP, "probe"], capture_output=True, text=True)
        if "Device #" in r.stdout + r.stderr:
            break
        time.sleep(0.4)
    else:
        sys.exit("timed out")
    # Factory badges ship with read-out protection on and debug off. 'config reset'
    # writes WCH's default option bytes (unprotected, debug enabled, reset pin on)
    # so the flash write and verify are allowed; nothing else on the chip changes.
    subprocess.run([WCHISP, "config", "reset"])
    r = subprocess.run([WCHISP, "flash", fw])
    if r.returncode != 0:
        sys.exit("flash failed")
    print("flashed; setting the clock once it is back ...")
    if wait_for_custom():
        b = Badge(next(x for x in find_badges() if x["kind"] == "custom"))
        b.set_time()
        b.close()
        print("done")


# ---------------------------------------------------------------- menu

def pick_channel():
    """Menu start: choose how to talk to the badge and which badge."""
    while True:
        print("\nHow do you want to talk to the badge?")
        print(" 1  USB HID")
        print(" 2  USB serial (COM port) - not supported yet")
        print(" 3  Bluetooth")
        print(" q  quit")
        c = input("> ").strip().lower()
        if c in ("q", ""):
            return False
        if c == "1":
            badges = find_badges()
            if not badges:
                print("no badge on USB - plug one in (switched on) and try again")
                continue
            cmd_list(ns())
            return True
        if c == "2":
            print("Serial needs a firmware fix first: Windows can't open the badge's COM port yet.")
            continue
        if c == "3":
            print(" 1  scan for badges")
            print(" 2  enter address or chip UID")
            how = input("> ").strip()
            try:
                if how == "1":
                    print("scanning 6 s ...")
                    found = ble_scan()
                    if not found:
                        print("nothing found - is the badge on, with Bluetooth always-on or in BT mode?")
                        continue
                    for i, (addr, name, rssi) in enumerate(found):
                        print(f"#{i}  {addr}  {name or '(no name)'}  {rssi} dBm")
                    pick = input("which one? ").strip() or "0"
                    addr = found[int(pick)][0]
                elif how == "2":
                    addr = ble_address(input("address or UID: ").strip())
                else:
                    continue
                SESSION["ble"] = BleBadge(addr, keep=True)
                print("connected - while this menu is open the badge stays connected and is "
                      "invisible to other devices (phone app, other scans)")
                return True
            except SystemExit as e:
                print(e)
            except Exception as e:
                print("could not connect:", e)


def menu_upload():
    path = os.path.join(HERE, "config.toml")
    if not os.path.exists(path):
        print(f"{path} is missing; it comes with the repo (two example messages)")
        return
    cmd_upload(ns(file=path, font="thin"))


def menu_text():
    msgs = [m for m in iter(lambda: input("slot text (empty = done): "), "")][:8]
    if not msgs:
        return
    mode = input(f"mode [{'/'.join(SLOT_MODES)}] (enter = left): ").strip() or "left"
    speed = input("speed 0-7 (enter = 4): ").strip() or "4"
    font = input("font thin/app (enter = thin): ").strip() or "thin"
    cmd_text(ns(messages=msgs, mode=mode, speed=int(speed), font=font,
                blink=input("blink? y/N: ").strip().lower() == "y",
                border=input("border? y/N: ").strip().lower() == "y"))


def menu():
    if not pick_channel():
        return
    try:
        _menu()
    finally:
        if SESSION["ble"] is not None:
            SESSION["ble"].close(force=True)


def _menu():
    items = [
        ("status", lambda: cmd_status(ns())),
        ("battery (live, Ctrl+C to stop)", lambda: cmd_battery(ns(watch=2))),
        ("set clock to PC time", lambda: cmd_time(ns())),
        ("brightness", lambda: cmd_brightness(ns(level=int(ask("level 0-3: ", "0123"))))),
        ("Bluetooth always-on", lambda: cmd_ble(ns(state=ask("on/off: ", ("on", "off"))))),
        ("Bluetooth name", lambda: cmd_name(ns(name=input("new name (max 20): ").strip()))),
        ("startup animation", lambda: cmd_splash(ns(state=ask("on/off: ", ("on", "off"))))),
        ("upload text (replaces all slots)", menu_text),
        ("upload config.toml", menu_upload),
        ("upload image", lambda: cmd_image(ns(file=input("image path: ").strip('" '),
                                              invert=False, preview=False))),
        ("full white test screen", lambda: cmd_stream(ns(what="white"))),
        ("stop streaming", lambda: cmd_stream(ns(what="off"))),
        ("reboot", lambda: cmd_reset(ns())),
        ("power off", lambda: cmd_off(ns())),
        ("flash firmware", lambda: cmd_flash(ns(firmware=ask("build (" + " / ".join(FIRMWARE) + "): ",
                                                            tuple(FIRMWARE))))),
    ]
    while True:
        print()
        if SESSION["ble"] is not None:
            addr = SESSION["ble"].address
            print(f"Bluetooth: {addr}")
        else:
            cmd_list(ns())
        print()
        for i, (label, _) in enumerate(items, 1):
            print(f"{i:2d}  {label}")
        print(" q  quit")
        c = input("> ").strip().lower()
        if c in ("q", "quit", "exit", ""):
            return
        if c.isdigit() and 1 <= int(c) <= len(items):
            try:
                items[int(c) - 1][1]()
            except SystemExit as e:
                print(e)
            except KeyboardInterrupt:
                print()
            except Exception as e:
                print("error:", e)


def ns(**kw):
    kw.setdefault("index", None)
    return argparse.Namespace(**kw)


def ask(prompt, valid):
    while True:
        v = input(prompt).strip().lower()
        if v in valid:
            return v


def main():
    if len(sys.argv) == 1:
        return menu()
    p = argparse.ArgumentParser(description="LED badge tool", epilog=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-i", "--index", type=int, help="badge number from 'list' (USB)")
    p.add_argument("--ble", nargs="?", const="scan", metavar="ADDR_OR_UID",
                   help="use Bluetooth; without a value: scan and pick")
    p.add_argument("--serial", action="store_true", help="USB serial (not supported yet)")
    # the channel options also work after the command ("list --ble")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-i", "--index", type=int, default=argparse.SUPPRESS)
    common.add_argument("--ble", nargs="?", const="scan", default=argparse.SUPPRESS)
    common.add_argument("--serial", action="store_true", default=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)
    _add = sub.add_parser
    sub.add_parser = lambda *a, **kw: _add(*a, parents=[common], **kw)
    sub.add_parser("list").set_defaults(f=cmd_list)
    sub.add_parser("status").set_defaults(f=cmd_status)
    s = sub.add_parser("battery"); s.add_argument("-w", "--watch", type=float); s.set_defaults(f=cmd_battery)
    sub.add_parser("time").set_defaults(f=cmd_time)
    s = sub.add_parser("brightness"); s.add_argument("level", type=int, choices=range(4)); s.set_defaults(f=cmd_brightness)
    s = sub.add_parser("ble"); s.add_argument("state", choices=["on", "off"]); s.set_defaults(f=cmd_ble)
    s = sub.add_parser("name"); s.add_argument("name"); s.set_defaults(f=cmd_name)
    s = sub.add_parser("splash"); s.add_argument("state", choices=["on", "off"]); s.set_defaults(f=cmd_splash)
    s = sub.add_parser("text"); s.add_argument("messages", nargs="+")
    s.add_argument("--mode", default="left",
                   choices=["left", "right", "up", "down", "center", "fast", "drop", "curtain", "laser"])
    s.add_argument("--speed", type=int, default=4, choices=range(8))
    s.add_argument("--blink", action="store_true"); s.add_argument("--border", action="store_true")
    s.add_argument("--preview", action="store_true", help="show the first slot, don't upload")
    s.add_argument("--font", choices=FONTS, default="thin",
                   help="thin = badgemagic.exe font (default), app = phone app 8x11 font")
    s.set_defaults(f=cmd_text)
    s = sub.add_parser("upload"); s.add_argument("file")
    s.add_argument("--font", choices=FONTS, default="thin"); s.set_defaults(f=cmd_upload)
    s = sub.add_parser("image"); s.add_argument("file")
    s.add_argument("--invert", action="store_true", help="light pixels light up (default: dark pixels do)"); s.add_argument("--preview", action="store_true")
    s.set_defaults(f=cmd_image)
    s = sub.add_parser("stream"); s.add_argument("what", help="white | off | image file")
    s.add_argument("--invert", action="store_true", help="light pixels light up (default: dark pixels do)"); s.set_defaults(f=cmd_stream)
    sub.add_parser("reset").set_defaults(f=cmd_reset)
    sub.add_parser("off").set_defaults(f=cmd_off)
    s = sub.add_parser("flash"); s.add_argument("firmware", metavar="normal|pb6|normal-fastble|pb6-fastble|FILE.bin",
                                                help="prebuilt variant from firmware/, or your own build")
    s.set_defaults(f=cmd_flash)
    a = p.parse_args()
    try:
        a.f(a)
    except (RuntimeError, ValueError, OSError, tomllib.TOMLDecodeError) as e:
        sys.exit(f"error: {e}")  # badge problems or bad input: a message, not a traceback


if __name__ == "__main__":
    main()
