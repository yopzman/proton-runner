# proton-runner

![Proton Runner](image.png)

Run auxiliary Windows tools (`.exe`, `.bat`, mod loaders, debugging utilities) and Linux commands inside a Steam game's Proton environment without modifying game launch options.

Supports live process detection: if the game is already running, `proton-runner` attaches to its active Proton environment and Wine prefix automatically. If offline, it reconstructs the environment from Steam libraries and `compatdata`.

Available as both a standalone Bash CLI tool and an ultra-fast, compact Qt6 desktop GUI (< 0.15s instant startup).

---

## What's New in v0.2.0

- **Instant Window Startup (< 0.15s):** Window renders immediately before background operations.
- **Progressive Discovery Pipeline:** Non-blocking `QThread` stages discover Steam roots, libraries, game ACF metadata, and Proton tools without freezing the UI.
- **Smart XDG Caching (`~/.cache/proton-runner/`):** Instant launch (< 1ms) with timestamp and mtime invalidation when libraries or manifests change.
- **Lazy Detail Inspector:** Detailed Wine prefix and Proton path resolution loaded on-demand per game.
- **Automated Test Suite:** Comprehensive unit & integration tests (`tests/`) for VDF/ACF parsers, caching, discovery, and CLI subcommands.

---

## Requirements

- **CLI Core:** Linux with Bash 4.4+ and standard POSIX utilities (`awk`, `sed`, `grep`, `pgrep`, `find`).
- **Desktop GUI:** Python 3.10+ with `PySide6` (`pip install PySide6` or distribution package like `python-pyside6`).

---

## Features

- **Process Auto-Detection:** Inspects `/proc/<pid>/environ` (safely via NUL-byte parsing) to capture live `STEAM_COMPAT_*` variables, `WINEPREFIX`, and Proton binary paths in real time.
- **Offline Environment Reconstruction:** Finds installed games, compatdata prefixes, and Proton versions across multiple Steam library folders (`libraryfolders.vdf`).
- **Path Handling:** Translates Linux absolute/relative paths and Windows drive paths (`C:\...`, `Z:\...`).
- **Prefix Utilities:** One-click / one-command shortcuts to launch `cmd.exe`, `winecfg`, `regedit`, or open the prefix directory.
- **Doctor Diagnostics:** Built-in health check for Steam libraries, filesystems (with NTFS warnings), prefix permissions, and Proton installations.
- **Robust Error Isolation:** Tolerates missing Steam roots, unmounted disks, and corrupted manifests gracefully.

---

## Installation

Clone the repository and copy the executables to your user `$PATH`:

```bash
git clone https://github.com/your-user/proton-runner.git
cd proton-runner

mkdir -p ~/.local/bin ~/.local/share/applications
cp proton-runner proton_runner_gui.py ~/.local/bin/
cp proton-runner.desktop ~/.local/share/applications/
chmod +x ~/.local/bin/proton-runner ~/.local/bin/proton_runner_gui.py
```

Make sure `~/.local/bin` is in your `$PATH` (in `~/.bashrc` or `~/.zshrc`):
```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

## Usage

### Desktop GUI
Launch from your application menu or run:
```bash
proton-runner
# or
proton-runner gui
```

#### Benchmark & Timing Mode
Inspect startup timings:
```bash
proton-runner gui --timing
```

### CLI Commands

#### Run an Executable in a Game's Prefix
```bash
# Linux path
proton-runner run 3513350 ~/Tools/mod_manager.exe

# Windows drive path
proton-runner run 3513350 "C:\Tools\tool.exe" --debug
```

#### Open Windows Command Prompt
```bash
proton-runner cmd 3513350
```

#### Run Wine Configuration or Tools
```bash
proton-runner wine 3513350 winecfg
proton-runner wine 3513350 regedit
proton-runner wine 3513350 explorer.exe
```

#### Run Native Linux Programs in Proton Environment
```bash
proton-runner native 3513350 bash
proton-runner native 3513350 env
```

#### Inspect Game Environment
```bash
# Summary info (paths, prefix, Proton version, filesystems)
proton-runner info 3513350

# Print exportable environment variables
proton-runner env 3513350
```

#### List Running Games
```bash
proton-runner list
```

#### Diagnostics
```bash
# Check global Steam/Proton setup
proton-runner doctor

# Check specific game prefix & filesystems
proton-runner doctor 3513350
```

---

## Running the Test Suite

Run the automated unit and integration tests:
```bash
python3 -m unittest discover -s tests -v
```

---

## License

This project is licensed under the [MIT License](LICENSE).
