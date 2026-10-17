"""Measure BLE streaming speed, frame by frame.

Usage:  python ble_fps.py [AA:BB:CC:DD:EE:FF] [--frames N] [--no-response] [--rate FPS] [--csv out.csv]

Sends N frames of a sweeping bar over the ng characteristic. The badge answers
every ng command with a 1-byte notification on f056, so the script times when
each frame actually arrived on the badge, and counts frames that never did.

  default        write with response: each write waits for the badge's ack
  --no-response  write without response (firmware with WRITE_NO_RSP on f057);
                 the PC queues frames, the notifications show the real pace
  --rate FPS     send at most FPS frames per second instead of back to back
  --no-notify    don't subscribe to the confirmations (times are PC side only)
"""
import argparse, asyncio, statistics, time
from bleak import BleakClient
from badge_ng import ble_find, CMD_STREAM_SET, CMD_STREAM_BM, fb_bytes, blank, COLS

NG_WRITE = "0000f057-0000-1000-8000-00805f9b34fb"
NG_NOTIFY = "0000f056-0000-1000-8000-00805f9b34fb"


def report(label, gaps):
    ms = [g * 1000 for g in gaps]
    if not ms:
        print(label, "no data"); return
    print("%s: min %.0f  median %.0f  mean %.0f  max %.0f  stdev %.0f ms"
          % (label, min(ms), statistics.median(ms), statistics.mean(ms), max(ms), statistics.pstdev(ms)))
    k = max(1, len(ms) // 6)
    print("  first %d: mean %.0f ms   last %d: mean %.0f ms"
          % (k, statistics.mean(ms[:k]), k, statistics.mean(ms[-k:])))
    for i in range(0, len(ms), 10):
        print("  %3d: " % i + " ".join("%4.0f" % m for m in ms[i:i + 10]))


async def main(a):
    dev = await ble_find(a.address, timeout=12.0)
    if not dev:
        print("no badge found"); return
    async with BleakClient(dev, timeout=25.0) as c:
        arrivals = []
        if not a.no_notify:
            await c.start_notify(NG_NOTIFY, lambda _h, _d: arrivals.append(time.perf_counter()))
        print("connected, MTU", c.mtu_size, "| response:", not a.no_response,
              "| rate:", a.rate or "max")
        if a.no_response and "write-without-response" not in c.services.get_characteristic(NG_WRITE).properties:
            print("this firmware doesn't accept writes without response on f057 (use a fastble build)")
            return
        await c.write_gatt_char(NG_WRITE, bytes([CMD_STREAM_SET, 0x00]), response=True)
        await asyncio.sleep(2.0)  # the badge asks for a faster interval 1 s after connecting
        arrivals.clear()

        t_start = time.perf_counter()
        for i in range(a.frames):
            if a.rate:
                await asyncio.sleep(max(0, t_start + i / a.rate - time.perf_counter()))
            cols = blank()
            cols[i % COLS] = 0x7FF
            cols[(i + 1) % COLS] = 0x7FF
            await c.write_gatt_char(NG_WRITE, bytes([CMD_STREAM_BM]) + fb_bytes(cols),
                                    response=not a.no_response)
        sent = time.perf_counter() - t_start
        if a.no_notify:
            print("sent %d frames in %.2f s = %.1f fps (no notifications: PC side only)"
                  % (a.frames, sent, a.frames / sent))
            await c.write_gatt_char(NG_WRITE, bytes([CMD_STREAM_SET, 0x01]), response=True)
            return
        # wait until the badge has gone quiet
        n = -1
        while n != len(arrivals):
            n = len(arrivals)
            await asyncio.sleep(1.0)

        got = len(arrivals)
        total = (arrivals[-1] - t_start) if arrivals else 0
        print("sent %d frames in %.2f s; badge confirmed %d (%d lost)" % (a.frames, sent, got, a.frames - got))
        if got > 1:
            print("on the badge: %d frames in %.2f s = %.1f fps" % (got, total, got / total))
            report("time between frames on the badge", [b - x for x, b in zip(arrivals, arrivals[1:])])
        if a.csv:
            with open(a.csv, "w") as f:
                f.write("frame,arrival_ms\n" + "".join(
                    "%d,%.2f\n" % (i, (t - t_start) * 1000) for i, t in enumerate(arrivals)))
        await c.write_gatt_char(NG_WRITE, bytes([CMD_STREAM_SET, 0x01]), response=True)


ap = argparse.ArgumentParser()
ap.add_argument("address", nargs="?")
ap.add_argument("--frames", type=int, default=120)
ap.add_argument("--no-response", action="store_true")
ap.add_argument("--rate", type=float)
ap.add_argument("--no-notify", action="store_true", help="don't ask the badge to confirm frames")
ap.add_argument("--csv")
asyncio.run(main(ap.parse_args()))
