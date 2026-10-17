import asyncio, sys, time
from bleak import BleakClient
from badge_ng import ble_find, CMD_STREAM_SET, CMD_STREAM_BM, fb_bytes, blank, COLS

NG_WRITE = "0000f057-0000-1000-8000-00805f9b34fb"

async def main():
    dev = await ble_find(sys.argv[1] if len(sys.argv) > 1 else None, timeout=12.0)
    if not dev:
        print("no badge found"); return
    async with BleakClient(dev, timeout=25.0) as c:
        await c.write_gatt_char(NG_WRITE, bytes([CMD_STREAM_SET, 0x00]), response=True)
        await asyncio.sleep(0.3)
        n, t0 = 60, time.time()
        for i in range(n):
            cols = blank()
            cols[i % COLS] = 0x7FF
            cols[(i + 1) % COLS] = 0x7FF
            await c.write_gatt_char(
                NG_WRITE, bytes([CMD_STREAM_BM]) + fb_bytes(cols), response=True)
        dt = time.time() - t0
        print("BLE: %d frames in %.2fs = %.1f fps" % (n, dt, n / dt))
        await asyncio.sleep(0.5)
        await c.write_gatt_char(NG_WRITE, bytes([CMD_STREAM_SET, 0x01]), response=True)

asyncio.run(main())
