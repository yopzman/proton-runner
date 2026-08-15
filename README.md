# proton-runner

![Proton Runner](image.png)

Run auxiliary Windows tools (`.exe`, `.bat`, mod loaders, debugging utilities) and Linux commands inside a Steam game's Proton environment without modifying game launch options.

Supports live process detection: if the game is already running, `proton-runner` attaches to its active Proton environment and Wine prefix automatically. If offline, it reconstructs the environment from Steam libraries and `compatdata`.

Available as both a standalone Bash CLI tool and an ultra-fast, compact Qt6 desktop GUI (< 0.15s instant startup).

---

## What's New in v0.3.0

- **Proton Provider Abstraction:** Automatically classifies Proton builds (`Valve Official`, `GE-Proton`, `Proton Experimental`, `Custom / Community`).
- **Steam Linux Runtime (SLR) & Pressure-Vessel Awareness:** Detects container runtime status (`Container-Attached`, `Direct`, or `Host-Fallback`) with compatibility reports.
- **GUI Environment Inspector:** Interactive dialog in the GUI with key paths, container status, filesystem types, and a search-filterable environment variable table with 1-click copy.
- **Flatpak & Multi-Steam Support:** Detects Native and Flatpak Steam installations (`--steam-root <PATH>`).
- **Filesystem & NTFS Diagnostics:** Detects underlying filesystem types for game directories and compatdata prefixes with NTFS warnings.
- **Structured Debug Mode:** `--debug` / `PROTON_RUNNER_DEBUG=1` without leaking sensitive credentials or tokens.
- **Expanded Automated Test Suite:** 27 unit & integration tests covering providers, runtimes, filesystems, parsers, caching, and CLI commands.

---

## Requirements

- **CLI Core:** Linux with Bash 4.4+ and standard POSIX utilities (`awk`, `sed`, `grep`, `pgrep`, `find`, `df`).
- **Desktop GUI:** Python 3.10+ with `PySide6` (`pip install PySide6` or distribution package like `python-pyside6`).

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

#### Benchmark & Debug Modes
```bash
proton-runner gui --timing
proton-runner gui --debug
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

#### Diagnostics & Health Check
```bash
# Check global Steam/Proton setup
proton-runner doctor

# Check specific game prefix & filesystems
proton-runner doctor 3513350
```

#### Targeting Specific Steam Installations (Flatpak / Custom)
```bash
proton-runner --steam-root ~/.var/app/com.valvesoftware.Steam/.local/share/Steam list
```

---

## Project Structure

```text
proton-runner/
├── proton-runner              # Standalone POSIX Bash CLI script
├── proton_runner_gui.py       # Asynchronous Qt6 (PySide6) GUI application
├── proton-runner.desktop      # Freedesktop application entry
├── tests/                     # Automated unit and integration test suite
│   ├── test_cli.py
│   ├── test_parsers.py
│   ├── test_cache.py
│   ├── test_discovery.py
│   ├── test_proton_providers.py
│   ├── test_runtime.py
│   ├── test_environment_model.py
│   └── test_filesystem.py
├── LICENSE                    # MIT License
└── README.md
```

---

## Running the Test Suite

Run the full automated test suite:
```bash
python3 -m unittest discover -s tests -v
```

Run individual test modules:
```bash
python3 -m unittest tests/test_proton_providers.py -v
python3 -m unittest tests/test_runtime.py -v
python3 -m unittest tests/test_environment_model.py -v
```

---

## License

This project is licensed under the [MIT License](LICENSE).
