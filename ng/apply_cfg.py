import time
from badge_ng import *

b = HidBadge()
print("loading firmware defaults (splash off, BLE always-on)...")
b.load_defaults(); time.sleep(0.4)

# be explicit rather than relying on the compiled-in defaults
b.splash_speed(0);       time.sleep(0.2)   # 0 = no startup animation
b.ble_always_on(True);   time.sleep(0.2)

print("saving to EEPROM...")
b.save_cfg(); time.sleep(0.8)
b.close()
print("done")
