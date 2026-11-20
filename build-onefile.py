#!/usr/bin/env python3
"""Bundle xutil.py + the whole tabs/ folder into ONE self-contained file.
Usage: python3 build-onefile.py [output.py]   (default: dist/xutil.py)"""
import base64, json, sys, zlib
from pathlib import Path

here = Path(__file__).resolve().parent
files = {p.relative_to(here).as_posix(): p.read_text(encoding="utf-8")
         for p in sorted((here / "tabs").rglob("*")) if p.is_file() and "__pycache__" not in p.parts}
files["xutil_icons.py"] = (here / "xutil_icons.py").read_text(encoding="utf-8")  # window icons, imported from the unpack dir
blob = base64.b64encode(zlib.compress(json.dumps(files).encode(), 9)).decode()
lines = [blob[i:i + 100] for i in range(0, len(blob), 100)]
literal = "(\n" + "\n".join(f'    "{ln}"' for ln in lines) + "\n)"
src = (here / "xutil.py").read_text(encoding="utf-8")
assert "EMBEDDED = None" in src, "placeholder missing"
out = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "dist" / "xutil.py"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(src.replace("EMBEDDED = None", "EMBEDDED = " + literal, 1), encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(files)} embedded files)")
