"""Set the badge clock to the PC's local time over USB.

Usage:  python set_time.py

The clock survives power off/on with the button (shutdown wake), but a
software reset (ng reset command, flashing) clears it, as does a flat battery.
ble_always_on.py re-sets it after its reboot.
"""
import datetime
import time
from badge_ng import *

b = HidBadge()
# wait for the next full second so the badge isn't up to a second behind
now = datetime.datetime.now()
time.sleep(1 - now.microsecond / 1e6)
now = datetime.datetime.now().replace(microsecond=0)
b.set_time(now)
b.close()
print("badge clock set to", now.strftime("%Y-%m-%d %H:%M:%S"))
