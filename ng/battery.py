"""Read the badge's battery over USB.

Usage:  python battery.py          # once
        python battery.py -w 5     # every 5 s until Ctrl+C

Voltage = raw ADC through the badge's 182k/100k divider, so it is only as
accurate as those resistors (~1-2 %). Reads high while the charger is active.
"""
import argparse
import time
from badge_ng import *

ap = argparse.ArgumentParser()
ap.add_argument("-w", "--watch", type=float, metavar="SEC")
a = ap.parse_args()

b = HidBadge()
try:
    while True:
        raw, mv, chg = b.battery()
        print(f"{time.strftime('%H:%M:%S')}  {mv/1000:.3f} V  raw {raw:4d}  "
              f"{'charging' if chg else 'not charging'}")
        if not a.watch:
            break
        time.sleep(a.watch)
except KeyboardInterrupt:
    pass
finally:
    b.close()
