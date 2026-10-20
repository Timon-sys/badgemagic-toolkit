"""Builds index.html from panel.src.html with the fonts from badgetool.py."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import badgetool

src = open(os.path.join(HERE, "panel.src.html"), encoding="utf-8").read()
out = (src.replace("__APPFONT__", json.dumps(badgetool.APP_FONT, ensure_ascii=False))
          .replace("__LUCAS__", badgetool.LUCASFONT_U8G2.hex()))
open(os.path.join(HERE, "index.html"), "w", encoding="utf-8").write(out)
print("index.html written,", len(out), "bytes")
