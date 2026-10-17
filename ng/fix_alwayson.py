import time
from badge_ng import *

b = HidBadge()
print("setting ble_always_on = 1 ...")
b.ble_always_on(True); time.sleep(0.3)
print("saving to EEPROM ...")
b.save_cfg(); time.sleep(1.0)
print("rebooting badge (power_setting fn=2 -> SYS_ResetExecute) ...")
b.send(bytes([CMD_POWER, 2]))
try:
    b.close()
except Exception:
    pass
print("sent")
