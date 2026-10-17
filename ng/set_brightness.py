import sys, time
from badge_ng import *

lvl = int(sys.argv[1]) if len(sys.argv) > 1 else 3
assert 0 <= lvl <= 3, "brightness is 0-3"

b = HidBadge()
b.brightness(lvl); time.sleep(0.3)
b.save_cfg();      time.sleep(0.8)
b.close()
pct = [25, 50, 75, 100][lvl]
print("brightness set to %d (~%d%% duty) and saved" % (lvl, pct))
