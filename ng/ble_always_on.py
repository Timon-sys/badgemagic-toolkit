"""Turn the badge's always-on BLE advertising on or off (USB, custom firmware).

Usage:  python ble_always_on.py on|off

Saves to EEPROM and reboots the badge, since the setting is only read at boot.
"""
import sys
import time
from badge_ng import *

if len(sys.argv) != 2 or sys.argv[1] not in ("on", "off"):
    sys.exit(__doc__)
on = sys.argv[1] == "on"

b = HidBadge()
b.ble_always_on(on);  time.sleep(0.3)
b.save_cfg();         time.sleep(1.0)
b.send(bytes([CMD_POWER, 2]))   # power_setting fn=2 -> SYS_ResetExecute
try:
    b.close()
except Exception:
    pass
print("ble_always_on =", int(on), "saved, badge rebooting")

# a software reset clears the RTC, so put the time back once it re-enumerates
import datetime, hid
time.sleep(3)   # let the old USB instance go away first
for _ in range(30):
    time.sleep(1)
    if any(d["manufacturer_string"] == "FOSSASIA WAS HERE" for d in hid.enumerate(0x0416, 0x5020)):
        time.sleep(1)
        b = HidBadge()
        now = datetime.datetime.now().replace(microsecond=0)
        b.set_time(now)
        b.close()
        print("clock restored to", now.strftime("%H:%M:%S"))
        break
else:
    print("badge did not come back within 30 s; run set_time.py")
