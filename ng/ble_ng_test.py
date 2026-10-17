import asyncio, sys
from bleak import BleakClient
from badge_ng import ble_find, CMD_MISC, CMD_STREAM_SET, CMD_STREAM_BM, fb_bytes, COLS

NG_WRITE = "0000f057-0000-1000-8000-00805f9b34fb"

async def main():
    dev = await ble_find(sys.argv[1] if len(sys.argv) > 1 else None, timeout=12.0)
    if not dev:
        print("no badge found"); return
    async with BleakClient(dev, timeout=25.0) as c:
        print("connected, MTU", c.mtu_size)

        async def ng(payload, label):
            try:
                await c.write_gatt_char(NG_WRITE, bytes(payload), response=True)
                print("  OK  ", label)
                return True
            except Exception as e:
                print("  FAIL", label, type(e).__name__, e)
                return False

        await ng([CMD_MISC, 0x01, 1], "brightness -> 1")
        await asyncio.sleep(1.5)
        await ng([CMD_MISC, 0x01, 3], "brightness -> 3")
        await asyncio.sleep(0.5)

        # how much of a frame fits in one BLE write at MTU 64?
        await ng([CMD_STREAM_SET, 0x00], "enter streaming")
        await asyncio.sleep(0.3)
        frame = fb_bytes([0x7FF] * COLS)          # 88 bytes
        for n in (88, 60, 50):
            ok = await ng([CMD_STREAM_BM] + list(frame[:n]), "stream %d bytes" % n)
            if ok:
                print("      -> largest single-write frame chunk: %d bytes" % n)
                await asyncio.sleep(1.2)
                break
        await ng([CMD_STREAM_SET, 0x01], "leave streaming")

asyncio.run(main())
