# linutil analysis (from `linutil-main.zip`)

## 1. What it is
A distro-agnostic Linux toolbox: a Rust terminal UI over a catalog of POSIX shell scripts. About 3,600 lines of Rust and about 73 shell scripts, grouped into five tabs (applications-setup, gaming, security, system-setup, utils).

## 2. Repository map
| Path | Role |
|---|---|
| `core/` (`linutil_core`) | Data model, TOML loading, precondition filtering, embeds `core/tabs/` into the binary with `include_dir!`, extracts it to a temp dir at startup, parses the user config |
| `tui/` (`linutil_tui`) | `ratatui` interface: tabs, search, preview, multi-select, confirmation, PTY runner (`portable_pty` + `vt100`) |
| `xtask/` | `cargo xtask docgen` generates docs from the catalog |
| `core/tabs/` | Catalog: `tabs.toml` (tab order), `<tab>/tab_data.toml`, scripts, shared libraries |
| `SPEC.md`, `docs/`, `.github/workflows/` | Spec, Hugo docs, CI (rust fmt/clippy/test, shellcheck, checkbashisms, typos) |

## 3. Runtime flow
1. Scripts are embedded at compile time and extracted to a temp dir at start.
2. `tabs.toml` lists the tab directories; each `tab_data.toml` becomes a tree of `ListNode`s.
3. Preconditions are evaluated; unsupported leaves and empty folders disappear.
4. The user browses (descriptions, source preview), multi-selects, and confirms.
5. Commands are composed into one shell program and run in a PTY with live output, a success/failure banner and Ctrl-C to kill.

## 4. Data model
- `Command::Raw(String)`: inline command. `Command::LocalFile{executable,args,file}`: script, interpreter taken from the **shebang** (default `/bin/sh -e`); a script whose interpreter is missing is hidden. `Command::None`: folder.
- Entry fields: `name`, `description`, one of `entries|script|command`, `preconditions[]`, `task_list`, `multi_select` (inherited from the parent).
- Preconditions: `matches` (true/false), `data` (`command_exists`, `file_exists`, `environment`, `containing_file`), `values[]`. All must pass.
- Task flags are informational warnings: `D FI FM I K MP RP SI SS P*`.

## 5. Script contract
POSIX `sh -e`; source `../common-script.sh` then call `checkEnv`, which detects architecture, the escalation tool (`sudo`/`doas`), the package manager (`PACKAGER`), distro (`DTYPE`) and AUR helper. Scripts run unprivileged and escalate only where needed, ask before destructive actions, back up config before overwriting, and are idempotent. The working directory is the script's folder.

## 6. CLI and config
Flags: `-c/--config`, `-t/--theme`, `-y/--skip-confirmation`, `-u/--override-validation`, `-s/--size-bypass`, `-m/--mouse`, `-r/--bypass-root`. The config accepts only `auto_execute` (display names), `skip_confirmation` and `size_bypass`, and unknown fields are an error. Missing names are silently ignored, which SPEC §8 itself flags as something to improve.

## 7. Why it cannot run on Windows as is
| Linux-only piece | Reason |
|---|---|
| `os::unix::fs::PermissionsExt` in `core/inner.rs` | Unix permissions API, does not compile on Windows |
| Shebang interpreters (`/bin/sh`) | No `sh` on Windows by default |
| `common-script.sh`: `sudo/doas`, `apt/dnf/pacman`, `/etc/os-release`, `id`, `groups` | All Linux concepts |
| Precondition catalog (`containing_file: /etc/os-release`, commands like `pacman`) | Describes Linux only |
| Scripts: systemd, Flatpak, GRUB, ufw, mounting, drivers | No Windows equivalent |

## 8. How xutil maps each concept to Windows
| linutil concept | xutil (Windows) | xutil (Linux/macOS) |
|---|---|---|
| Shebang picks interpreter | Extension picks it: `.ps1` runs with `pwsh`/`powershell -ExecutionPolicy Bypass -File` | `.sh` shebang, default `sh -e` |
| `common-script.sh` / `checkEnv` | `common-script.ps1`: `Get-Packager` (winget/choco/scoop), `Get-Arch`, `Test-CommandExists`, `Install-Package` | `common-script.sh` (apt/dnf/pacman/zypper/apk/brew) |
| Escalation tool (`sudo`) | No in-process elevation on Windows, so `Assert-Admin` fails fast with instructions; flag `A` marks admin tasks and the runner skips them (and says so) when not elevated | `sudo`/`doas` |
| Platform filtering | New precondition `data = "os"`. Same display name can exist per OS, so one config file works on both | same |
| Task flags | Added `A R REG WF WG FW` for Windows concerns | `D FI FM I K MP RP SI SS P*` kept |
| Root warning | n/a (admin is needed for some tasks) | Warns when run as root unless `-r` |
| PTY pane with vt100 | Tasks inherit the real console (interactive prompts just work); no embedded pane or kill-key | same |
| Embedded in binary | Plain folder; `python xutil.py` | same |
| `cargo test` catalog checks | `xutil.py --check` (parse, scripts exist, unique names, preconditions evaluate) | same |

## 9. Deliberate differences and limits
- Not a Rust binary: stdlib-only Python 3.11+ (`tomllib`) so one file runs everywhere. The catalog format is compatible in spirit (TOML, same precondition/flag semantics), so a Rust front-end could reuse it.
- A queued run **stops at the first failure** (linutil composes one shell program; failure behavior there is not specified in SPEC.md).
- Missing `auto_execute` names are reported, as SPEC §8 suggests.
- `args = [...]` is an extension: it lets one generic installer script serve many apps (data-and-script additions only).
- Not ported: gaming mods, desktop-environment installers, GRUB/zram/driver scripts, mouse support, docs generator, embedded log saving.
- Windows scripts were written to follow the documented cmdlets but were **not executed** in this build environment (no Windows host); the engine, catalog loading and Linux scripts were exercised.
