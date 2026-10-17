"""Connect to the badge over BLE and report exactly what happens.

Usage:  python ble_check.py [AA:BB:CC:DD:EE:FF]   (default: nearest badge)
"""
import asyncio, sys
from bleak import BleakScanner, BleakClient
from badge_ng import ble_find

LEG  = "0000fee1-0000-1000-8000-00805f9b34fb"

async def main():
    print("scanning 12s...")
    dev = await ble_find(sys.argv[1] if len(sys.argv) > 1 else None, timeout=12.0)
    if dev is None:
        devs = await BleakScanner.discover(timeout=6.0)
        named = [(d.address, d.name) for d in devs if d.name]
        print("NOT ADVERTISING. named devices seen:", named)
        return
    print("found:", dev.address, dev.name)

    try:
        async with BleakClient(dev, timeout=25.0) as c:
            print("CONNECTED:", c.is_connected)
            print("MTU:", getattr(c, "mtu_size", "?"))
            for s in c.services:
                print(" service", s.uuid)
                for ch in s.characteristics:
                    print("    char", ch.uuid, ch.properties)
            # try a legacy-width write to see if it is accepted
            try:
                await c.write_gatt_char(LEG, bytes(16), response=True)
                print("16-byte write to fee1: ACCEPTED")
            except Exception as e:
                print("16-byte write to fee1 FAILED:", type(e).__name__, e)
    except Exception as e:
        print("CONNECT FAILED:", type(e).__name__, e)

asyncio.run(main())
