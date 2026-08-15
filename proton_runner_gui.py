#!/usr/bin/env python3
"""
Proton Runner - Fast, Asynchronous, Minimalist Qt6 Interface
for Steam Proton Environments.
"""

import os
import sys
import json
import time
import subprocess
import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QFileDialog,
    QTextEdit, QFrame, QCheckBox, QDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer

SCRIPT_DIR = Path(__file__).resolve().parent
CLI_PATH = SCRIPT_DIR / "proton-runner"
if not CLI_PATH.exists():
    CLI_PATH = Path(shutil.which("proton-runner") or "proton-runner")

CACHE_DIR = Path.home() / ".cache" / "proton-runner"
CACHE_FILE = CACHE_DIR / "games_cache.json"

TIMING_ENABLED = "--timing" in sys.argv or os.environ.get("PROTON_RUNNER_TIMING") == "1"

IGNORED_KEYWORDS = (
    "steam linux runtime", "proton experimental", "proton hotfix",
    "proton easyanticheat", "steamworks common", "proton 10.",
    "proton 9.", "proton 8.", "proton 7.", "steamworks"
)


def log_timing(tag, start_time):
    if TIMING_ENABLED:
        elapsed = time.perf_counter() - start_time
        print(f"[STARTUP] {tag}: {elapsed:.3f}s")


# --- Fast Native Python Discovery Helpers (Zero Subprocesses) ---

def get_steam_roots():
    candidates = [
        Path.home() / ".local/share/Steam",
        Path.home() / ".steam/steam",
        Path.home() / ".steam/root",
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "Steam",
        Path.home() / ".var/app/com.valvesoftware.Steam/.steam/steam",
        Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam"
    ]
    seen = set()
    roots = []
    for c in candidates:
        if c.exists():
            try:
                resolved = c.resolve()
                if resolved not in seen and resolved.exists():
                    seen.add(resolved)
                    roots.append(resolved)
            except Exception:
                pass
    return roots


def find_all_libraries():
    roots = get_steam_roots()
    libs = set(roots)
    for root in roots:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            try:
                with open(vdf, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if '"path"' in line:
                            parts = line.split('"')
                            if len(parts) >= 4:
                                p = Path(parts[3])
                                if p.exists():
                                    libs.add(p.resolve())
            except Exception:
                pass
    return list(libs)


def scan_installed_games_fast(libraries):
    """Fast native Python parser for appmanifest_*.acf without shelling out."""
    games = []
    seen_appids = set()

    for lib in libraries:
        steamapps = lib / "steamapps"
        if not steamapps.exists():
            continue

        try:
            acf_files = list(steamapps.glob("appmanifest_*.acf"))
        except Exception:
            continue

        for acf in acf_files:
            appid = acf.stem.replace("appmanifest_", "")
            if appid in seen_appids or not appid.isdigit():
                continue

            name = f"AppID {appid}"
            last_played = 0
            try:
                with open(acf, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if '"name"' in line:
                            parts = line.split('"')
                            if len(parts) >= 4:
                                name = parts[3]
                        elif '"LastPlayed"' in line:
                            parts = line.split('"')
                            if len(parts) >= 4 and parts[3].isdigit():
                                last_played = int(parts[3])
            except Exception:
                pass

            name_lower = name.lower()
            if any(k in name_lower for k in IGNORED_KEYWORDS):
                continue

            seen_appids.add(appid)
            games.append({
                "appid": appid,
                "name": name,
                "last_played": last_played,
                "library": str(lib)
            })

    games.sort(key=lambda g: (-g["last_played"], g["name"].lower()))
    return games


def scan_running_games_fast():
    """Fast native /proc parser to detect running Steam games without Bash overhead."""
    running = {}
    my_uid = os.getuid()

    try:
        proc_entries = [p for p in Path("/proc").iterdir() if p.name.isdigit()]
    except Exception:
        return running

    for p in proc_entries:
        try:
            # Check owner
            stat = p.stat()
            if stat.st_uid != my_uid:
                continue

            environ_file = p / "environ"
            if not environ_file.exists():
                continue

            with open(environ_file, "rb") as f:
                data = f.read()

            items = data.split(b"\x00")
            detected_appid = None

            for item in items:
                if item.startswith(b"STEAM_COMPAT_APP_ID="):
                    detected_appid = item[20:].decode(errors="ignore")
                    break
                elif item.startswith(b"SteamAppId="):
                    detected_appid = item[11:].decode(errors="ignore")
                    break
                elif item.startswith(b"SteamGameId="):
                    detected_appid = item[12:].decode(errors="ignore")
                    break
                elif item.startswith(b"WINEPREFIX=") and b"/compatdata/" in item:
                    val = item[11:].decode(errors="ignore")
                    parts = val.split("/compatdata/")
                    if len(parts) > 1:
                        cand = parts[1].split("/")[0]
                        if cand.isdigit():
                            detected_appid = cand
                            break

            if detected_appid and detected_appid != "0":
                running[detected_appid] = p.name

        except Exception:
            continue

    return running


# --- Cache Management ---

def load_cache():
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Valid if younger than 24 hours
            if time.time() - data.get("timestamp", 0) < 86400:
                return data.get("games", [])
    except Exception:
        pass
    return None


def save_cache(games):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"timestamp": time.time(), "games": games}, f)
    except Exception:
        pass


# --- Asynchronous Worker Threads ---

class FastDiscoveryWorker(QThread):
    games_ready = Signal(list)

    def run(self):
        t0 = time.perf_counter()
        libs = find_all_libraries()
        games = scan_installed_games_fast(libs)
        save_cache(games)
        log_timing("Background library & game discovery", t0)
        self.games_ready.emit(games)


class ProcessScanWorker(QThread):
    running_ready = Signal(dict)

    def run(self):
        running = scan_running_games_fast()
        self.running_ready.emit(running)


class DetailFetchWorker(QThread):
    detail_ready = Signal(str, dict)

    def __init__(self, appid, parent=None):
        super().__init__(parent)
        self.appid = appid

    def run(self):
        info_data = {"proton": "-", "prefix": "-", "status": "Offline"}
        try:
            p = subprocess.run([str(CLI_PATH), "info", str(self.appid)], capture_output=True, text=True, timeout=5)
            for line in p.stdout.splitlines():
                if "Wine prefix:" in line:
                    info_data["prefix"] = line.split(":", 1)[1].strip()
                elif "Proton:" in line:
                    info_data["proton"] = Path(line.split(":", 1)[1].strip()).parent.name
        except Exception as e:
            info_data["error"] = str(e)

        self.detail_ready.emit(self.appid, info_data)


class CommandWorker(QThread):
    output = Signal(str)
    finished = Signal(int)

    def __init__(self, command, cwd=None, parent=None):
        super().__init__(parent)
        self.command = command
        self.cwd = cwd
        self._process = None

    def run(self):
        try:
            self._process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                bufsize=1,
                universal_newlines=True
            )
            for line in self._process.stdout:
                self.output.emit(line)
            self._process.wait()
            self.finished.emit(self._process.returncode)
        except Exception as e:
            self.output.emit(f"Error: {e}\n")
            self.finished.emit(1)

    def stop(self):
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass
        self.terminate()
        self.wait(500)


class DoctorDialog(QDialog):
    def __init__(self, appid=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Diagnostics {f'- AppID {appid}' if appid else ''}")
        self.resize(600, 420)
        self.appid = appid
        self.worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("""
            QTextEdit {
                background: #141416;
                color: #d1d5db;
                font-family: monospace;
                font-size: 11px;
                border: 1px solid #2e3038;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        layout.addWidget(self.log)

        bottom = QHBoxLayout()
        refresh = QPushButton("Re-run")
        refresh.clicked.connect(self.run_diag)
        bottom.addWidget(refresh)
        bottom.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        layout.addLayout(bottom)

        self.run_diag()

    def run_diag(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()

        self.log.clear()
        cmd = [str(CLI_PATH), "doctor"]
        if self.appid:
            cmd.append(str(self.appid))
        self.worker = CommandWorker(cmd, parent=self)
        self.worker.output.connect(self.log.append)
        self.worker.start()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        super().closeEvent(event)

    def reject(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        super().reject()

    def accept(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        super().accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        t_init = time.perf_counter()
        self.setWindowTitle("Proton Runner")
        self.resize(640, 520)
        self.setMinimumSize(560, 440)

        self.games = []
        self.running_map = {}
        self.selected_appid = None
        self.auto_detect = True
        self.details_cache = {}

        # Workers
        self.discovery_worker = None
        self.process_worker = None
        self.detail_worker = None
        self.cmd_worker = None

        self.apply_theme()
        self.setup_ui()
        log_timing("MainWindow UI setup", t_init)

        # Load instant disk cache if present
        cached_games = load_cache()
        if cached_games:
            self.games = cached_games
            self.update_combo()

        # Background process polling timer (non-blocking)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.trigger_process_scan)
        self.poll_timer.start(2000)

    def apply_theme(self):
        self.setStyleSheet("""
            QMainWindow, QDialog {
                background: #18191d;
                color: #e5e7eb;
            }
            QWidget {
                font-size: 12px;
                color: #e5e7eb;
            }
            QFrame#panel {
                background: #202228;
                border: 1px solid #2d3039;
                border-radius: 6px;
                padding: 10px;
            }
            QLineEdit, QComboBox {
                background: #141416;
                color: #f3f4f6;
                border: 1px solid #333642;
                border-radius: 4px;
                padding: 5px 8px;
                min-height: 18px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #3b82f6;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background: #1e2026;
                color: #f3f4f6;
                selection-background-color: #2563eb;
                border: 1px solid #333642;
            }
            QPushButton {
                background: #2a2d36;
                color: #e5e7eb;
                border: 1px solid #383c48;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #343844;
                border-color: #484d5c;
            }
            QPushButton:pressed {
                background: #22252c;
            }
            QPushButton#primaryBtn {
                background: #2563eb;
                color: #ffffff;
                border: 1px solid #1d4ed8;
                font-weight: 600;
            }
            QPushButton#primaryBtn:hover {
                background: #1d4ed8;
            }
            QPushButton#primaryBtn:disabled {
                background: #1e3a6e;
                color: #94a3b8;
            }
            QTextEdit {
                background: #141416;
                color: #9ca3af;
                border: 1px solid #2d3039;
                border-radius: 4px;
                font-family: monospace;
                font-size: 11px;
                padding: 6px;
            }
            QCheckBox {
                color: #9ca3af;
            }
        """)

    def setup_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 1. Top Bar: Game Selector & Controls
        top = QHBoxLayout()
        top.setSpacing(8)

        lbl = QLabel("Game:")
        lbl.setStyleSheet("font-weight: 600; color: #9ca3af;")
        top.addWidget(lbl)

        self.game_combo = QComboBox()
        self.game_combo.addItem("Detecting Steam games...", None)
        self.game_combo.currentIndexChanged.connect(self.on_combo_changed)
        top.addWidget(self.game_combo, 1)

        self.auto_cb = QCheckBox("Auto-detect")
        self.auto_cb.setChecked(True)
        self.auto_cb.toggled.connect(lambda v: setattr(self, "auto_detect", v))
        top.addWidget(self.auto_cb)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.start_background_discovery)
        top.addWidget(btn_refresh)

        btn_diag = QPushButton("Doctor")
        btn_diag.clicked.connect(lambda: DoctorDialog(self.selected_appid, self).exec())
        top.addWidget(btn_diag)

        layout.addLayout(top)

        # 2. Environment Info Card
        self.info_panel = QFrame()
        self.info_panel.setObjectName("panel")
        info_l = QVBoxLayout(self.info_panel)
        info_l.setContentsMargins(10, 8, 10, 8)
        info_l.setSpacing(4)

        self.status_line = QLabel("Status: Detecting...")
        self.status_line.setStyleSheet("color: #9ca3af; font-size: 11px;")
        info_l.addWidget(self.status_line)

        self.env_line = QLabel("Proton: - | Prefix: -")
        self.env_line.setStyleSheet("color: #6b7280; font-size: 11px;")
        self.env_line.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_l.addWidget(self.env_line)

        layout.addWidget(self.info_panel)

        # 3. Executable Runner Panel
        run_panel = QFrame()
        run_panel.setObjectName("panel")
        run_l = QVBoxLayout(run_panel)
        run_l.setContentsMargins(10, 10, 10, 10)
        run_l.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        lbl_exe = QLabel("Executable:")
        lbl_exe.setFixedWidth(75)
        row1.addWidget(lbl_exe)

        self.exe_input = QLineEdit()
        self.exe_input.setPlaceholderText("/path/to/program.exe or C:\\Tools\\tool.exe")
        row1.addWidget(self.exe_input, 1)

        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self.browse_exe)
        row1.addWidget(btn_browse)
        run_l.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        lbl_args = QLabel("Arguments:")
        lbl_args.setFixedWidth(75)
        row2.addWidget(lbl_args)

        self.args_input = QLineEdit()
        self.args_input.setPlaceholderText("Optional arguments (e.g. -windowed)")
        row2.addWidget(self.args_input, 1)

        self.btn_run = QPushButton("Run in Proton")
        self.btn_run.setObjectName("primaryBtn")
        self.btn_run.clicked.connect(self.run_program)
        row2.addWidget(self.btn_run)
        run_l.addLayout(row2)

        layout.addWidget(run_panel)

        # 4. Quick Actions
        tools = QHBoxLayout()
        tools.setSpacing(6)

        btn_cmd = QPushButton("CMD Shell")
        btn_cmd.clicked.connect(self.run_cmd)
        tools.addWidget(btn_cmd)

        btn_winecfg = QPushButton("Winecfg")
        btn_winecfg.clicked.connect(lambda: self.run_wine("winecfg"))
        tools.addWidget(btn_winecfg)

        btn_reg = QPushButton("Regedit")
        btn_reg.clicked.connect(lambda: self.run_wine("regedit"))
        tools.addWidget(btn_reg)

        btn_pfx = QPushButton("Open Prefix Folder")
        btn_pfx.clicked.connect(self.open_pfx)
        tools.addWidget(btn_pfx)

        layout.addLayout(tools)

        # 5. Log Output
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("Output Log:"))
        log_header.addStretch()
        btn_clear = QPushButton("Clear")
        btn_clear.setStyleSheet("padding: 2px 8px; font-size: 10px;")
        btn_clear.clicked.connect(lambda: self.log_view.clear())
        log_header.addWidget(btn_clear)
        layout.addLayout(log_header)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)

    def log(self, text):
        self.log_view.append(text.rstrip())

    def start_background_discovery(self):
        """Asynchronously scan Steam libraries without blocking the Qt event loop."""
        if self.discovery_worker and self.discovery_worker.isRunning():
            return
        self.discovery_worker = FastDiscoveryWorker(parent=self)
        self.discovery_worker.games_ready.connect(self.on_games_discovered)
        self.discovery_worker.start()

        # Trigger process scan simultaneously
        self.trigger_process_scan()

    def trigger_process_scan(self):
        """Asynchronously scan /proc for running Steam games without blocking."""
        if self.process_worker and self.process_worker.isRunning():
            return
        self.process_worker = ProcessScanWorker(parent=self)
        self.process_worker.running_ready.connect(self.on_running_processes_ready)
        self.process_worker.start()

    def on_games_discovered(self, games):
        self.games = games
        self.update_combo()

    def on_running_processes_ready(self, running_map):
        changed = (self.running_map != running_map)
        self.running_map = running_map

        if changed:
            self.update_combo()

        # Check if auto-detection should switch
        if self.auto_detect and running_map:
            first_running = next(iter(running_map))
            if self.selected_appid != first_running:
                for i in range(self.game_combo.count()):
                    if self.game_combo.itemData(i) == first_running:
                        self.game_combo.setCurrentIndex(i)
                        break

    def update_combo(self):
        current_data = self.selected_appid or self.game_combo.currentData()

        # Sort: running first, then recency
        sorted_games = sorted(
            self.games,
            key=lambda g: (g["appid"] not in self.running_map, -g.get("last_played", 0), g["name"].lower())
        )

        self.game_combo.blockSignals(True)
        self.game_combo.clear()

        if not sorted_games:
            self.game_combo.addItem("No installed games found", None)
        else:
            select_idx = 0
            for i, g in enumerate(sorted_games):
                is_running = g["appid"] in self.running_map
                dot = "● " if is_running else "○ "
                label = f"{dot}{g['name']} ({g['appid']})"
                self.game_combo.addItem(label, g["appid"])
                if g["appid"] == current_data:
                    select_idx = i

            self.game_combo.setCurrentIndex(select_idx)

        self.game_combo.blockSignals(False)

        selected = self.game_combo.currentData()
        if selected:
            self.selected_appid = selected
            self.update_info_lazy(selected)

    def on_combo_changed(self, idx):
        if idx >= 0:
            appid = self.game_combo.itemData(idx)
            if appid:
                self.selected_appid = appid
                self.update_info_lazy(appid)

    def update_info_lazy(self, appid):
        """Updates game info on-demand without freezing the UI."""
        self.selected_appid = appid
        is_running = appid in self.running_map
        pid = self.running_map.get(appid, "")

        if is_running:
            self.status_line.setText(f"<span style='color: #22c55e; font-weight: bold;'>● Running (PID {pid})</span> - Proton active")
        else:
            self.status_line.setText("<span style='color: #9ca3af;'>○ Offline</span> - Environment reconstructed on run")

        # If already cached in memory, show instantly
        if appid in self.details_cache:
            data = self.details_cache[appid]
            self.env_line.setText(f"<b>Proton:</b> {data.get('proton', '-')}  |  <b>Prefix:</b> {data.get('prefix', '-')}")
            return

        self.env_line.setText("<b>Proton:</b> loading...  |  <b>Prefix:</b> loading...")

        # Fetch in background thread
        if self.detail_worker and self.detail_worker.isRunning():
            self.detail_worker.terminate()

        self.detail_worker = DetailFetchWorker(appid, parent=self)
        self.detail_worker.detail_ready.connect(self.on_detail_ready)
        self.detail_worker.start()

    def on_detail_ready(self, appid, data):
        self.details_cache[appid] = data
        if self.selected_appid == appid:
            self.env_line.setText(f"<b>Proton:</b> {data.get('proton', '-')}  |  <b>Prefix:</b> {data.get('prefix', '-')}")

    def browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Executable", str(Path.home()),
            "Executables (*.exe *.bat *.cmd *.msi);;All Files (*)"
        )
        if path:
            self.exe_input.setText(path)

    def run_program(self):
        if not self.selected_appid:
            return
        exe = self.exe_input.text().strip()
        if not exe:
            self.log("Please specify an executable to run.")
            return

        if self.cmd_worker and self.cmd_worker.isRunning():
            self.cmd_worker.stop()

        cmd = [str(CLI_PATH), "run", str(self.selected_appid), exe]
        args = self.args_input.text().strip()
        if args:
            import shlex
            cmd.extend(shlex.split(args))

        self.log(f">> {' '.join(cmd)}")
        self.btn_run.setEnabled(False)

        self.cmd_worker = CommandWorker(cmd, parent=self)
        self.cmd_worker.output.connect(self.log)
        self.cmd_worker.finished.connect(lambda: self.btn_run.setEnabled(True))
        self.cmd_worker.start()

    def run_cmd(self):
        if not self.selected_appid:
            return
        term = shutil.which("konsole") or shutil.which("xterm") or shutil.which("gnome-terminal")
        if term:
            if "konsole" in term:
                subprocess.Popen([term, "-e", str(CLI_PATH), "cmd", str(self.selected_appid)])
            else:
                subprocess.Popen([term, "-e", f"{CLI_PATH} cmd {self.selected_appid}"])
            self.log(f">> Spawned cmd.exe in {Path(term).name}")
        else:
            if self.cmd_worker and self.cmd_worker.isRunning():
                self.cmd_worker.stop()
            self.cmd_worker = CommandWorker([str(CLI_PATH), "cmd", str(self.selected_appid)], parent=self)
            self.cmd_worker.output.connect(self.log)
            self.cmd_worker.start()

    def run_wine(self, tool):
        if not self.selected_appid:
            return
        if self.cmd_worker and self.cmd_worker.isRunning():
            self.cmd_worker.stop()
        self.log(f">> Running {tool} in prefix...")
        self.cmd_worker = CommandWorker([str(CLI_PATH), "wine", str(self.selected_appid), tool], parent=self)
        self.cmd_worker.output.connect(self.log)
        self.cmd_worker.start()

    def open_pfx(self):
        if not self.selected_appid:
            return
        cached = self.details_cache.get(self.selected_appid, {})
        pfx_str = cached.get("prefix", "-")
        if pfx_str and pfx_str != "-":
            pfx = Path(pfx_str)
            target = pfx / "drive_c" if (pfx / "drive_c").exists() else pfx
            if target.exists():
                subprocess.Popen(["xdg-open", str(target)])
                self.log(f">> Opened: {target}")
                return

        # Fallback to CLI lookup in thread
        try:
            p = subprocess.run([str(CLI_PATH), "info", str(self.selected_appid)], capture_output=True, text=True)
            for line in p.stdout.splitlines():
                if "Wine prefix:" in line:
                    pfx = Path(line.split(":", 1)[1].strip())
                    target = pfx / "drive_c" if (pfx / "drive_c").exists() else pfx
                    if target.exists():
                        subprocess.Popen(["xdg-open", str(target)])
                        self.log(f">> Opened: {target}")
                        return
            self.log("Prefix directory not found.")
        except Exception as e:
            self.log(f"Error: {e}")

    def closeEvent(self, event):
        self.poll_timer.stop()
        for w in [self.discovery_worker, self.process_worker, self.detail_worker, self.cmd_worker]:
            if w and w.isRunning():
                w.stop() if hasattr(w, "stop") else w.terminate()
        super().closeEvent(event)


def main():
    t0 = time.perf_counter()
    app = QApplication(sys.argv)
    app.setApplicationName("Proton Runner")
    log_timing("Qt Application initialization", t0)

    t_win = time.perf_counter()
    win = MainWindow()
    win.show()
    log_timing("MainWindow constructed & shown on screen", t_win)
    log_timing("Total time to interactive window", t0)

    # Trigger background non-blocking discovery after window is rendered
    win.start_background_discovery()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
