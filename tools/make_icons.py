#!/usr/bin/env python3
"""Build xutil_icons.py: brand + glyph icons as base64 PNGs (needs rsvg-convert; run only when icons change).

Brand logos come from the `simple-icons` npm package (CC0). Glyphs are hand-written 24x24 outline icons.
Usage: python3 tools/make_icons.py <simple-icons-new-dir> <simple-icons-old-dir>
"""
import base64, colorsys, json, re, subprocess, sys
from pathlib import Path

NEW, OLD = Path(sys.argv[1]), Path(sys.argv[2])
OUT = Path(__file__).resolve().parent.parent / "xutil_icons.py"
SIZE = 64  # rendered px; shown at 28-32px with subsample, or 56 on the detail panel

# key -> (simple-icons slug, hex colour or None to use the brand colour)
BRANDS = {
    "git": ("git", None), "neovim": ("neovim", None), "python": ("python", "3776AB"),
    "nodejs": ("nodedotjs", None), "java": ("openjdk", "ED8B00"), "vscode": ("visualstudiocode", None),
    "zed": ("zedindustries", "0DC8FF"), "github": ("github", "F0F6FC"), "gitlab": ("gitlab", None),
    "docker": ("docker", None), "firefox": ("firefox", None), "chromium": ("googlechrome", "4285F4"),
    "brave": ("brave", None), "discord": ("discord", None), "telegram": ("telegram", None),
    "libreoffice": ("libreoffice", None), "gimp": ("gimp", "C9B99A"), "inkscape": ("inkscape", "E6E6E6"),
    "blender": ("blender", None), "krita": ("krita", None), "obs": ("obsstudio", "E8E8E8"),
    "audacity": ("audacity", None), "kdenlive": ("kdenlive", None), "thunderbird": ("thunderbird", None),
    "keepassxc": ("keepassxc", None), "qbittorrent": ("qbittorrent", None), "curl": ("curl", "E8E8E8"),
    "7zip": ("7zip", "E8E8E8"), "vlc": ("vlcmediaplayer", "FF8800"), "bash": ("gnubash", "4EAA25"),
    "winterminal": ("windowsterminal", "4D9BE6"),
    "steam": ("steam", "66C0F4"), "whatsapp": ("whatsapp", "25D366"), "dotnet": ("dotnet", "8B6FE8"), "rider": ("rider", "E8466D"),
    "visualstudio": ("visualstudio", "9B7BEA"), "word": ("microsoftword", "4C8BE0"),
    "linux": ("linux", "FCC624"), "windows": ("windows", "0A9DFF"), "apple": ("apple", "E8E8E8"),
}

def g(body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#{c}" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + body + "</svg>")

GLYPHS = {  # key -> (svg body, colour)
    "code": ('<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>', "7AA2F7"),
    "globe": ('<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>', "7DCFFF"),
    "chat": ('<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>', "BB9AF7"),
    "package": ('<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><polyline points="3.3 7 12 12 20.7 7"/><line x1="12" y1="22" x2="12" y2="12"/>', "E0AF68"),
    "wrench": ('<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>', "9ECE6A"),
    "grid": ('<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>', "7AA2F7"),
    "cpu": ('<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>', "9ECE6A"),
    "shield": ('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>', "F7768E"),
    "shieldcheck": ('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>', "9ECE6A"),
    "terminal": ('<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>', "E0AF68"),
    "refresh": ('<path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><polyline points="3 3 3 8 8 8"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><polyline points="16 16 21 16 21 21"/>', "7AA2F7"),
    "trash": ('<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>', "F7768E"),
    "info": ('<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>', "7DCFFF"),
    "disk": ('<line x1="22" y1="12" x2="2" y2="12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><line x1="6" y1="16" x2="6.01" y2="16"/><line x1="10" y1="16" x2="10.01" y2="16"/>', "BB9AF7"),
    "server": ('<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>', "7AA2F7"),
    "activity": ('<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>', "9ECE6A"),
    "image": ('<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>', "FF9E64"),
    "film": ('<rect x="2" y="2" width="20" height="20" rx="2.2"/><path d="M7 2v20M17 2v20M2 12h20M2 7h5M2 17h5M17 17h5M17 7h5"/>', "F7768E"),
    "chart": ('<line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/>', "9ECE6A"),
    "history": ('<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><polyline points="3 3 3 8 8 8"/><polyline points="12 7 12 12 15 14"/>', "7DCFFF"),
    "layers": ('<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>', "7AA2F7"),
    "folder": ('<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>', "E0AF68"),
    "flame": ('<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>', "FF9E64"),
    "scan": ('<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><line x1="7" y1="12" x2="17" y2="12"/>', "F7768E"),
    "dns": ('<circle cx="12" cy="12" r="10"/><path d="M8 12h8M12 8v8"/>', "7DCFFF"),
    "box": ('<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/>', "7AA2F7"),
    "download": ('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>', "7AA2F7"),
    "palette": ('<circle cx="13.5" cy="6.5" r="1"/><circle cx="17.5" cy="10.5" r="1"/><circle cx="8.5" cy="7.5" r="1"/><circle cx="6.5" cy="12.5" r="1"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.93 0 1.5-.67 1.5-1.5 0-.4-.15-.77-.4-1.04-.23-.27-.35-.61-.35-.96 0-.83.67-1.5 1.5-1.5H16c3.3 0 6-2.7 6-6 0-4.97-4.5-9-10-9z"/>', "BB9AF7"),
    "play": ('<polygon points="6 3 20 12 6 21 6 3"/>', "9ECE6A"),
    "x": ('<path d="M18 6L6 18M6 6l12 12"/>', "F7768E"),
    "search": ('<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>', "7AA2F7"),
    "playdark": ('<polygon points="6 3 20 12 6 21 6 3"/>', "1A1B26"),
    "doc": ('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/>', "7AA2F7"),
    "gamepad": ('<line x1="6" y1="11" x2="10" y2="11"/><line x1="8" y1="9" x2="8" y2="13"/><line x1="15" y1="12" x2="15.01" y2="12"/><line x1="18" y1="10" x2="18.01" y2="10"/><path d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258-.007-.05-.011-.1-.017-.151A4 4 0 0 0 17.32 5z"/>', "BB9AF7"),
    "check": ('<polyline points="20 6 9 17 4 12"/>', "9ECE6A"),
}

def lift(hexc, min_l=0.62):
    """Brand colours that are too dark vanish on a dark tile: raise lightness, keep hue."""
    r, g_, b = (int(hexc[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g_, b)
    if l < min_l:
        l = min_l
    r, g_, b = colorsys.hls_to_rgb(h, l, s)
    return "%02X%02X%02X" % (round(r * 255), round(g_ * 255), round(b * 255))

def hex_of(slug):
    for root in (NEW, OLD):
        for p in (root / "_data" / "simple-icons.json",):
            if p.exists():
                data = json.loads(p.read_text())
                data = data["icons"] if isinstance(data, dict) else data
                for it in data:
                    if it.get("slug") == slug or re.sub(r"\W", "", it["title"].lower()) == slug:
                        return it["hex"]
    return "AAAAAA"

SIZES = (64, 32, 22)  # detail panel, cards, sidebar/headers; pre-rendered so Tk never has to resample

def render(svg, size=SIZE):
    return subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size)], input=svg.encode(), capture_output=True, check=True).stdout

LOGO = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#1a1b26"/>'
        '<rect x="2" y="2" width="60" height="60" rx="12" fill="none" stroke="#7aa2f7" stroke-width="2.5"/>'
        '<polyline points="18,20 32,32 18,44" fill="none" stroke="#7aa2f7" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
        '<line x1="36" y1="46" x2="48" y2="46" stroke="#9ece6a" stroke-width="5" stroke-linecap="round"/></svg>')

icons, missing = {}, []
for key, (slug, colour) in BRANDS.items():
    f = next((r / "icons" / f"{slug}.svg" for r in (NEW, OLD) if (r / "icons" / f"{slug}.svg").exists()), None)
    if not f:
        missing.append(key); continue
    c = colour or lift(hex_of(slug))
    svg = f.read_text().replace("<svg ", f'<svg fill="#{c}" ', 1)
    for sz in SIZES:
        icons[key if sz == 64 else f"{key}.{sz}"] = base64.b64encode(render(svg, sz)).decode()
for key in ("linux", "windows", "apple"):                 # 16px platform badges: lit and dimmed
    f = next(r / "icons" / f"{BRANDS[key][0]}.svg" for r in (NEW, OLD) if (r / "icons" / f"{BRANDS[key][0]}.svg").exists())
    for tag, col in (("", BRANDS[key][1]), ("d", "555B75")):
        icons[f"{key}.{tag}16"] = base64.b64encode(render(f.read_text().replace("<svg ", f'<svg fill="#{col}" ', 1), 16)).decode()
for key, (body, colour) in GLYPHS.items():
    svg = g(body).replace("{c}", colour)
    for sz in SIZES:
        icons[key if sz == 64 else f"{key}.{sz}"] = base64.b64encode(render(svg, sz)).decode()
for sz in (64, 32):
    icons["logo" if sz == 64 else f"logo.{sz}"] = base64.b64encode(render(LOGO, sz)).decode()
(OUT.parent / "assets").mkdir(exist_ok=True)
(OUT.parent / "assets" / "xutil.png").write_bytes(render(LOGO, 256))
(OUT.parent / "assets" / "xutil.svg").write_text(LOGO)

lines = ['"""Generated by tools/make_icons.py - do not edit. Brand logos: simple-icons (CC0). Glyphs: original."""', "ICONS = {"]
lines += [f'    "{k}": (\n' + "\n".join(f'        "{v[i:i+96]}"' for i in range(0, len(v), 96)) + "\n    )," for k, v in sorted(icons.items())]
lines.append("}")
OUT.write_text("\n".join(lines) + "\n")
print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(icons)} icons); missing: {missing}")
