#!/usr/bin/env python3
"""xutil - cross-platform apps and system setup (Windows, Linux, macOS).

A stdlib-only implementation:
  core : tabs.toml + tab_data.toml catalog, preconditions, interpreter resolution, config
  tui  : tabs, folders, search, preview, multi-select, confirmation, execution
Needs Python 3.11+ (tomllib); the window also needs tkinter.
"""
import argparse
import atexit
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover
    sys.exit("xutil needs Python 3.11+ (tomllib).\n  Windows: winget install Python.Python.3.12\n  Linux:   use your package manager's python3 (3.11 or newer)")

HERE = Path(__file__).resolve().parent
EMBEDDED = None  # filled in by build-onefile.py: base64(zlib(json({relative path: text})))


def extract_embedded():
    """Unpack the embedded tabs/ tree to a temp dir."""
    import atexit
    import base64
    import json
    import tempfile
    import zlib
    files = json.loads(zlib.decompress(base64.b64decode(EMBEDDED)))
    tmp = tempfile.mkdtemp(prefix="xutil_")
    atexit.register(shutil.rmtree, tmp, True)
    for rel, text in files.items():
        p = Path(tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    return Path(tmp) / "tabs"
WINDOWS = os.name == "nt"
OS_NAME = platform.system().lower()  # linux | windows | darwin

TASK_FLAGS = {
    "D": "Disk modification", "FI": "Flatpak installation", "FM": "File modification",
    "I": "Privileged installation", "K": "Kernel modification", "MP": "Package manager action",
    "RP": "Package removal", "SI": "Full system installation", "SS": "Service action",
    "A": "Needs Administrator (Windows)", "R": "Reboot likely required", "REG": "Registry modification",
    "WF": "Windows feature change", "WG": "winget/choco/scoop action", "FW": "Firewall / Defender change",
}


def describe_flags(task_list):
    out = []
    for tok in task_list.split():
        if tok in TASK_FLAGS:
            out.append(f"{tok}: {TASK_FLAGS[tok]}")
        elif tok.startswith("P"):
            rest = tok[1:]
            out.append(f"{tok}: Requires privileges" + (f" + {TASK_FLAGS[rest]}" if rest in TASK_FLAGS else ""))
    return out


# ═════════════════════════════ core: data model ═════════════════════════════

class Node:
    def __init__(self, name, desc="", kind="dir", multi=True, task_list="", argv=None, path=None, cwd=None, raw=None):
        self.name, self.desc, self.kind = name, desc, kind  # kind: dir | raw | script
        self.multi, self.task_list = multi, task_list
        self.argv, self.path, self.cwd, self.raw = argv, path, cwd, raw
        self.children = []
        self.os_tags = None      # operating systems this entry targets (None = all)
        self.usable = True       # runnable on THIS system (interpreter present, preconditions pass)
        self.platforms = None    # GUI: set of OSes the app exists for
        self.base, self.how = None, {}   # GUI: description without per-OS notes, and the per-OS install notes

    def leaves(self):
        for c in self.children:
            if c.kind == "dir":
                yield from c.leaves()
            else:
                yield c

    def preview(self):
        if self.kind == "script":
            try:
                return self.path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                return f"(cannot read script: {e})"
        return self.raw or ""

    def needs_admin(self):
        return "A" in self.task_list.split()


def which(cmd):
    return shutil.which(cmd) is not None


def precondition_ok(p):
    matches, data, values = p["matches"], p["data"], p["values"]
    if data == "command_exists":
        return all(which(v) == matches for v in values)
    if data == "file_exists":
        return all(Path(os.path.expandvars(v)).is_file() == matches for v in values)
    if data == "os":  # platform filter
        return (OS_NAME in values) == matches
    if isinstance(data, dict) and "environment" in data:
        v = os.environ.get(data["environment"])
        return v is not None and ((v in values) == matches)
    if isinstance(data, dict) and "containing_file" in data:
        try:
            text = Path(os.path.expandvars(data["containing_file"])).read_text(errors="replace")
        except OSError:
            return False
        return all((m in text) == matches for m in values)
    raise ValueError(f"unknown precondition data: {data!r}")


def os_tags_of(entry):
    """OSes an entry is restricted to by its `os` preconditions (empty set = no restriction)."""
    tags = set()
    for p in entry.get("preconditions", []):
        if p.get("data") == "os" and p.get("matches", True):
            tags |= set(p["values"])
    return tags


def supported(entry):
    return all(precondition_ok(p) for p in entry.get("preconditions", []))


def resolve_script(path: Path):
    """Interpreter lookup from the shebang. Returns argv prefix or None if unavailable."""
    ext = path.suffix.lower()
    if ext == ".ps1":
        ps = shutil.which("pwsh") or shutil.which("powershell")
        return [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)] if ps else None
    if ext == ".py":
        return [sys.executable, str(path)]
    if ext in (".cmd", ".bat"):
        return ["cmd", "/c", str(path)] if WINDOWS else None
    try:
        first = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        first = ""
    if first.startswith("#!"):
        parts = shlex.split(first[2:].strip())
        exe = shutil.which(parts[0]) or shutil.which(os.path.basename(parts[0]))
        return [exe, *parts[1:], str(path)] if exe else None
    sh = shutil.which("sh")
    return [sh, "-e", str(path)] if sh else None


def raw_argv(command):
    if WINDOWS:
        ps = shutil.which("pwsh") or shutil.which("powershell")
        return [ps, "-NoProfile", "-Command", command] if ps else None
    sh = shutil.which("sh")
    return [sh, "-c", command] if sh else None


def build_dir(entries, tab_dir, validate, parent_multi=True):
    out = []
    for e in entries:
        if validate and not supported(e):
            continue
        multi = parent_multi and e.get("multi_select", True)
        kinds = [k for k in ("entries", "script", "command") if k in e]
        if len(kinds) != 1:
            raise SystemExit(f"Entry '{e.get('name')}' must define exactly one of entries/script/command")
        if "entries" in e:
            node = Node(e["name"], e.get("description", ""), "dir", multi)
            node.children = build_dir(e["entries"], tab_dir, validate, multi)
            if validate and not node.children:
                continue
            out.append(node)
        elif "script" in e:
            path = (tab_dir / e["script"]).resolve()
            if not path.exists():
                raise SystemExit(f"Script {path} does not exist")
            prefix = resolve_script(path)
            if prefix is None and validate:
                continue  # interpreter unavailable -> hidden
            argv = (prefix + [str(a) for a in e.get("args", [])]) if prefix else None
            node = Node(e["name"], e.get("description", ""), "script", multi, e.get("task_list", ""), argv, path, path.parent)
            node.os_tags, node.usable = os_tags_of(e) or None, supported(e) and prefix is not None
            out.append(node)
        else:
            argv = raw_argv(e["command"])
            if argv is None and validate:
                continue
            node = Node(e["name"], e.get("description", ""), "raw", multi, e.get("task_list", ""), argv, None, None, e["command"])
            node.os_tags, node.usable = os_tags_of(e) or None, supported(e) and argv is not None
            out.append(node)
    return out


def load_tabs(tabs_dir: Path, validate=True):
    index = tomllib.loads((tabs_dir / "tabs.toml").read_text(encoding="utf-8"))
    tabs = []
    for d in index["directories"]:
        data = tomllib.loads((tabs_dir / d / "tab_data.toml").read_text(encoding="utf-8"))
        root = Node(data["name"])
        root.children = build_dir(data["data"], tabs_dir / d, validate)
        if root.children or not validate:
            tabs.append(root)
    if not tabs:
        raise SystemExit("No tabs available for this system")
    return tabs


def find_by_name(tabs, name):
    return next((n for t in tabs for n in t.leaves() if n.name == name), None)


ALLOWED_CONFIG = {"auto_execute", "skip_confirmation", "size_bypass"}


def read_config(path, tabs):
    p = Path(path)
    try:
        cfg = tomllib.loads(p.read_text(encoding="utf-8")) if p.suffix != ".json" else __import__("json").loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        sys.exit(f"Failed to read config {p}: {e}")
    unknown = set(cfg) - ALLOWED_CONFIG
    if unknown:
        sys.exit(f"Unknown config fields: {', '.join(sorted(unknown))}")
    nodes, missing = [], []
    for n in cfg.get("auto_execute", []):
        node = find_by_name(tabs, n)
        (nodes if node else missing).append(node or n)
    for m in missing:  # report names that are not available on this system
        print(f"! '{m}' not found or unsupported on this system; skipped")
    return nodes, bool(cfg.get("skip_confirmation")), bool(cfg.get("size_bypass"))


def is_admin():
    try:
        if WINDOWS:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except Exception:
        return False


# ═════════════════════════════ execution ═════════════════════════════

def confirm_and_run(nodes, skip_confirmation, dry_run):
    admin = is_admin()
    runnable, blocked = [], []
    for n in nodes:
        (blocked if (WINDOWS and n.needs_admin() and not admin) else runnable).append(n)
    print("\n\033[1mCommands to run (in order):\033[0m")
    for i, n in enumerate(nodes, 1):
        tag = "  \033[31m[needs Administrator - will be skipped]\033[0m" if n in blocked else ""
        print(f" {i}. {n.name}{tag}")
        shown = n.raw if n.kind == "raw" else f"{n.path.name} {' '.join(map(str, n.argv[len(resolve_script(n.path) or []):] if n.argv else []))}".strip()
        print(f"      $ {shown}")
        for line in describe_flags(n.task_list):
            print(f"      - {line}")
    if blocked:
        print("\n\033[33mRe-open your terminal as Administrator to run the skipped tasks.\033[0m")
    if not runnable:
        return pause()
    if not skip_confirmation and not dry_run:
        if input("\nProceed? [y/N] ").strip().lower() != "y":
            print("Cancelled.")
            return pause()
    results = []
    for n in runnable:
        print(f"\n\033[1;36m▶ {n.name}\033[0m")
        if dry_run:
            print("  (dry run)", " ".join(shlex.quote(a) for a in n.argv))
            results.append((n.name, 0))
            continue
        try:
            rc = subprocess.call(n.argv, cwd=n.cwd)
        except KeyboardInterrupt:
            rc = 130
        except OSError as e:
            print(f"  cannot start: {e}")
            rc = 127
        results.append((n.name, rc))
        if rc != 0:
            print(f"\033[31m✗ {n.name} failed (exit {rc}); stopping the queue.\033[0m")
            break
    print("\n\033[1mSummary\033[0m")
    for name, rc in results:
        print(f"  {'✓' if rc == 0 else '✗'} {name}")
    skipped = [n.name for n in runnable[len(results):]]
    for name in skipped:
        print(f"  - {name} (not run)")
    return pause(any(rc for _, rc in results))


def pause(failed=False):
    if sys.stdin.isatty():
        input("\nPress Enter to return…")
    return not failed


# ═════════════════════════════ tui ═════════════════════════════

def enable_ansi():
    if WINDOWS:
        os.system("")  # turns on VT processing in the Windows console
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


if WINDOWS:
    import msvcrt

    def raw_on():
        pass

    def raw_off():
        pass

    def get_key():
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return {"H": "up", "P": "down", "K": "left", "M": "right", "\x0f": "btab",
                    "I": "pgup", "Q": "pgdn"}.get(msvcrt.getwch(), "")
        return {"\r": "enter", " ": "space", "\t": "tab", "\x1b": "esc", "\x08": "backspace", "\x03": "ctrl-c"}.get(ch, ch)
else:
    import select
    import termios
    import tty

    _saved = []

    def raw_on():
        """cbreak once for the whole TUI session (keeps output post-processing and Ctrl-C)."""
        if not _saved:
            fd = sys.stdin.fileno()
            _saved.append(termios.tcgetattr(fd))
            tty.setcbreak(fd)

    def raw_off():
        if _saved:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _saved.pop())

    def get_key():
        fd = sys.stdin.fileno()
        ch = os.read(fd, 1).decode("utf-8", "ignore")
        if ch == "\x1b":
            if select.select([fd], [], [], 0.05)[0]:
                seq = os.read(fd, 8).decode("utf-8", "ignore")
                return {"[A": "up", "[B": "down", "[C": "right", "[D": "left", "[Z": "btab",
                        "[5~": "pgup", "[6~": "pgdn"}.get(seq, "")
            return "esc"
        return {"\r": "enter", "\n": "enter", " ": "space", "\t": "tab", "\x7f": "backspace", "\x03": "ctrl-c"}.get(ch, ch)


class Theme:
    def __init__(self, compatible):
        self.dir, self.cur = ("[+]", ">") if compatible else ("▸", "▶")
        self.on, self.off = ("[x]", "[ ]") if compatible else ("◉", "○")
        self.rule = "-" if compatible else "─"


class App:
    def __init__(self, tabs, args, size_bypass, skip_confirmation):
        self.tabs, self.args = tabs, args
        self.theme = Theme(args.theme == "compatible")
        self.size_bypass, self.skip = size_bypass, skip_confirmation
        self.tab = 0
        self.stacks = [[(t, 0)] for t in tabs]  # per tab: [(dir node, cursor)]
        self.selected = []
        self.query = ""

    # ----- navigation helpers
    def cur_dir(self):
        return self.stacks[self.tab][-1][0]

    def items(self):
        if self.query:
            q = self.query.lower()
            return [n for n in self.tabs[self.tab].leaves() if q in n.name.lower() or q in n.desc.lower()]
        return self.cur_dir().children

    def cursor(self):
        return self.stacks[self.tab][-1][1]

    def set_cursor(self, v):
        n = len(self.items())
        node, _ = self.stacks[self.tab][-1]
        self.stacks[self.tab][-1] = (node, max(0, min(v, n - 1)) if n else 0)

    def current(self):
        it = self.items()
        return it[self.cursor()] if it else None

    # ----- drawing
    def draw(self):
        cols, rows = shutil.get_terminal_size((100, 30))
        t, out = self.theme, []
        tabline = "  ".join((f"\033[7m {x.name} \033[0m" if i == self.tab else f" {x.name} ") for i, x in enumerate(self.tabs))
        out.append(f"\033[1mxutil\033[0m {OS_NAME}{' (admin)' if is_admin() else ''}  │ {tabline}")
        path = " / ".join(n.name for n, _ in self.stacks[self.tab][1:])
        out.append(f"\033[2m{('/' + path) if path else '/'}{'   search: ' + self.query if self.query else ''}\033[0m")
        out.append(t.rule * cols)
        list_h = max(3, rows - 12)
        items, cur = self.items(), self.cursor()
        top = max(0, min(cur - list_h // 2, max(0, len(items) - list_h)))
        for i in range(top, min(len(items), top + list_h)):
            n = items[i]
            mark = (t.on if n in self.selected else t.off) + " " if n.kind != "dir" and n.multi else ("  " if n.kind != "dir" else "")
            icon = f"{t.dir} " if n.kind == "dir" else ""
            line = f"{icon}{mark}{n.name}{'/' if n.kind == 'dir' else ''}"
            pointer = f"\033[1;36m{t.cur}\033[0m " if i == cur else "  "
            out.append(pointer + (f"\033[1m{line}\033[0m" if i == cur else line))
        out += [""] * (list_h - min(len(items) - top, list_h))
        out.append(t.rule * cols)
        n = self.current()
        if n:
            for ln in textwrap.wrap(n.desc.replace("\\n", " "), cols - 2)[:3]:
                out.append(ln)
            fl = describe_flags(n.task_list)
            if fl:
                out.append("\033[33m" + "; ".join(fl)[: cols - 2] + "\033[0m")
        if self.selected:
            out.append(f"\033[32mSelected ({len(self.selected)}): {', '.join(x.name for x in self.selected)}\033[0m"[: cols + 12])
        keys = "↑↓ move  ←/→ back/open  Tab tab  Space select  Enter run/open  r run selected  p preview  / search  g flags  t theme  q quit"
        if self.theme.rule == "-":
            keys = "Up/Down move  Left/Right back/open  Tab tab  Space select  Enter run/open  r run  p preview  / search  g flags  t theme  q quit"
        sys.stdout.write("\033[H\033[2J" + "\n".join(out[: rows - 2]) + f"\033[{rows};1H\033[2m{keys[:cols - 1]}\033[0m")
        sys.stdout.flush()

    def viewer(self, title, text):
        cols, rows = shutil.get_terminal_size((100, 30))
        lines = [ln for raw in text.splitlines() or [""] for ln in (textwrap.wrap(raw, cols - 2, replace_whitespace=False) or [""])]
        top = 0
        while True:
            body = lines[top: top + rows - 3]
            sys.stdout.write("\033[H\033[2J\033[1m" + title + "\033[0m\n" + "\n".join(body) +
                             f"\033[{rows};1H\033[2m↑↓ scroll  q/Esc close   ({top + 1}/{len(lines)})\033[0m")
            sys.stdout.flush()
            k = get_key()
            if k in ("q", "esc", "enter", "ctrl-c"):
                return
            top = max(0, min(top + {"up": -1, "k": -1, "down": 1, "j": 1, "pgup": -10, "pgdn": 10}.get(k, 0), max(0, len(lines) - (rows - 3))))

    def search(self):
        self.query = ""
        while True:
            self.set_cursor(0)
            self.draw()
            sys.stdout.write(f"\033[{shutil.get_terminal_size((100, 30))[1] - 1};1H\033[1m/ {self.query}\033[0m\033[K")
            sys.stdout.flush()
            k = get_key()
            if k == "enter":
                return
            if k in ("esc", "ctrl-c"):
                self.query = ""
                return
            if k == "backspace":
                self.query = self.query[:-1]
            elif len(k) == 1 and k.isprintable():
                self.query += k

    # ----- actions
    def run(self, nodes):
        sys.stdout.write("\033[?25h\033[H\033[2J")
        sys.stdout.flush()
        raw_off()
        try:
            confirm_and_run(nodes, self.skip, self.args.dry_run)
        finally:
            raw_on()
            sys.stdout.write("\033[?25l")
        self.selected.clear()

    def enter(self):
        n = self.current()
        if not n:
            return
        if n.kind == "dir":
            self.stacks[self.tab].append((n, 0))
        else:
            self.run(self.selected if self.selected else [n])

    def back(self):
        if self.query:
            self.query = ""
        elif len(self.stacks[self.tab]) > 1:
            self.stacks[self.tab].pop()

    def loop(self):
        cols, rows = shutil.get_terminal_size((100, 30))
        if not self.size_bypass and (cols < 60 or rows < 18):
            sys.exit(f"Terminal too small ({cols}x{rows}); need 60x18. Use --size-bypass to ignore.")
        sys.stdout.write("\033[?1049h\033[?25l")
        raw_on()
        try:
            while True:
                self.draw()
                k = get_key()
                if k in ("q", "ctrl-c"):
                    return
                elif k in ("down", "j"): self.set_cursor(self.cursor() + 1)
                elif k in ("up", "k"): self.set_cursor(self.cursor() - 1)
                elif k == "pgdn": self.set_cursor(self.cursor() + 10)
                elif k == "pgup": self.set_cursor(self.cursor() - 10)
                elif k in ("enter", "right", "l"): self.enter()
                elif k in ("left", "h", "backspace", "esc"): self.back()
                elif k == "tab": self.tab, self.query = (self.tab + 1) % len(self.tabs), ""
                elif k == "btab": self.tab, self.query = (self.tab - 1) % len(self.tabs), ""
                elif k == "space":
                    n = self.current()
                    if n and n.kind != "dir" and n.multi:
                        (self.selected.remove if n in self.selected else self.selected.append)(n)
                        self.set_cursor(self.cursor() + 1)
                elif k == "r" and self.selected: self.run(self.selected)
                elif k == "p":
                    n = self.current()
                    if n and n.kind != "dir":
                        self.viewer(f"Preview: {n.name}", n.preview())
                elif k == "/": self.search()
                elif k == "g": self.viewer("Task flags", "\n".join(f"{a:<4}{b}" for a, b in TASK_FLAGS.items()) + "\nP*  Requires privileges (e.g. PMP = privileged package-manager action)")
                elif k == "t": self.theme = Theme(self.theme.rule != "-")
        except KeyboardInterrupt:
            return
        finally:
            raw_off()
            sys.stdout.write("\033[?25h\033[?1049l")
            sys.stdout.flush()



# ═════════════════════════════ gui (tkinter, Windows + Linux + macOS) ═════════════════════════════

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def askpass():
    """sudo -A helper: shows a small password dialog and prints the password."""
    import tkinter as tk
    from tkinter import simpledialog
    r = tk.Tk()
    r.withdraw()
    print(simpledialog.askstring("xutil", "Password for sudo:", show="*", parent=r) or "")


def gui_env(admin):
    """Environment for child processes. On Linux/macOS, sudo gets a GUI password prompt."""
    env = dict(os.environ)
    if not WINDOWS and not admin and which("sudo"):
        import tempfile
        d = tempfile.mkdtemp(prefix="xutil_gui_")
        atexit.register(shutil.rmtree, d, True)
        me = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(__file__)]
        ask, wrap = Path(d) / "askpass", Path(d) / "sudo-gui"
        ask.write_text("#!/bin/sh\nexec " + " ".join(shlex.quote(x) for x in me) + " --askpass\n")
        wrap.write_text('#!/bin/sh\nexec sudo -A "$@"\n')
        for f in (ask, wrap):
            f.chmod(0o755)
        env.update(SUDO_ASKPASS=str(ask), XUTIL_ESCALATION=str(wrap))
    return env


def run_tasks(nodes, env, emit, dry=False, admin=False, box=None, status=None):
    """Run tasks in order, streaming output through emit(text). Stops at the first failure."""
    results = []
    note = status or (lambda n, st: None)
    for n in nodes:
        emit(f"\n▶ {n.name}\n")
        if WINDOWS and n.needs_admin() and not admin:
            emit("  skipped: needs Administrator (use 'Relaunch as Administrator')\n")
            results.append((n.name, "skipped"))
            note(n, "skipped")
            continue
        note(n, "running")
        if dry:
            emit("  (dry run) " + " ".join(shlex.quote(a) for a in n.argv) + "\n")
            results.append((n.name, "ok"))
            note(n, "ok")
            continue
        try:
            p = subprocess.Popen(n.argv, cwd=n.cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1,
                                 creationflags=0x08000000 if WINDOWS else 0)  # no flashing console on Windows
        except OSError as e:
            emit(f"  cannot start: {e}\n")
            results.append((n.name, "failed"))
            note(n, "failed")
            break
        if box is not None:
            box["proc"] = p
        for line in p.stdout:
            emit(ANSI_RE.sub("", line))
        rc = p.wait()
        if box and box.get("stop"):
            results.append((n.name, "stopped"))
            note(n, "stopped")
            break
        results.append((n.name, "ok" if rc == 0 else f"failed (exit {rc})"))
        note(n, "ok" if rc == 0 else "failed")
        if rc == 0:
            emit(f"✓ {n.name} done\n")
        if rc != 0:
            emit(f"✗ {n.name} failed (exit {rc}); stopping the queue.\n")
            break
    return results


def omarchy_palette():
    """Read the active Omarchy theme so xutil follows the desktop colour scheme."""
    if WINDOWS or OS_NAME != "linux":
        return None
    p = Path.home() / ".local/state/omarchy/current/theme/colors.toml"
    try:
        c = tomllib.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    def get(*keys, default):
        return next((c[k] for k in keys if k in c), default)

    return dict(
        bg=get("dark_background", "background", default="#1a1b26"),
        surface=get("background", "lighter_background", default="#24283b"),
        surface2=get("lighter_background", "selection", default="#2f334d"),
        fg=get("foreground", "light_foreground", default="#c0caf5"),
        dim=get("dark_foreground", "light_foreground", default="#7982a9"),
        accent=get("accent", "blue", default="#7aa2f7"),
        good=get("green", default="#9ece6a"),
        bad=get("red", default="#f7768e"),
        warn=get("orange", "yellow", default="#e0af68"),
        border=get("muted", "selection", default="#3b4261"),
    )


THEMES = {  # Modern dark palettes: bg / surface / surface2 / fg / dim / accent / good / bad / warn / border
    "Tokyo Night":      dict(bg="#181925", surface="#22253a", surface2="#2d3149", fg="#c8d0f5", dim="#828bad", accent="#7aa2f7", good="#9ece6a", bad="#f7768e", warn="#e0af68", border="#353b57"),
    "Catppuccin":       dict(bg="#1b1b2b", surface="#252536", surface2="#313244", fg="#cdd6f4", dim="#9399b2", accent="#cba6f7", good="#a6e3a1", bad="#f38ba8", warn="#f9e2af", border="#3b3d52"),
    "Gruvbox":          dict(bg="#282828", surface="#32302f", surface2="#3c3836", fg="#ebdbb2", dim="#a89984", accent="#fabd2f", good="#b8bb26", bad="#fb4934", warn="#fe8019", border="#504945"),
    "Nord":             dict(bg="#2b303b", surface="#353c4a", surface2="#3f4859", fg="#d8dee9", dim="#8a96ad", accent="#88c0d0", good="#a3be8c", bad="#bf616a", warn="#ebcb8b", border="#4c566a"),
    "Rose Pine":        dict(bg="#191724", surface="#1f1d2e", surface2="#2a2740", fg="#e0def4", dim="#908caa", accent="#ebbcba", good="#9ccfd8", bad="#eb6f92", warn="#f6c177", border="#423d5c"),
    "Kanagawa":         dict(bg="#1f1f28", surface="#27272f", surface2="#32323f", fg="#dcd7ba", dim="#8a8980", accent="#7e9cd8", good="#98bb6c", bad="#e46876", warn="#e6c384", border="#4a4a5e"),
    "Matte Black":      dict(bg="#0d0d0f", surface="#171719", surface2="#222225", fg="#d6d6d8", dim="#8b8b90", accent="#f59e0b", good="#8bb46c", bad="#e05b5b", warn="#e6b450", border="#2d2d32"),
}
OMARCHY_THEME = omarchy_palette()
if OMARCHY_THEME:
    THEMES["Omarchy"] = OMARCHY_THEME  # live colours from the active Omarchy theme
DEFAULT_THEME = "Omarchy" if OMARCHY_THEME else "Tokyo Night"
FONT_PREF = ["JetBrainsMono Nerd Font", "JetBrainsMono NF", "JetBrains Mono", "CaskaydiaMono Nerd Font", "Cascadia Mono",
             "Cascadia Code", "Fira Code", "SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono", "Liberation Mono", "Courier New"]

ICON_FOR = {
    "git": "git", "neovim": "neovim", "python 3": "python", "node.js": "nodejs", "java (jdk)": "java",
    "visual studio code": "vscode", "zed": "zed", "github cli": "github", "github desktop": "github",
    "gitlab cli": "gitlab", "docker": "docker", "windows terminal": "winterminal", "firefox": "firefox",
    "chromium": "chromium", "brave": "brave", "discord": "discord", "telegram": "telegram",
    "libreoffice": "libreoffice", "gimp": "gimp", "inkscape": "inkscape", "blender": "blender", "krita": "krita",
    "obs studio": "obs", "audacity": "audacity", "kdenlive": "kdenlive", "handbrake": "film",
    "thunderbird": "thunderbird", "keepassxc": "keepassxc", "qbittorrent": "qbittorrent", "photocraft": "image",
    "curl": "curl", "btop": "chart", "7-zip": "7zip", "vlc": "vlc", "fastfetch": "terminal",
    "ripgrep": "search", "fzf": "search", "jq": "code", "bat": "terminal", "lazygit": "git", "delta": "code",
    "fd": "search", "tldr": "doc", "zoxide": "folder", "starship": "terminal", "hyperfine": "activity", "eza": "folder",
    "developer tools": "code", "browsers": "globe", "communication": "chat", "open source apps": "package",
    "utilities": "wrench", "windows maintenance": "wrench",
    "applications setup": "grid", "system setup": "cpu", "security": "shield", "utils": "terminal",
    "system update": "refresh", "update xutil": "refresh", "system cleanup": "trash", "build essentials": "wrench",
    "ufw firewall baseline": "flame", "firewall baseline": "flame", "lynis security audit": "shieldcheck",
    "defender quick scan": "scan", "system info": "info", "disk usage": "disk", "ssh server": "server",
    "listening ports": "activity", "flush dns cache": "dns", "create restore point": "history",
    "repair windows (dism + sfc)": "wrench", "enable wsl": "layers", "explorer tweaks": "folder", "install xutil": "download",
    "timeshift": "history", "gnome tweaks": "wrench", "flatseal": "shieldcheck", "distrobox": "box", "powertoys": "wrench",
    "everything": "search", "windirstat": "disk", "notepad++": "code", "iterm2": "terminal", "rectangle": "grid",
    "raycast": "search", "stats": "chart", "common apps": "layers",
    "whatsapp": "whatsapp", "steam": "steam", ".net sdk": "dotnet", "jetbrains rider": "rider", "visual studio community": "visualstudio",
    "microsoft word": "word", "microsoft word 2013": "word", "gaming": "gamepad", "office & productivity": "doc",
}
CHIPS = {"I": ("root", 0), "MP": ("pkg", 0), "FI": ("flatpak", 0), "WG": ("winget", 0), "A": ("admin", 1), "SS": ("service", 0),
         "FM": ("files", 0), "RP": ("removes", 1), "D": ("disk", 1), "K": ("kernel", 1), "SI": ("system", 1), "R": ("reboot", 1),
         "REG": ("registry", 1), "WF": ("feature", 0), "FW": ("firewall", 1)}


def mix(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


def gui_cfg_path():
    base = os.environ.get("APPDATA") if WINDOWS else (os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config"))
    return Path(base or Path.home()) / "xutil" / "gui.json"


def load_gui_cfg():
    try:
        return json.loads(gui_cfg_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_gui_cfg(cfg):
    try:
        p = gui_cfg_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cfg), encoding="utf-8")
    except OSError:
        pass


def chips_for(task_list):
    out = []
    for tok in task_list.split():
        label = CHIPS.get(tok) or (("root", 0) if tok.startswith("P") else None)
        if tok.startswith("P") and tok[1:] in CHIPS:
            out.append(("root", 0))
            label = CHIPS[tok[1:]]
        if label and label not in out:
            out.append(label)
    return out[:4]


def run_gui(tabs, args):
    import base64
    import queue
    import threading
    import tkinter as tk
    from tkinter import font as tkfont

    try:
        from xutil_icons import ICONS
    except ImportError:
        ICONS = {}

    admin = is_admin()
    env = gui_env(admin)
    root = tk.Tk()
    root.title("xutil")
    root.geometry("1320x820")
    root.minsize(1000, 640)

    fams = set(tkfont.families(root))
    mono = next((f for f in FONT_PREF if f in fams), "TkFixedFont")
    F = dict(
        title=tkfont.Font(family=mono, size=19, weight="bold"), h=tkfont.Font(family=mono, size=13, weight="bold"),
        body=tkfont.Font(family=mono, size=11), bold=tkfont.Font(family=mono, size=11, weight="bold"),
        small=tkfont.Font(family=mono, size=10), tiny=tkfont.Font(family=mono, size=9), log=tkfont.Font(family=mono, size=11),
    )

    cfg = load_gui_cfg()
    name = getattr(args, "gui_theme", None) or cfg.get("theme") or DEFAULT_THEME
    S = dict(theme=name if name in THEMES else DEFAULT_THEME, tab=0, focus=None, hover=None)
    sel = {}                     # id(node) -> node  (survives rebuilds)
    dry = tk.BooleanVar(value=bool(args.dry_run))
    query = tk.StringVar()
    W = {}                       # live widgets of the current build
    cards = {}                   # id(node) -> card frame
    visible = []                 # nodes currently shown, in order
    cache = {}

    def C(k):
        return THEMES[S["theme"]][k]

    def icon(key, size=32):
        suffix = "" if size == 64 else f".{size}"
        k = key if (key + suffix) in ICONS else "box"
        if (k + suffix) not in ICONS:
            return None
        if (k, size) not in cache:
            cache[(k, size)] = tk.PhotoImage(data=base64.b64decode(ICONS[k + suffix]))
        return cache[(k, size)]

    def icon_key(n):
        return ICON_FOR.get(n.name.lower(), "folder" if n.kind == "dir" else "box")

    try:
        root.iconphoto(True, icon("logo", 64))
    except Exception:
        pass

    # ───────────── small widget helpers ─────────────
    def rrect(cv, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return cv.create_polygon(pts, smooth=True, **kw)

    def tile(parent, key, box, size, bg):
        cv = tk.Canvas(parent, width=box, height=box, bg=bg, highlightthickness=0, bd=0)
        rrect(cv, 1, 1, box - 1, box - 1, 10, fill=C("bg"), outline=C("border"))
        im = icon(key, size)
        if im:
            cv.create_image(box // 2, box // 2, image=im)
        return cv

    def button(parent, text, cmd, primary=False, img=None, bg=None):
        base = C("accent") if primary else C("surface2")
        hov = mix(base, "#ffffff", 0.14)
        fg = C("bg") if primary else C("fg")
        b = tk.Label(parent, text=text, image=img, compound="left" if img else "none", font=F["bold"], bg=base, fg=fg,
                     padx=18, pady=9, cursor="", highlightthickness=0 if primary else 1,
                     highlightbackground=C("border"), highlightcolor=C("border"))
        b.on, b.base, b.hov = True, base, hov
        b.off = C("border") if primary else C("surface")

        def enter(_):
            if b.on:
                b.configure(bg=b.hov)

        def leave(_):
            b.configure(bg=b.base if b.on else b.off)
        b.bind("<Enter>", enter)
        b.bind("<Leave>", leave)
        b.bind("<Button-1>", lambda e: cmd() if b.on else None)
        return b

    def enable(b, flag, primary=True):
        b.on = flag
        b.configure(bg=b.base if flag else b.off, fg=(C("bg") if primary else C("fg")) if flag else C("dim"),
                    cursor="")

    def walk(w):
        yield w
        for c in w.winfo_children():
            yield from walk(c)

    # ───────────── data helpers ─────────────
    def sections():
        """[(title, icon_key, [leaf nodes])] for the current tab, or for every tab when searching."""
        q = query.get().strip().lower()

        def collect(nodes, prefix):
            direct = [n for n in nodes if n.kind != "dir"]
            out = [(prefix, None, direct)] if direct else []
            for d in (n for n in nodes if n.kind == "dir"):
                out += collect(d.children, (prefix + " / " if prefix else "") + d.name)
            return out
        out = []
        for i, tab in enumerate(tabs):
            if not q and i != S["tab"]:
                continue
            for title, _, leaves in collect(tab.children, ""):
                if q:
                    leaves = [n for n in leaves if q in (n.name + " " + n.desc).lower()]
                    title = getattr(tab, "label", tab.name) + (" · " + title if title else "")
                if leaves:
                    last = title.split(" / ")[-1].split(" · ")[-1]
                    out.append((title, ICON_FOR.get(last.lower(), "folder"), leaves))
        return out

    # ───────────── selection / focus ─────────────
    def paint(n):
        card = cards.get(id(n))
        if not card:
            return
        selected, focused = id(n) in sel, S["focus"] is n
        bg = mix(C("surface"), C("accent"), 0.18) if selected else (C("surface2") if S["hover"] is n else C("surface"))
        for w in walk(card):
            if isinstance(w, tk.Canvas) and getattr(w, "is_tile", False):
                w.configure(bg=bg)
            elif isinstance(w, (tk.Frame, tk.Label)):
                w.configure(bg=bg)
            elif isinstance(w, tk.Canvas) and getattr(w, "is_check", False):
                w.configure(bg=bg)
        ring = C("accent") if focused else C("border")
        card.configure(highlightbackground=ring, highlightcolor=ring)
        cb = card.check
        cb.delete("all")
        rrect(cb, 1, 1, 19, 19, 5, fill=C("accent") if selected else bg, outline=C("accent") if selected else C("dim"), width=1.5)
        if selected:
            cb.create_line(5, 10, 9, 14, 15, 6, fill=C("bg"), width=2.2, capstyle="round", joinstyle="round")

    def set_focus(n, scroll=True):
        old = S["focus"]
        S["focus"] = n
        if old is not None:
            paint(old)
        if n is not None:
            paint(n)
            if scroll:
                ensure_visible(n)
        show_detail(n)
        refresh_actions()

    def toggle(n):
        if n is None or not n.multi or not n.usable:
            return
        if id(n) in sel:
            del sel[id(n)]
        else:
            sel[id(n)] = n
        paint(n)
        refresh_actions()
        show_detail(S["focus"])

    def ensure_visible(n):
        card = cards.get(id(n))
        if not card:
            return
        root.update_idletasks()
        cv, inner = W["canvas"], W["inner"]
        y = card.winfo_rooty() - inner.winfo_rooty()
        h, total, view = card.winfo_height(), max(inner.winfo_height(), 1), cv.winfo_height()
        top = cv.canvasy(0)
        if y < top + 8:
            cv.yview_moveto(max(0, (y - 56) / total))
        elif y + h > top + view - 8:
            cv.yview_moveto(min(1, (y + h - view + 20) / total))

    def move(dx, dy):
        cur = S["focus"]
        if not visible:
            return
        if cur not in visible:
            return set_focus(visible[0])
        root.update_idletasks()
        cc = cards[id(cur)]
        cx, cy = cc.winfo_rootx() + cc.winfo_width() / 2, cc.winfo_rooty() + cc.winfo_height() / 2
        best, score = None, None
        for n in visible:
            if n is cur:
                continue
            c = cards[id(n)]
            x, y = c.winfo_rootx() + c.winfo_width() / 2, c.winfo_rooty() + c.winfo_height() / 2
            if dx and abs(y - cy) < 30 and (x - cx) * dx > 5:
                s = abs(x - cx)
            elif dy and (y - cy) * dy > 10:
                s = abs(y - cy) * 3 + abs(x - cx)
            else:
                continue
            if score is None or s < score:
                best, score = n, s
        if best:
            set_focus(best)

    # ───────────── detail panel ─────────────
    def show_detail(n):
        d = W["detail"]
        for w in d.winfo_children():
            w.destroy()
        d.configure(bg=C("side"))
        if n is None:
            tk.Label(d, text="Select an item to see details", font=F["body"], bg=C("side"), fg=C("dim")).pack(expand=True)
            return
        head = tk.Frame(d, bg=C("side"))
        head.pack(fill="x", padx=20, pady=(22, 8))
        t = tile(head, icon_key(n), 76, 64, C("side"))
        t.pack(side="left")
        info = tk.Frame(head, bg=C("side"))
        info.pack(side="left", fill="x", expand=True, padx=14)
        tk.Label(info, text=n.name, font=F["h"], bg=C("side"), fg=C("fg"), anchor="w", justify="left", wraplength=190).pack(anchor="w")
        tk.Label(info, text=("script" if n.kind == "script" else "command"), font=F["tiny"], bg=C("side"), fg=C("dim")).pack(anchor="w")
        tk.Label(d, text=n.base or n.desc, font=F["body"], bg=C("side"), fg=C("fg"), wraplength=300, justify="left", anchor="w").pack(fill="x", padx=20, pady=(4, 6))
        if n.platforms:                                   # where this app exists
            pr = tk.Frame(d, bg=C("side"))
            pr.pack(fill="x", padx=20, pady=(2, 6))
            for o in PLATFORMS:
                on = o in n.platforms
                cell = tk.Frame(pr, bg=C("side"))
                cell.pack(side="left", padx=(0, 14))
                tk.Label(cell, image=icon(PLAT_ICON[o], "16" if on else "d16"), bg=C("side")).pack(side="left", padx=(0, 5))
                tk.Label(cell, text=PLAT_LABEL[o], font=F["tiny"], bg=C("side"), fg=(C("accent") if o == OS_NAME else C("fg")) if on else C("border")).pack(side="left")
        how = n.how.get(OS_NAME)
        if how and n.usable:
            tk.Label(d, text="Installs via: " + how, font=F["small"], bg=C("side"), fg=C("dim"), anchor="w", justify="left", wraplength=300).pack(fill="x", padx=20, pady=(0, 4))
        for line in (describe_flags(n.task_list) if n.usable else []):
            tk.Label(d, text="• " + line, font=F["small"], bg=C("side"), fg=C("warn") if any(k in line for k in ("removal", "Disk", "Kernel", "Registry", "Firewall", "Full system")) else C("dim"),
                     anchor="w", justify="left", wraplength=300).pack(fill="x", padx=20)
        if not n.usable:
            tk.Label(d, text=getattr(n, "why", "Not available on this system") + ".", font=F["small"], bg=C("side"), fg=C("warn"), anchor="w", justify="left",
                     wraplength=300).pack(fill="x", padx=20, pady=(8, 0))
            hint = n.how.get(OS_NAME)
            if hint:
                tk.Label(d, text=PLAT_LABEL.get(OS_NAME, OS_NAME) + ": " + hint, font=F["small"], bg=C("side"), fg=C("fg"), anchor="w", justify="left",
                         wraplength=300).pack(fill="x", padx=20, pady=(6, 0))
            tk.Label(d, text="You can open it on a " + " / ".join(PLAT_LABEL[o] for o in PLATFORMS if o in (n.platforms or ())) + " computer.", font=F["small"],
                     bg=C("side"), fg=C("dim"), anchor="w", justify="left", wraplength=300).pack(fill="x", padx=20, pady=(4, 0))
            return
        row = tk.Frame(d, bg=C("side"))
        row.pack(fill="x", padx=20, pady=14)
        button(row, "Run", lambda: go([n]), primary=True, img=icon("playdark", 22)).pack(side="left")
        if n.multi:
            lab = "Deselect" if id(n) in sel else "Select"
            button(row, lab, lambda: toggle(n), img=icon("check", 22)).pack(side="left", padx=8)
        tk.Label(d, text="SOURCE", font=F["tiny"], bg=C("side"), fg=C("dim"), anchor="w").pack(fill="x", padx=20)
        box = tk.Frame(d, bg=C("bg"), highlightthickness=1, highlightbackground=C("border"))
        box.pack(fill="both", expand=True, padx=20, pady=(4, 20))
        txt = tk.Text(box, wrap="word", font=F["tiny"], bg=C("bg"), fg=C("dim"), relief="flat", bd=0, highlightthickness=0, padx=10, pady=8, height=8)
        txt.insert("1.0", n.preview()[:5000])
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)

    # ───────────── running things ─────────────
    def refresh_actions():
        if "run" not in W:
            return
        n_sel, f = len(sel), S["focus"]
        if n_sel:
            W["run"].configure(text=f"Run selected ({n_sel})")
            enable(W["run"], True)
            names = ", ".join(n.name for n in list(sel.values())[:4]) + (" …" if n_sel > 4 else "")
            W["status"].configure(text=names, fg=C("fg"))
        elif f is not None and not f.usable:
            W["run"].configure(text="Not available")
            enable(W["run"], False)
            W["status"].configure(text=getattr(f, "why", "Not available on this system"), fg=C("warn"))
        elif f is not None:
            W["run"].configure(text=f"Run {f.name}")
            enable(W["run"], True)
            W["status"].configure(text="Space select · Enter run · / search · T theme", fg=C("dim"))
        else:
            W["run"].configure(text="Run")
            enable(W["run"], False)
            W["status"].configure(text="Select an item to get started", fg=C("dim"))
        enable(W["clear"], bool(n_sel), primary=False)
        if "count" in W and W["count"].winfo_exists():
            total = sum(len(s[2]) for s in sections())
            ready = sum(1 for s in sections() for n in s[2] if n.usable)
            searching = bool(query.get().strip())
            summary = f"{ready}/{total} ready on this computer" if not searching else f"Enter runs · Space selects · Esc clears"
            if n_sel:
                summary += f" · {n_sel} selected"
            W["count"].configure(text=summary)

    def run_primary():
        if sel:
            go(list(sel.values()))
        elif S["focus"] is not None:
            go([S["focus"]])

    def clear_sel():
        olds = list(sel.values())
        sel.clear()
        for n in olds:
            paint(n)
        refresh_actions()
        show_detail(S["focus"])

    def modal(title, w=520, h=None):
        win = tk.Toplevel(root)
        win.title(title)
        win.configure(bg=C("bg"))
        win.transient(root)
        win.geometry(f"{w}x{h}" if h else f"{w}x1")
        return win

    def confirm(nodes):
        win = modal("Run these tasks?", 540)
        win.geometry("")
        ok = {"v": False}
        body = tk.Frame(win, bg=C("bg"), padx=26, pady=22)
        body.pack(fill="both", expand=True)
        tk.Label(body, text=f"Run {len(nodes)} task{'s' if len(nodes) > 1 else ''}?", font=F["h"], bg=C("bg"), fg=C("fg")).pack(anchor="w")
        tk.Label(body, text="They run in this order and stop at the first failure.", font=F["small"], bg=C("bg"), fg=C("dim")).pack(anchor="w", pady=(2, 12))
        for n in nodes[:12]:
            r = tk.Frame(body, bg=C("surface"), padx=10, pady=7)
            r.pack(fill="x", pady=2)
            tk.Label(r, image=icon(icon_key(n), 22), bg=C("surface")).pack(side="left")
            tk.Label(r, text=n.name, font=F["bold"], bg=C("surface"), fg=C("fg")).pack(side="left", padx=10)
            skipped = WINDOWS and n.needs_admin() and not admin
            tk.Label(r, text="needs Administrator, will be skipped" if skipped else " ".join(c[0] for c in chips_for(n.task_list)),
                     font=F["tiny"], bg=C("surface"), fg=C("bad") if skipped else C("dim")).pack(side="right")
        if len(nodes) > 12:
            tk.Label(body, text=f"… and {len(nodes) - 12} more", font=F["small"], bg=C("bg"), fg=C("dim")).pack(anchor="w", pady=4)
        bar = tk.Frame(body, bg=C("bg"))
        bar.pack(fill="x", pady=(18, 0))

        def done(v):
            ok["v"] = v
            win.destroy()
        button(bar, "Run", lambda: done(True), primary=True, img=icon("playdark", 22)).pack(side="right")
        button(bar, "Cancel", lambda: done(False)).pack(side="right", padx=8)
        win.bind("<Return>", lambda e: done(True))
        win.bind("<Escape>", lambda e: done(False))
        win.update_idletasks()
        win.geometry(f"+{root.winfo_rootx() + (root.winfo_width() - win.winfo_width()) // 2}+{root.winfo_rooty() + 120}")
        win.grab_set()
        win.focus_set()
        root.wait_window(win)
        return ok["v"]

    def install_dialog():
        win = modal("Install xutil", 560)
        win.geometry("")
        body = tk.Frame(win, bg=C("bg"), padx=26, pady=22)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Install xutil", font=F["h"], bg=C("bg"), fg=C("fg")).pack(anchor="w")
        tk.Label(body, text="Adds xutil to your app menu and a 'xutil' command, so you can open it any time.", font=F["small"],
                 bg=C("bg"), fg=C("dim"), wraplength=500, justify="left").pack(anchor="w", pady=(2, 14))
        can_system = admin or (not WINDOWS and bool(env.get("XUTIL_ESCALATION")))

        def choose(system):
            win.destroy()
            me = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(__file__)]
            argv = me + ["--install"] + (["--system"] if system else [])
            if system and not WINDOWS and not admin:
                argv = [env["XUTIL_ESCALATION"]] + argv        # sudo -A: password dialog
            where = install_paths(system)["base"]
            node = Node("Install xutil", f"Copy xutil to {where}", "raw", False, "I" if system else "", argv, None, None, " ".join(argv))
            open_log([node])

        def option(title, sub, system, enabled=True, note=""):
            r = tk.Frame(body, bg=C("surface"), padx=14, pady=12, cursor="")
            r.pack(fill="x", pady=4)
            tk.Label(r, image=icon("download" if not system else "shield", 32), bg=C("surface")).pack(side="left", padx=(0, 14))
            col = tk.Frame(r, bg=C("surface"))
            col.pack(side="left", fill="x", expand=True)
            tk.Label(col, text=title, font=F["bold"], bg=C("surface"), fg=C("fg") if enabled else C("dim")).pack(anchor="w")
            tk.Label(col, text=sub + (f"  {note}" if note else ""), font=F["small"], bg=C("surface"), fg=C("dim"), anchor="w").pack(anchor="w")
            if enabled:
                for w in walk(r):
                    w.bind("<Button-1>", lambda e, s=system: choose(s))
                    w.bind("<Enter>", lambda e, r=r: [x.configure(bg=C("surface2")) for x in walk(r) if isinstance(x, (tk.Frame, tk.Label))])
                    w.bind("<Leave>", lambda e, r=r: [x.configure(bg=C("surface")) for x in walk(r) if isinstance(x, (tk.Frame, tk.Label))])
        option("Just for me", str(install_paths(False)["base"]), False, note="no password needed")
        option("All users on this computer", str(install_paths(True)["base"]), True, enabled=can_system,
               note="asks for your password" if not admin else "")
        if not can_system:
            tk.Label(body, text="All-users install needs Administrator (Windows) or sudo (Linux/macOS).", font=F["tiny"], bg=C("bg"), fg=C("warn")).pack(anchor="w", pady=(6, 0))
        bar = tk.Frame(body, bg=C("bg"))
        bar.pack(fill="x", pady=(16, 0))
        button(bar, "Cancel", win.destroy).pack(side="right")
        win.bind("<Escape>", lambda e: win.destroy())
        win.update_idletasks()
        win.geometry(f"+{root.winfo_rootx() + (root.winfo_width() - win.winfo_width()) // 2}+{root.winfo_rooty() + 120}")
        win.grab_set()
        win.focus_set()

    def go(nodes):
        nodes = [n for n in nodes if n is not None and n.usable]
        if not nodes:
            return
        if not dry.get() and not confirm(nodes):
            return
        open_log(nodes)

    def open_log(nodes):
        import math
        import time
        win = tk.Toplevel(root)
        win.title("xutil · running")
        win.geometry("1000x660")
        win.minsize(760, 480)
        win.configure(bg=C("bg"))
        win.transient(root)
        N = len(nodes)
        byid = {id(n): n for n in nodes}
        st = dict(done=0, cur=None, t0=time.time(), cur_t0=time.time(), prog=0.0, end=None, ok=True, finished=False, shown=None)

        # ── queue (left) ──
        side = tk.Frame(win, bg=C("side"), width=270)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="Queue", font=F["h"], bg=C("side"), fg=C("fg")).pack(anchor="w", padx=18, pady=(20, 8))
        marks = {}
        for n in nodes:
            r = tk.Frame(side, bg=C("side"))
            r.pack(fill="x", padx=14, pady=3)
            m = tk.Canvas(r, width=22, height=22, bg=C("side"), highlightthickness=0, bd=0)
            m.s, m.t, m.drawn = "pending", time.time(), False
            m.pack(side="left", padx=(0, 6))
            tk.Label(r, image=icon(icon_key(n), 22), bg=C("side")).pack(side="left", padx=(0, 8))
            tk.Label(r, text=n.name, font=F["body"], bg=C("side"), fg=C("fg"), anchor="w").pack(side="left")
            marks[id(n)] = m

        # ── hero (top right): icon / spinner, title, progress bar ──
        main = tk.Frame(win, bg=C("bg"))
        main.pack(side="left", fill="both", expand=True)
        hero = tk.Frame(main, bg=C("bg"))
        hero.pack(fill="x", padx=28, pady=(24, 8))
        holder = tk.Frame(hero, bg=C("bg"), width=84, height=84)
        holder.pack(side="left")
        holder.pack_propagate(False)
        txt_col = tk.Frame(hero, bg=C("bg"))
        txt_col.pack(side="left", padx=18, fill="x", expand=True)
        title = tk.Label(txt_col, text="Starting…", font=F["title"], bg=C("bg"), fg=C("fg"), anchor="w")
        title.pack(fill="x")
        sub = tk.Label(txt_col, text="", font=F["small"], bg=C("bg"), fg=C("dim"), anchor="w")
        sub.pack(fill="x", pady=(2, 0))
        bar = tk.Canvas(main, height=10, bg=C("bg"), highlightthickness=0, bd=0)
        bar.pack(fill="x", padx=28, pady=(6, 12))

        # ── details (collapsible log) ──
        dh = tk.Frame(main, bg=C("bg"))
        dh.pack(fill="x", padx=28)
        tk.Label(dh, text="DETAILS", font=F["tiny"], bg=C("bg"), fg=C("dim")).pack(side="left")
        tog = tk.Label(dh, text="hide", font=F["tiny"], bg=C("bg"), fg=C("accent"), cursor="")
        tog.pack(side="right")
        bottom = tk.Frame(main, bg=C("surface"), padx=10, pady=10)
        bottom.pack(side="bottom", fill="x")
        logwrap = tk.Frame(main, bg=C("bg"), highlightthickness=1, highlightbackground=C("border"))
        logwrap.pack(fill="both", expand=True, padx=28, pady=(6, 16))
        txt = tk.Text(logwrap, wrap="word", font=F["log"], bg=C("bg"), fg=C("fg"), insertbackground=C("fg"), relief="flat", bd=0,
                      highlightthickness=0, padx=14, pady=10, selectbackground=C("surface2"))
        sb = tk.Scrollbar(logwrap, command=txt.yview, bg=C("surface2"), troughcolor=C("bg"), relief="flat", bd=0, width=10, highlightthickness=0)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        for tag, kw in dict(step=dict(foreground=C("accent"), font=F["bold"]), bad=dict(foreground=C("bad")), dim=dict(foreground=C("dim")),
                            good=dict(foreground=C("good"), font=F["bold"])).items():
            txt.tag_configure(tag, **kw)

        def toggle_details(_=None):
            if logwrap.winfo_ismapped():
                logwrap.pack_forget()
                tog.configure(text="show")
            else:
                logwrap.pack(fill="both", expand=True, padx=28, pady=(6, 16))
                tog.configure(text="hide")
        tog.bind("<Button-1>", toggle_details)

        tk.Label(bottom, text="❯", font=F["bold"], bg=C("surface"), fg=C("accent")).pack(side="left", padx=(4, 8))
        ent = tk.Entry(bottom, font=F["body"], bg=C("surface"), fg=C("fg"), insertbackground=C("fg"), relief="flat", highlightthickness=0)
        ent.pack(side="left", fill="x", expand=True, ipady=6)
        box, qu = {}, queue.Queue()

        def send(_=None):
            p = box.get("proc")
            if p and p.poll() is None:
                try:
                    p.stdin.write(ent.get() + "\n")
                    p.stdin.flush()
                    txt.insert("end", "> " + ent.get() + "\n", "dim")
                except OSError:
                    pass
            ent.delete(0, "end")

        def stop():
            box["stop"] = True
            p = box.get("proc")
            if p and p.poll() is None:
                p.terminate()
        ent.bind("<Return>", send)
        stop_btn = button(bottom, "Stop", stop)
        stop_btn.pack(side="right", padx=(8, 0))
        button(bottom, "Send", send).pack(side="right", padx=(8, 0))

        # ── drawing ──
        hero_cv = {"cv": None}

        def set_hero_tile(n):
            for w in holder.winfo_children():
                w.destroy()
            cv = tk.Canvas(holder, width=84, height=84, bg=C("bg"), highlightthickness=0, bd=0)
            cv.pack()
            rrect(cv, 16, 16, 68, 68, 12, fill=C("surface"), outline=C("border"))     # tile with the app icon, spinner ring drawn around it
            im = icon(icon_key(n), 32)
            if im:
                cv.create_image(42, 42, image=im)
            hero_cv["cv"] = cv

        def draw_mark(cv, now):
            cv.delete("all")
            s, t = cv.s, now - cv.t
            if s == "pending":
                cv.create_oval(5, 5, 17, 17, outline=C("border"), width=2)
            elif s == "running":
                cv.create_oval(3, 3, 19, 19, outline=C("border"), width=2)
                cv.create_arc(3, 3, 19, 19, start=-(now * 320) % 360, extent=110, style="arc", outline=C("accent"), width=2.6)
            else:
                col = dict(ok=C("good"), failed=C("bad")).get(s, C("warn"))
                k = min(1.0, t / 0.28)
                r = 10 * (1 - (1 - k) ** 3) * (1 + 0.18 * math.sin(k * math.pi))   # ease-out with a little overshoot
                cv.create_oval(11 - r, 11 - r, 11 + r, 11 + r, fill=col, outline="")
                if k > 0.55:
                    if s == "ok":
                        cv.create_line(6.5, 11.5, 10, 15, 16, 7.5, fill=C("bg"), width=2.2, capstyle="round", joinstyle="round")
                    elif s == "failed":
                        cv.create_line(7, 7, 15, 15, 15, 7, 7, 15, fill=C("bg"), width=2.2, capstyle="round")
                    else:
                        cv.create_line(7, 11, 15, 11, fill=C("bg"), width=2.2, capstyle="round")

        def draw_hero(now):
            sp = hero_cv["cv"]
            if sp is None:
                return
            if st["end"] is None:
                sp.delete("spin")
                sp.create_arc(3, 3, 81, 81, start=-(now * 260) % 360, extent=80, style="arc", outline=C("accent"), width=3, tags="spin")
                sp.create_arc(3, 3, 81, 81, start=-(now * 260) % 360 + 180, extent=40, style="arc", outline=mix(C("accent"), C("bg"), .55), width=3, tags="spin")
            else:
                sp.delete("all")
                t = now - st["end"]
                col = C("good") if st["ok"] else C("bad")
                k = min(1.0, t / 0.55)
                sp.create_oval(4, 4, 80, 80, outline=C("border"), width=3)
                sp.create_arc(4, 4, 80, 80, start=90, extent=-360 * (1 - (1 - k) ** 3), style="arc", outline=col, width=4)
                if k >= 1:                                   # glyph draws in after the ring closes
                    g = min(1.0, (t - 0.55) / 0.3)
                    if st["ok"]:
                        pts = [(26, 43), (37, 54), (59, 30)]
                        seg1 = min(1, g * 2)
                        sp.create_line(26, 43, 26 + 11 * seg1, 43 + 11 * seg1, fill=col, width=5, capstyle="round")
                        if g > 0.5:
                            s2 = (g - 0.5) * 2
                            sp.create_line(37, 54, 37 + 22 * s2, 54 - 24 * s2, fill=col, width=5, capstyle="round")
                    else:
                        sp.create_line(30, 30, 30 + 24 * g, 30 + 24 * g, fill=col, width=5, capstyle="round")
                        sp.create_line(54, 30, 54 - 24 * g, 30 + 24 * g, fill=col, width=5, capstyle="round")

        def draw_bar(now):
            w = max(bar.winfo_width(), 40)
            bar.delete("all")
            rrect(bar, 0, 0, w, 10, 5, fill=C("surface2"), outline="")
            fw = w * st["prog"]
            col = C("accent")
            if st["end"] is not None:
                col = mix(C("accent"), C("good") if st["ok"] else C("bad"), min(1.0, (now - st["end"]) / 0.5))
            if fw >= 10:
                rrect(bar, 0, 0, fw, 10, 5, fill=col, outline="")
                if st["end"] is None and fw > 40:             # shimmer sweeping through the filled part
                    x = (now * 240) % (fw + 140) - 100
                    a, b = max(6, x), min(fw - 6, x + 100)
                    if b > a:
                        bar.create_rectangle(a, 2, b, 8, fill=mix(col, "#ffffff", 0.38), outline="")

        def elapsed():
            s = int((st["end"] or time.time()) - st["t0"])
            return f"{s // 60:02d}:{s % 60:02d}"

        def tick():
            if not win.winfo_exists():
                return
            now = time.time()
            if st["end"] is None:                              # target: finished tasks + a slowly creeping share of the running one
                creep = 0.9 * (1 - math.exp(-(now - st["cur_t0"]) / 7)) if st["cur"] is not None else 0
                target = (st["done"] + creep) / N
            else:
                target = 1.0 if st["ok"] else st["prog"]
            st["prog"] += (target - st["prog"]) * 0.12
            if abs(target - st["prog"]) < 0.0005:
                st["prog"] = target
            draw_bar(now)
            draw_hero(now)
            for m in marks.values():
                if m.s in ("running", "pending") and (m.s == "running" or not m.drawn) or now - m.t < 0.4 or not m.drawn:
                    draw_mark(m, now)
                    m.drawn = m.s != "running" and now - m.t >= 0.4
            if st["end"] is None and st["cur"] is not None:
                i = nodes.index(st["cur"]) + 1
                sub.configure(text=f"Task {i} of {N}  ·  {elapsed()}" + ("  ·  dry run" if dry.get() else ""))
            win.after(33, tick)

        def verb(n):
            p = str(n.path or "")
            return "Installing" if ("install" in p or "docker-setup" in p or n.name == "Install xutil") else "Running"

        def pump():
            try:
                while True:
                    item = qu.get_nowait()
                    if isinstance(item, tuple) and item[0] == "status":
                        n, state = byid[item[1]], item[2]
                        m = marks[item[1]]
                        m.s, m.t, m.drawn = ("running" if state == "running" else state), time.time(), False
                        if state == "running":
                            st["cur"], st["cur_t0"] = n, time.time()
                            title.configure(text=f"{verb(n)} {n.name}")
                            set_hero_tile(n)
                        elif state in ("ok", "skipped"):
                            st["done"] += 1
                        else:
                            st["ok"] = False
                    elif isinstance(item, tuple):
                        res = item[1]
                        good = sum(1 for _, s in res if s == "ok")
                        st["ok"] = st["ok"] and good == N
                        st["end"] = time.time()
                        for w in holder.winfo_children():
                            w.destroy()
                        sp = tk.Canvas(holder, width=84, height=84, bg=C("bg"), highlightthickness=0, bd=0)
                        sp.pack()
                        hero_cv["cv"] = sp
                        title.configure(text="All done" if st["ok"] else ("Stopped" if box.get("stop") else "Finished with errors"),
                                        fg=C("good") if st["ok"] else C("bad"))
                        sub.configure(text=f"{good} of {N} succeeded  ·  {elapsed()}" + ("  ·  dry run" if dry.get() else ""))
                        txt.insert("end", f"\n{good} ok" + (f", {N - good} not ok" if good != N else "") + "\n", "good" if st["ok"] else "bad")
                        stop_btn.configure(text="Close", bg=C("accent"), fg=C("bg"))
                        stop_btn.base, stop_btn.hov, stop_btn.on = C("accent"), mix(C("accent"), "#ffffff", .14), True
                        stop_btn.bind("<Button-1>", lambda e: win.destroy())
                    else:
                        tag = "step" if item.lstrip().startswith("▶") else ("bad" if item.lstrip().startswith("✗") else ("good" if item.lstrip().startswith("✓") else ("dim" if "(dry run)" in item else None)))
                        txt.insert("end", item, tag) if tag else txt.insert("end", item)
                    txt.see("end")
            except queue.Empty:
                pass
            if win.winfo_exists():
                win.after(60, pump)

        def work():
            res = run_tasks(nodes, env, qu.put, dry.get(), admin, box, status=lambda n, s: qu.put(("status", id(n), s)))
            qu.put(("done", res))
        set_hero_tile(nodes[0])
        title.configure(text=f"{verb(nodes[0])} {nodes[0].name}")
        threading.Thread(target=work, daemon=True).start()
        pump()
        tick()
        ent.focus_set()

    def relaunch_admin():
        import ctypes
        params = "--gui" if getattr(sys, "frozen", False) else f'"{os.path.abspath(sys.argv[0])}" --gui'
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        root.destroy()

    # ───────────── cards ─────────────
    def make_card(parent, n):
        card = tk.Frame(parent, bg=C("surface"), highlightthickness=1, highlightbackground=C("border"), highlightcolor=C("border"), cursor="")
        t = tile(card, icon_key(n), 54, 32, C("surface"))
        t.is_tile = True
        t.pack(side="left", padx=(14, 12), pady=14, anchor="n")
        card.check = tk.Canvas(card, width=20, height=20, bg=C("surface"), highlightthickness=0, bd=0, cursor="")
        card.check.is_check = True
        if n.multi:
            card.check.pack(side="right", padx=(0, 14), pady=16, anchor="n")
        mid = tk.Frame(card, bg=C("surface"))
        mid.pack(side="left", fill="both", expand=True, pady=(14, 12))
        ok = n.usable
        tk.Label(mid, text=n.name, font=F["bold"], bg=C("surface"), fg=C("fg") if ok else C("dim"), anchor="w").pack(fill="x")
        d = tk.Label(mid, text=n.base or n.desc, font=F["small"], bg=C("surface"), fg=C("dim") if ok else mix(C("dim"), C("surface"), .45), anchor="w", justify="left", wraplength=190)
        d.pack(fill="x", pady=(2, 5))
        card.desc = d
        row = tk.Frame(mid, bg=C("surface"))
        row.pack(fill="x")
        if n.platforms:                                  # which operating systems have this app
            bf = tk.Frame(row, bg=C("surface"))
            bf.pack(side="right")
            for o in PLATFORMS:
                tk.Label(bf, image=icon(PLAT_ICON[o], "16" if o in n.platforms else "d16"), bg=C("surface")).pack(side="left", padx=2)
        for label, risky in (chips_for(n.task_list) if ok else [("not on " + PLAT_LABEL.get(OS_NAME, OS_NAME), 1)]):
            ch = tk.Label(row, text=label, font=F["tiny"], bg=C("surface"), fg=C("warn") if risky else C("dim"), padx=0)
            ch.chip = True
            ch.pack(side="left", padx=(0, 8))
            ch.configure(bg=C("surface"))

        def hover(on):
            if on:
                S["hover"] = n
            elif S["hover"] is n:
                S["hover"] = None
            paint(n)

        def leave(_):
            x, y = root.winfo_pointerxy()
            w = root.winfo_containing(x, y)
            if not (w and str(w).startswith(str(card))):
                hover(False)
        for w in walk(card):
            w.bind("<Enter>", lambda e: hover(True), add="+")
            w.bind("<Leave>", leave, add="+")
            w.bind("<Button-1>", lambda e: set_focus(n, scroll=False), add="+")
            w.bind("<Double-Button-1>", lambda e: go([n]) if n.usable else None, add="+")
        card.check.bind("<Button-1>", lambda e: (toggle(n), "break")[1])
        card.check.bind("<Double-Button-1>", lambda e: "break")
        return card

    def relayout(_=None):
        if "canvas" not in W or not W["canvas"].winfo_exists():
            return
        cv = W["canvas"]
        width = max(cv.winfo_width(), 300)
        cv.itemconfigure(W["win"], width=width)
        cols = max(1, (width - 20) // 330)
        for sec in W["secs"]:
            for c in range(8):
                sec.grid_columnconfigure(c, weight=1 if c < cols else 0, uniform="c" if c < cols else "")
            for i, n in enumerate(sec.nodes):
                cards[id(n)].grid(row=i // cols + 1, column=i % cols, sticky="nsew", padx=6, pady=6)
                cards[id(n)].desc.configure(wraplength=max(120, (width - 20) // cols - 150))
        cv.configure(scrollregion=cv.bbox("all"))

    def populate():
        inner = W["inner"]
        for w in inner.winfo_children():
            w.destroy()
        cards.clear()
        visible.clear()
        W["secs"] = []
        secs = sections()
        for title, ik, leaves in secs:
            sec = tk.Frame(inner, bg=C("bg"))
            sec.pack(fill="x", padx=14, pady=(8, 6))
            sec.nodes = leaves
            if title:
                h = tk.Frame(sec, bg=C("bg"))
                h.grid(row=0, column=0, columnspan=8, sticky="w", padx=6, pady=(8, 0))
                tk.Label(h, image=icon(ik, 22), bg=C("bg")).pack(side="left")
                tk.Label(h, text=title, font=F["bold"], bg=C("bg"), fg=C("dim")).pack(side="left", padx=8)
            for n in leaves:
                cards[id(n)] = make_card(sec, n)
                visible.append(n)
            W["secs"].append(sec)
        if not secs:
            box = tk.Frame(inner, bg=C("bg"))
            box.pack(pady=90)
            tk.Label(box, image=icon("search", 64), bg=C("bg")).pack()
            tk.Label(box, text="No matches", font=F["h"], bg=C("bg"), fg=C("fg")).pack(pady=(10, 2))
            tk.Label(box, text="Try another word, or press Esc to clear the search", font=F["small"], bg=C("bg"), fg=C("dim")).pack()
        relayout()
        W["canvas"].yview_moveto(0)
        for n in visible:
            paint(n)
        if S["focus"] not in visible:
            S["focus"] = None
        set_focus(S["focus"] or (visible[0] if visible else None), scroll=False)
        total = sum(len(s[2]) for s in secs)
        cur = tabs[S["tab"]]
        ready = sum(1 for s_ in secs for n_ in s_[2] if n_.usable)
        searching = bool(query.get().strip())
        W["title"].configure(text="Search" if searching else getattr(cur, "title", cur.name))
        blurb = getattr(cur, "blurb", "")
        W["sub"].configure(text=(f"{total} {'result' if total == 1 else 'results'} for “{query.get().strip()}”" if searching
                                 else (blurb or f"Tools for {PLAT_LABEL.get(OS_NAME, OS_NAME)}")))
        summary = f"{ready}/{total} ready on this computer" if not searching else f"Enter runs · Space selects · Esc clears"
        if sel:
            summary += f" · {len(sel)} selected"
        W["count"].configure(text=summary)

    def pick_tab(i):
        S["tab"] = i % len(tabs)
        if query.get():
            query.set("")
        build_tabs()
        populate()

    def build_tabs():
        for w in W["tabs"].winfo_children():
            w.destroy()
        searching = bool(query.get().strip())
        group = None
        for i, tab in enumerate(tabs):
            g = getattr(tab, "group", None)
            if g and g != group:
                group = g
                tk.Label(W["tabs"], text=g, font=F["tiny"], bg=C("side"), fg=C("dim"), anchor="w").pack(fill="x", padx=20, pady=(14 if i else 4, 4))
            active = i == S["tab"] and not searching
            bg = C("surface") if active else C("side")
            row = tk.Frame(W["tabs"], bg=bg, cursor="")
            row.pack(fill="x", pady=1)
            tk.Frame(row, bg=C("accent") if active else bg, width=3).pack(side="left", fill="y")
            ik = getattr(tab, "icon", None) or ICON_FOR.get(tab.name.lower(), "box")
            tk.Label(row, image=icon(ik, 22), bg=bg).pack(side="left", padx=(14, 10), pady=9)
            tk.Label(row, text=getattr(tab, "label", tab.name), font=F["bold"] if active else F["body"], bg=bg, fg=C("fg") if active else C("dim")).pack(side="left")
            tk.Label(row, text=str(sum(1 for _ in tab.leaves())), font=F["tiny"], bg=bg, fg=C("dim")).pack(side="right", padx=14)
            if getattr(tab, "plat", None) == OS_NAME:
                tk.Label(row, text="●", font=F["tiny"], bg=bg, fg=C("good")).pack(side="right")
            for w in walk(row):
                w.bind("<Button-1>", lambda e, i=i: pick_tab(i))

    def cycle_theme(step=1):
        names = list(THEMES)
        S["theme"] = names[(names.index(S["theme"]) + step) % len(names)]
        cfg["theme"] = S["theme"]
        save_gui_cfg(cfg)
        build()

    # ───────────── main layout ─────────────
    def build():
        old = W.get("app")
        if old is not None:
            old.destroy()
        for k in list(W):
            del W[k]
        root.configure(bg=C("bg"))
        THEMES[S["theme"]]["side"] = mix(C("bg"), "#000000", 0.20)
        app = tk.Frame(root, bg=C("bg"))
        app.pack(fill="both", expand=True)
        W["app"] = app
        app.grid_columnconfigure(1, weight=1)
        app.grid_rowconfigure(0, weight=1)

        # sidebar
        side = tk.Frame(app, bg=C("side"), width=252)
        side.grid(row=0, column=0, rowspan=2, sticky="ns")
        side.pack_propagate(False)
        logo = tk.Frame(side, bg=C("side"))
        logo.pack(fill="x", padx=18, pady=(22, 20))
        tk.Label(logo, image=icon("logo", 32), bg=C("side")).pack(side="left")
        lt = tk.Frame(logo, bg=C("side"))
        lt.pack(side="left", padx=10)
        tk.Label(lt, text="xutil", font=F["h"], bg=C("side"), fg=C("fg")).pack(anchor="w")
        tk.Label(lt, text="setup toolbox", font=F["tiny"], bg=C("side"), fg=C("dim")).pack(anchor="w")
        W["tabs"] = tk.Frame(side, bg=C("side"))
        W["tabs"].pack(fill="x")
        foot = tk.Frame(side, bg=C("side"))
        foot.pack(side="bottom", fill="x", padx=14, pady=16)
        if WINDOWS and not admin:
            button(foot, "Relaunch as Admin", relaunch_admin, img=icon("shield", 22)).pack(fill="x", pady=(0, 10))
        button(foot, "Install xutil", install_dialog, img=icon("download", 22)).pack(fill="x", pady=(0, 10))
        tb = tk.Frame(foot, bg=C("surface"), cursor="")
        tb.pack(fill="x")
        tk.Label(tb, image=icon("palette", 22), bg=C("surface")).pack(side="left", padx=(10, 8), pady=9)
        tk.Label(tb, text=S["theme"], font=F["small"], bg=C("surface"), fg=C("fg")).pack(side="left")
        dots = tk.Canvas(tb, width=54, height=12, bg=C("surface"), highlightthickness=0)
        dots.pack(side="right", padx=10)
        for i, k in enumerate(("accent", "good", "warn", "bad")):
            dots.create_oval(i * 13 + 1, 1, i * 13 + 11, 11, fill=C(k), outline="")
        for w in walk(tb):
            w.bind("<Button-1>", lambda e: cycle_theme(1))
            w.bind("<Button-3>", lambda e: cycle_theme(-1))
        tk.Label(foot, text=f"● {PLAT_LABEL.get(OS_NAME, OS_NAME)} (this computer)\n   {'administrator' if admin else 'standard user'}", font=F["tiny"], bg=C("side"), fg=C("dim"), justify="left").pack(anchor="w", pady=(10, 0))

        # main column
        main = tk.Frame(app, bg=C("bg"))
        main.grid(row=0, column=1, sticky="nsew")
        top = tk.Frame(main, bg=C("bg"))
        top.pack(fill="x", padx=26, pady=(22, 8))
        tl = tk.Frame(top, bg=C("bg"))
        tl.pack(side="left")
        W["title"] = tk.Label(tl, text="", font=F["title"], bg=C("bg"), fg=C("fg"))
        W["title"].pack(anchor="w")
        W["sub"] = tk.Label(tl, text="", font=F["small"], bg=C("bg"), fg=C("dim"), justify="left", anchor="w")
        W["sub"].pack(anchor="w")
        W["count"] = tk.Label(tl, text="", font=F["tiny"], bg=C("bg"), fg=C("dim"), anchor="w")
        W["count"].pack(anchor="w", pady=(4, 0))
        sbox = tk.Frame(top, bg=C("surface"), highlightthickness=1, highlightbackground=C("border"), highlightcolor=C("accent"))
        sbox.pack(side="right")
        tk.Label(sbox, image=icon("search", 22), bg=C("surface")).pack(side="left", padx=(12, 6))
        ent = tk.Entry(sbox, textvariable=query, width=30, font=F["body"], bg=C("surface"), fg=C("fg"), insertbackground=C("accent"), relief="flat", highlightthickness=0)
        ent.pack(side="left", ipady=8, padx=(0, 6))
        hint = tk.Label(sbox, text="/", font=F["tiny"], bg=C("surface2"), fg=C("dim"), padx=6, cursor="")
        hint.pack(side="right", padx=8)
        W["search"], W["search_hint"] = ent, hint

        def sync_search(*_):
            has = bool(query.get().strip())
            hint.configure(text="✕" if has else "/", fg=C("fg") if has else C("dim"))
            if "canvas" in W:
                build_tabs()
                populate()
        hint.bind("<Button-1>", lambda e: (query.set(""), ent.focus_set()))
        query.trace_add("write", sync_search)
        sync_search()

        ent.bind("<Down>", lambda e: (root.focus_set(), move(0, 1) if S["focus"] else None, "break")[2])
        ent.bind("<Return>", lambda e: (root.focus_set(), set_focus(visible[0]) if visible else None))
        ent.bind("<Escape>", lambda e: (query.set(""), root.focus_set()))

        wrap = tk.Frame(main, bg=C("bg"))
        wrap.pack(fill="both", expand=True)
        cv = tk.Canvas(wrap, bg=C("bg"), highlightthickness=0, bd=0)
        sc = tk.Scrollbar(wrap, orient="vertical", command=cv.yview, bg=C("surface2"), troughcolor=C("bg"), activebackground=C("dim"),
                          relief="flat", bd=0, width=9, highlightthickness=0, elementborderwidth=0)
        cv.configure(yscrollcommand=sc.set)
        sc.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(cv, bg=C("bg"))
        W["win"] = cv.create_window(0, 0, window=inner, anchor="nw")
        W["canvas"], W["inner"] = cv, inner
        cv.bind("<Configure>", relayout)
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))

        # detail panel
        W["detail"] = tk.Frame(app, bg=C("side"), width=368)
        W["detail"].grid(row=0, column=2, sticky="ns")
        W["detail"].pack_propagate(False)

        # action bar
        bar = tk.Frame(app, bg=C("surface"))
        bar.grid(row=1, column=1, columnspan=2, sticky="ew")
        inner_bar = tk.Frame(bar, bg=C("surface"), padx=22, pady=12)
        inner_bar.pack(fill="x")
        W["run"] = button(inner_bar, "Run", run_primary, primary=True, img=icon("playdark", 22))
        W["run"].pack(side="right")
        W["clear"] = button(inner_bar, "Clear", clear_sel)
        W["clear"].pack(side="right", padx=8)
        dc = tk.Checkbutton(inner_bar, text="Dry run", variable=dry, font=F["small"], bg=C("surface"), fg=C("fg"), selectcolor=C("bg"),
                            activebackground=C("surface"), activeforeground=C("fg"), highlightthickness=0, bd=0, cursor="")
        dc.pack(side="right", padx=14)
        W["status"] = tk.Label(inner_bar, text="", font=F["small"], bg=C("surface"), fg=C("dim"), anchor="w")
        W["status"].pack(side="left", fill="x", expand=True)

        build_tabs()
        populate()
        refresh_actions()

    # ───────────── keyboard + wheel ─────────────
    def typing(e):
        return isinstance(e.widget, (tk.Entry, tk.Text))

    def on_key(e):
        if typing(e) or e.widget.winfo_toplevel() is not root:
            return
        k = e.keysym
        if k in ("Left", "Right", "Up", "Down"):
            move({"Left": -1, "Right": 1}.get(k, 0), {"Up": -1, "Down": 1}.get(k, 0))
        elif k == "space":
            toggle(S["focus"])
        elif k == "Return":
            run_primary() if (e.state & 4) else go([S["focus"]])
        elif k in ("slash",) or (k == "k" and e.state & 4):
            W["search"].focus_set()
        elif k == "Escape":
            clear_sel() if sel and not query.get() else query.set("")
        elif k == "t":
            cycle_theme(1)
        elif k == "i" and not (e.state & 4):
            install_dialog()
        elif k == "bracketright":
            pick_tab(S["tab"] + 1)
        elif k == "bracketleft":
            pick_tab(S["tab"] - 1)
        elif k in "1234567" and len(k) == 1 and int(k) <= len(tabs):
            pick_tab(int(k) - 1)
        elif k == "q" and e.state & 4:
            root.destroy()
        return "break"

    def on_wheel(e):
        cv = W.get("canvas")
        if not cv or e.widget.winfo_toplevel() is not root:
            return
        if getattr(e, "num", 0) == 4:
            d = -1
        elif getattr(e, "num", 0) == 5:
            d = 1
        else:
            d = -1 if e.delta > 0 else 1
        cv.yview_scroll(d * 3, "units")
    root.bind("<Key>", on_key)
    root.bind_all("<MouseWheel>", on_wheel)
    root.bind_all("<Button-4>", on_wheel)
    root.bind_all("<Button-5>", on_wheel)

    build()
    root._x = dict(sel=sel, go=go, S=S, W=W, cards=cards, visible=visible, pick_tab=pick_tab, cycle_theme=cycle_theme,
                   run_tasks=run_tasks, install_dialog=install_dialog, set_focus=set_focus, toggle=toggle, query=query, open_log=open_log, tabs=tabs)  # test hook
    root.mainloop()


# ═════════════════════════════ platform views (Common / Windows / Linux / macOS) ═════════════════════════════

PLATFORMS = ("windows", "linux", "darwin")
PLAT_LABEL = {"windows": "Windows", "linux": "Linux", "darwin": "macOS"}
PLAT_ICON = {"windows": "windows", "linux": "linux", "darwin": "apple"}
_OS_MARK = re.compile(r"\s+(Linux|Windows|macOS):")
_MARK_OS = {"Linux": "linux", "Windows": "windows", "macOS": "darwin"}


def desc_parts(desc):
    """'Editor. Linux: Flatpak. Windows: winget.' -> ('Editor.', {'linux': 'Flatpak.', 'windows': 'winget.'})"""
    parts = _OS_MARK.split(desc)
    return parts[0].strip(), {_MARK_OS[parts[i]]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def gui_tabs(all_tabs, ok_tabs):
    """Window layout: app tabs split by platform (Common = on 2+ OSes), then the system tabs for this OS.
    `all_tabs` is the catalog loaded with validate=False, `ok_tabs` the one filtered for this system."""
    out = []
    apps = next((t for t in all_tabs if t.name == "Applications Setup"), None)
    if apps is not None:
        seen = {}

        def visit(nodes, folder):
            for n in nodes:
                if n.kind == "dir":
                    visit(n.children, n.name)
                else:
                    a = seen.setdefault((folder, n.name), dict(folder=folder, name=n.name, desc=n.desc, task=n.task_list, v={}))
                    for o in (n.os_tags or PLATFORMS):
                        a["v"].setdefault(o, n)
        visit(apps.children, "")
        groups = {k: {} for k in ("common",) + PLATFORMS}
        for a in seen.values():
            plats = set(a["v"])
            cat = "common" if len(plats) >= 2 else next(iter(plats))
            node = a["v"].get(OS_NAME)
            if node is None or not node.usable:
                why = (f"Needs a tool that is missing on this {PLAT_LABEL.get(OS_NAME, OS_NAME)} system" if node is not None
                       else "Not available for " + PLAT_LABEL.get(OS_NAME, OS_NAME))
                node = Node(a["name"], a["desc"], "script", False, a["task"])      # greyed-out placeholder card
                node.usable, node.why = False, why
            node.platforms = plats
            node.base, node.how = desc_parts(a["desc"])
            groups[cat].setdefault(a["folder"], []).append(node)
        meta = [("common", "Common Apps", "Common", "layers", "Cross-platform apps. xutil installs each one with the right tool for this computer."),
                ("windows", "Windows Apps", "Windows", "windows", "Apps that only exist on Windows."),
                ("linux", "Linux Apps", "Linux", "linux", "Apps that only exist on Linux."),
                ("darwin", "macOS Apps", "macOS", "apple", "Apps that only exist on macOS.")]
        for cat, title, label, ic, blurb in meta:
            root = Node(title)
            for folder, leaves in groups[cat].items():
                if folder:
                    d = Node(folder)
                    d.children = leaves
                    root.children.append(d)
                else:
                    root.children += leaves
            root.title, root.label, root.icon, root.blurb, root.group = title, label, ic, blurb, "APPS"
            root.plat = cat if cat in PLATFORMS else None
            out.append(root)
    for t in ok_tabs:
        if t.name != "Applications Setup":
            t.title, t.label, t.icon, t.blurb, t.group, t.plat = t.name.replace(" Setup", ""), t.name.replace(" Setup", ""), None, "", "SYSTEM", None
            out.append(t)
    return out or ok_tabs


# ═════════════════════════════ self-install (xutil installs itself) ═════════════════════════════

def install_paths(system):
    """Where xutil lives for this OS and scope. Returns dict of base/bin/desktop/icon/menu."""
    if WINDOWS:
        root = Path(os.environ.get("ProgramFiles" if system else "LOCALAPPDATA", Path.home()))
        menu = (Path(os.environ.get("ProgramData", "C:/ProgramData")) if system else Path(os.environ.get("APPDATA", Path.home()))) / "Microsoft/Windows/Start Menu/Programs"
        return dict(base=root / "xutil", bin=None, desktop=None, icon=None, menu=menu / "xutil.lnk")
    prefix = Path("/usr/local") if system else Path.home() / ".local"
    return dict(base=prefix / "share" / "xutil", bin=prefix / "bin" / "xutil",
                desktop=None if OS_NAME == "darwin" else prefix / "share/applications/xutil.desktop",
                icon=None if OS_NAME == "darwin" else prefix / "share/icons/hicolor/256x256/apps/xutil.png", menu=None)


def png_to_ico(png: bytes):
    """Minimal .ico that wraps a PNG (Windows Vista+ reads it)."""
    import struct
    w = h = 64
    return struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png), 22) + png


def install_self(system=False, remove=False):
    import base64
    import stat
    P = install_paths(system)
    scope = "all users" if system else "this user"
    if remove:
        for k in ("base", "bin", "desktop", "icon", "menu"):
            if P[k]:
                shutil.rmtree(P[k], True) if P[k].is_dir() else P[k].unlink(missing_ok=True)
        print(f"xutil removed ({scope}).")
        return 0
    if system and not WINDOWS and os.geteuid() != 0:
        sys.exit("System-wide install needs root: run  sudo python3 xutil.py --install --system")
    frozen = getattr(sys, "frozen", False)
    me = Path(sys.executable if frozen else __file__).resolve()
    base = P["base"]
    src = HERE
    if base.resolve() == me.parent or base.resolve() in me.parents:
        # Reinstalling from the installed copy: stage it elsewhere first, because we wipe `base` below.
        import tempfile
        stage = Path(tempfile.mkdtemp(prefix="xutil_stage_"))
        atexit.register(shutil.rmtree, stage, True)
        shutil.copytree(base, stage / "x")
        me, src = stage / "x" / me.name, stage / "x"
    print(f"Installing xutil for {scope} into {base}")
    shutil.rmtree(base, True)
    base.mkdir(parents=True, exist_ok=True)
    if frozen:                                   # PyInstaller app: copy the executable itself
        target = base / me.name
        shutil.copy2(me, target)
        run_cmd = [str(target)]
    else:
        shutil.copy2(me, base / "xutil.py")
        if not EMBEDDED:                         # source checkout: also copy icons + catalog
            for name in ("xutil_icons.py",):
                if (src / name).exists():
                    shutil.copy2(src / name, base / name)
            shutil.copytree(src / "tabs", base / "tabs", ignore=shutil.ignore_patterns("__pycache__"))
        py = sys.executable
        if WINDOWS and Path(py).with_name("pythonw.exe").exists():
            py = str(Path(py).with_name("pythonw.exe"))   # no console window behind the GUI
        run_cmd = [py, str(base / "xutil.py")]
    try:
        from xutil_icons import ICONS
        png = base64.b64decode(ICONS["logo"])
    except Exception:
        png = b""
    big = src / "assets" / "xutil.png"
    big_png = big.read_bytes() if big.exists() else png
    if WINDOWS:
        ico = base / "xutil.ico"
        ico.write_bytes(png_to_ico(png))
        (base / "xutil.cmd").write_text('@echo off\r\n' + " ".join(f'"{a}"' for a in run_cmd) + " %*\r\n")
        lnk = P["menu"]
        lnk.parent.mkdir(parents=True, exist_ok=True)
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');$s.TargetPath='%s';$s.Arguments='%s';"
              "$s.IconLocation='%s';$s.WorkingDirectory='%s';$s.Description='Install apps and set up your system';$s.Save()"
              % (lnk, run_cmd[0], " ".join(f'"{a}"' for a in run_cmd[1:] + ["--gui"]).replace("'", "''"), ico, base))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
        print(f"Start Menu shortcut: {lnk}")
        print(f"Command: {base / 'xutil.cmd'}  (add {base} to PATH to use `xutil` anywhere)")
    else:
        launcher = P["bin"]
        launcher.parent.mkdir(parents=True, exist_ok=True)
        cmd = " ".join(shlex.quote(a) for a in run_cmd)
        launcher.write_text("#!/bin/sh\n# xutil launcher: window when a display exists, terminal menu otherwise.\n"
                            'if [ $# -eq 0 ] && { [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ] || [ "$(uname)" = Darwin ]; }; then set -- --gui; fi\n'
                            f'exec {cmd} "$@"\n')
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        for f in (base / "tabs").rglob("*.sh"):
            f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"Command: {launcher}")
        if P["desktop"]:
            P["icon"].parent.mkdir(parents=True, exist_ok=True)
            P["icon"].write_bytes(big_png)
            P["desktop"].parent.mkdir(parents=True, exist_ok=True)
            P["desktop"].write_text("[Desktop Entry]\nType=Application\nName=xutil\nComment=Install apps and set up your system\n"
                                    f"Exec={launcher} --gui\nIcon={P['icon']}\nTerminal=false\nCategories=System;Settings;Utility;\n"
                                    "Keywords=install;setup;apps;\nStartupWMClass=xutil\n")
            if shutil.which("update-desktop-database"):
                subprocess.run(["update-desktop-database", str(P["desktop"].parent)], check=False, stderr=subprocess.DEVNULL)
            print(f"App menu entry: {P['desktop']}")
        if str(launcher.parent) not in os.environ.get("PATH", "").split(os.pathsep):
            print(f"Note: add {launcher.parent} to your PATH to type 'xutil' in a terminal.")
    print("✓ Installed. Open xutil from your app menu" + (" or run: xutil" if not WINDOWS else "."))
    return 0


# ═════════════════════════════ cli ═════════════════════════════

def tree(nodes, depth=0):
    for n in nodes:
        print("  " * depth + (f"{n.name}/" if n.kind == "dir" else f"- {n.name}" + (f"  [{n.task_list}]" if n.task_list else "")))
        tree(n.children, depth + 1)


def check_catalog(tabs_dir):
    """Catalog test (SPEC 10.3): everything parses, scripts exist, names unique per OS, preconditions evaluate."""
    all_tabs = load_tabs(tabs_dir, validate=False)
    visible = load_tabs(tabs_dir, validate=True)
    seen, dup = {}, []
    for t in visible:
        for n in t.leaves():
            if n.name in seen:
                dup.append(n.name)
            seen[n.name] = n
    total = sum(1 for t in all_tabs for _ in t.leaves())
    print(f"catalog OK: {total} entries total, {len(seen)} visible on {OS_NAME}")
    if dup:
        sys.exit(f"duplicate visible names: {sorted(set(dup))}")


def main():
    ap = argparse.ArgumentParser(prog="xutil", description="Cross-platform apps and system setup for Windows, Linux and macOS.")
    ap.add_argument("-c", "--config", help="config file (TOML or JSON): auto_execute, skip_confirmation, size_bypass")
    ap.add_argument("-t", "--theme", choices=["default", "compatible"], default="default")
    ap.add_argument("-y", "--skip-confirmation", action="store_true")
    ap.add_argument("-u", "--override-validation", action="store_true", help="show all entries regardless of compatibility (UNSAFE)")
    ap.add_argument("-s", "--size-bypass", action="store_true")
    ap.add_argument("-r", "--bypass-root", action="store_true", help="skip the 'running as root' warning")
    ap.add_argument("--tabs-dir", default=None, help="use an external tabs/ folder instead of the built-in catalog")
    ap.add_argument("--gui", action="store_true", help="open the graphical window")
    ap.add_argument("--gui-theme", choices=list(THEMES), default=None, help="colour theme for the window (remembered afterwards)")
    ap.add_argument("--install", action="store_true", help="install xutil on this computer (menu entry + 'xutil' command)")
    ap.add_argument("--uninstall-self", action="store_true", help="remove an installed xutil")
    ap.add_argument("--system", action="store_true", help="with --install/--uninstall-self: all users (/usr/local, Program Files)")
    ap.add_argument("--askpass", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--list", action="store_true", help="print the catalog tree for this system and exit")
    ap.add_argument("--check", action="store_true", help="validate the catalog and exit")
    ap.add_argument("--dry-run", action="store_true", help="show what would run without executing")
    args = ap.parse_args()

    if args.askpass:
        return askpass()
    tabs_dir = Path(args.tabs_dir) if args.tabs_dir else (extract_embedded() if EMBEDDED else HERE / "tabs")
    if str(tabs_dir.parent) not in sys.path:
        sys.path.insert(0, str(tabs_dir.parent))  # xutil_icons.py lives next to tabs/ (also when embedded)
    if args.install or args.uninstall_self:
        return install_self(args.system, remove=args.uninstall_self)
    if args.check:
        return check_catalog(tabs_dir)
    tabs = load_tabs(tabs_dir, validate=not args.override_validation)
    if args.list:
        return tree(tabs)

    skip, size_bypass = args.skip_confirmation, args.size_bypass
    if args.config:
        nodes, cfg_skip, cfg_size = read_config(args.config, tabs)
        skip, size_bypass = skip or cfg_skip, size_bypass or cfg_size
        if nodes:
            enable_ansi()
            ok = confirm_and_run(nodes, skip, args.dry_run)
            sys.exit(0 if ok else 1)

    if args.gui or sys.stdin is None:  # windowed builds have no stdin
        try:
            return run_gui(gui_tabs(load_tabs(tabs_dir, validate=False), tabs), args)
        except ImportError:
            sys.exit("The window needs tkinter.\n  Fedora: sudo dnf install python3-tkinter\n  Debian/Ubuntu: sudo apt install python3-tk\n  Arch: sudo pacman -S tk\n  Windows: reinstall Python and keep 'tcl/tk' ticked")
    if args.list:
        return tree(tabs)

    skip, size_bypass = args.skip_confirmation, args.size_bypass
    if args.config:
        nodes, cfg_skip, cfg_size = read_config(args.config, tabs)
        skip, size_bypass = skip or cfg_skip, size_bypass or cfg_size
        if nodes:
            enable_ansi()
            ok = confirm_and_run(nodes, skip, args.dry_run)
            sys.exit(0 if ok else 1)
    if not sys.stdin.isatty():
        sys.exit("xutil's menu needs an interactive terminal. Use --gui for the window, or --list, --check, --config for non-interactive use.")
    if not WINDOWS and is_admin() and not args.bypass_root:
        if input("You are running xutil as root. Scripts run unprivileged by design; continue anyway? [y/N] ").lower() != "y":
            sys.exit(1)
    enable_ansi()
    App(tabs, args, size_bypass, skip).loop()


if __name__ == "__main__":
    main()
