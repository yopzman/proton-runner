#!/usr/bin/env python3
"""
Proton Runner v0.3.0 - Fast, Asynchronous, Progressive Qt6 Interface
with Proton Provider Abstraction, Steam Linux Runtime Awareness,
and Environment Inspection.
"""

import os
import re
import sys
import json
import time
import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass, field, asdict

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QFileDialog,
    QTextEdit, QFrame, QCheckBox, QDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor

VERSION = "0.3.0"
SCRIPT_DIR = Path(__file__).resolve().parent
CLI_PATH = SCRIPT_DIR / "proton-runner"
if not CLI_PATH.exists():
    CLI_PATH = Path(shutil.which("proton-runner") or "proton-runner")

CACHE_DIR = Path.home() / ".cache" / "proton-runner"
CACHE_FILE = CACHE_DIR / "cache_v3.json"

TIMING_ENABLED = "--timing" in sys.argv or os.environ.get("PROTON_RUNNER_TIMING") == "1"
DEBUG_ENABLED = "--debug" in sys.argv or os.environ.get("PROTON_RUNNER_DEBUG") == "1"

IGNORED_KEYWORDS = (
    "steam linux runtime", "proton experimental", "proton hotfix",
    "proton easyanticheat", "steamworks common", "proton 10.",
    "proton 9.", "proton 8.", "proton 7.", "steamworks"
)

SENSITIVE_ENV_KEYS = (
    "password", "token", "secret", "auth", "credential", "cookie",
    "session", "private", "api_key"
)


def log_timing(tag, start_time):
    if TIMING_ENABLED:
        elapsed = time.perf_counter() - start_time
        print(f"[STARTUP] {tag}: {elapsed:.3f}s")


def log_debug(msg):
    if DEBUG_ENABLED:
        print(f"[DEBUG] {msg}")


# --- Proton Provider Abstraction & Helpers ---

def classify_proton_provider(name, path_str=""):
    """Classifies a Proton tool into its provider category."""
    name_l = (name or "").lower()
    path_l = (path_str or "").lower()

    if "ge-proton" in name_l or "ge-proton" in path_l:
        return "GE-Proton (GloriousEggroll)"
    elif "experimental" in name_l:
        return "Valve Proton (Experimental)"
    elif "hotfix" in name_l:
        return "Valve Proton (Hotfix)"
    elif re.search(r"proton\s*[0-9]+(\.[0-9]+)?", name_l) or "valve" in path_l:
        return "Valve Official Proton"
    elif "cachyos" in name_l or "tkg" in name_l or "lutris" in name_l:
        return "Custom / Community Build"
    else:
        return "Community / Custom Proton"


def detect_filesystem_type(path_obj):
    """Detects filesystem type (e.g. btrfs, ext4, ntfs, fuseblk) for a directory."""
    if not path_obj or not Path(path_obj).exists():
        return "unknown"
    try:
        p = subprocess.run(["df", "-T", str(path_obj)], capture_output=True, text=True, timeout=2)
        lines = p.stdout.strip().splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 2:
                return parts[1].lower()
    except Exception:
        pass
    return "unknown"


def sanitize_env_vars(raw_env):
    """Filters and sanitizes environment variables to prevent credential leakage."""
    sanitized = {}
    for k, v in raw_env.items():
        k_lower = k.lower()
        if any(s in k_lower for s in SENSITIVE_ENV_KEYS):
            sanitized[k] = "[REDACTED]"
        else:
            sanitized[k] = v
    return sanitized


# --- Structured GameEnvironment Model ---

@dataclass
class GameEnvironment:
    appid: str
    game_name: str
    steam_root: str = ""
    steam_type: str = "Native"
    library_path: str = ""
    install_path: str = ""
    compatdata_path: str = ""
    wineprefix: str = ""
    proton_path: str = ""
    proton_name: str = ""
    proton_provider: str = ""
    runtime_type: str = "Host (Native)"
    runtime_status: str = "Direct"
    game_fs: str = "unknown"
    pfx_fs: str = "unknown"
    is_ntfs_warn: bool = False
    is_running: bool = False
    pid: str = ""
    env_vars: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


# --- Fast Native Discovery Engine ---

def parse_vdf_paths(vdf_path):
    """Extract library paths from libraryfolders.vdf cleanly."""
    paths = []
    if not Path(vdf_path).is_file():
        return paths
    try:
        with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if '"path"' in line:
                    match = re.search(r'"path"\s+"([^"]+)"', line)
                    if match:
                        p = Path(match.group(1))
                        if p.exists():
                            paths.append(p.resolve())
    except Exception:
        pass
    return paths


def parse_acf_file(acf_path):
    """Parse single appmanifest_*.acf file."""
    appid = Path(acf_path).stem.replace("appmanifest_", "")
    name = f"AppID {appid}"
    last_played = 0
    installdir = ""

    try:
        content = Path(acf_path).read_text(encoding="utf-8", errors="ignore")
        name_match = re.search(r'"name"\s+"([^"]+)"', content)
        if name_match:
            name = name_match.group(1)

        played_match = re.search(r'"LastPlayed"\s+"(\d+)"', content)
        if played_match:
            last_played = int(played_match.group(1))

        dir_match = re.search(r'"installdir"\s+"([^"]+)"', content)
        if dir_match:
            installdir = dir_match.group(1)
    except Exception:
        pass

    return {
        "appid": appid,
        "name": name,
        "last_played": last_played,
        "installdir": installdir
    }


def get_steam_roots():
    """Discover all valid Steam roots (Native + Flatpak)."""
    candidates = [
        (Path.home() / ".local/share/Steam", "Native"),
        (Path.home() / ".steam/steam", "Native"),
        (Path.home() / ".steam/root", "Native"),
        (Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "Steam", "Native"),
        (Path.home() / ".var/app/com.valvesoftware.Steam/.steam/steam", "Flatpak"),
        (Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam", "Flatpak")
    ]
    seen = set()
    roots = []
    for c, stype in candidates:
        if c.exists():
            try:
                resolved = c.resolve()
                if resolved not in seen and resolved.exists():
                    seen.add(resolved)
                    roots.append({"path": resolved, "type": stype})
            except Exception:
                pass
    return roots


def find_libraries(steam_roots=None):
    """Discover all active Steam library folders across all roots."""
    roots = steam_roots or [r["path"] for r in get_steam_roots()]
    libs = set(roots)
    for root in roots:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        for p in parse_vdf_paths(vdf):
            libs.add(p)
    return list(libs)


def scan_games_in_libraries(libraries):
    """Scan all installed games across discovered Steam libraries."""
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
            game_meta = parse_acf_file(acf)
            appid = game_meta["appid"]
            if appid in seen_appids or not appid.isdigit():
                continue

            name_lower = game_meta["name"].lower()
            if any(k in name_lower for k in IGNORED_KEYWORDS):
                continue

            seen_appids.add(appid)
            game_meta["library"] = str(lib)
            games.append(game_meta)

    games.sort(key=lambda g: (-g["last_played"], g["name"].lower()))
    return games


def scan_proton_installations(libraries=None):
    """Locate Proton tools and classify provider metadata."""
    search_dirs = []
    roots = [r["path"] for r in get_steam_roots()]
    for r in roots:
        search_dirs.append((r / "compatibilitytools.d", "compatibilitytools.d"))
        search_dirs.append((r / "steamapps" / "common", "steamapps/common"))

    libs = libraries or find_libraries(roots)
    for lib in libs:
        search_dirs.append((lib / "compatibilitytools.d", "compatibilitytools.d"))
        search_dirs.append((lib / "steamapps" / "common", "steamapps/common"))

    protons = []
    seen_paths = set()
    for d, source_type in search_dirs:
        if not d.exists():
            continue
        try:
            for p in d.iterdir():
                if p.is_dir() and (p / "proton").is_file() and os.access(p / "proton", os.X_OK):
                    real_p = (p / "proton").resolve()
                    if real_p not in seen_paths:
                        seen_paths.add(real_p)
                        provider = classify_proton_provider(p.name, str(real_p))
                        ver = p.name
                        ver_file = p / "version"
                        if ver_file.is_file():
                            try:
                                ver = ver_file.read_text(encoding="utf-8").strip()
                            except Exception:
                                pass
                        protons.append({
                            "name": p.name,
                            "version": ver,
                            "path": str(real_p),
                            "directory": str(p),
                            "provider": provider,
                            "source": source_type
                        })
        except Exception:
            continue

    return protons


def scan_running_processes():
    """Fast /proc scanner returning appid -> {pid, env}."""
    running = {}
    my_uid = os.getuid()

    try:
        proc_entries = [p for p in Path("/proc").iterdir() if p.name.isdigit()]
    except Exception:
        return running

    for p in proc_entries:
        try:
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
            env_map = {}

            for item in items:
                if b"=" in item:
                    k, v = item.split(b"=", 1)
                    k_str = k.decode(errors="ignore")
                    v_str = v.decode(errors="ignore")
                    env_map[k_str] = v_str

                    if k_str == "STEAM_COMPAT_APP_ID":
                        detected_appid = v_str
                    elif k_str == "SteamAppId" and not detected_appid:
                        detected_appid = v_str
                    elif k_str == "SteamGameId" and not detected_appid:
                        detected_appid = v_str

            if not detected_appid and "WINEPREFIX" in env_map:
                wp = env_map["WINEPREFIX"]
                if "/compatdata/" in wp:
                    cand = wp.split("/compatdata/")[1].split("/")[0]
                    if cand.isdigit():
                        detected_appid = cand

            if detected_appid and detected_appid != "0":
                running[detected_appid] = {
                    "pid": p.name,
                    "env": env_map
                }

        except Exception:
            continue

    return running


# --- Smart XDG Cache (v3 Schema) ---

class SmartCache:
    @staticmethod
    def get_library_mtimes(libraries):
        mtimes = {}
        for lib in libraries:
            vdf = lib / "steamapps" / "libraryfolders.vdf"
            if vdf.is_file():
                try:
                    mtimes[str(vdf)] = vdf.stat().st_mtime
                except Exception:
                    pass
            steamapps = lib / "steamapps"
            if steamapps.is_dir():
                try:
                    mtimes[str(steamapps)] = steamapps.stat().st_mtime
                except Exception:
                    pass
        return mtimes

    @staticmethod
    def load():
        if not CACHE_FILE.is_file():
            return None
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("schema_version") != 3:
                return None

            # Expire after 24 hours
            if time.time() - data.get("timestamp", 0) > 86400:
                return None

            # Validate mtimes
            cached_mtimes = data.get("mtimes", {})
            for path_str, cached_mtime in cached_mtimes.items():
                p = Path(path_str)
                if p.exists():
                    if abs(p.stat().st_mtime - cached_mtime) > 0.001:
                        return None
                else:
                    return None

            return {
                "games": data.get("games", []),
                "protons": data.get("protons", []),
                "roots": data.get("roots", [])
            }
        except Exception:
            return None

    @staticmethod
    def save(games, libraries, protons=None, roots=None):
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            mtimes = SmartCache.get_library_mtimes(libraries)
            payload = {
                "schema_version": 3,
                "timestamp": time.time(),
                "mtimes": mtimes,
                "libraries": [str(l) for l in libraries],
                "games": games,
                "protons": protons or [],
                "roots": roots or []
            }
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f)
        except Exception:
            pass


# --- Background Worker Threads ---

class ProgressiveDiscoveryWorker(QThread):
    discovery_complete = Signal(list, list, list, dict)

    def run(self):
        t0 = time.perf_counter()
        roots_info = get_steam_roots()
        roots_paths = [r["path"] for r in roots_info]
        libs = find_libraries(roots_paths)
        games = scan_games_in_libraries(libs)
        protons = scan_proton_installations(libs)
        running = scan_running_processes()

        roots_serialized = [{"path": str(r["path"]), "type": r["type"]} for r in roots_info]
        SmartCache.save(games, libs, protons, roots_serialized)

        log_timing("Progressive discovery pipeline", t0)
        self.discovery_complete.emit(games, protons, roots_info, running)


class ProcessScanWorker(QThread):
    running_ready = Signal(dict)

    def run(self):
        running = scan_running_processes()
        self.running_ready.emit(running)


class DetailFetchWorker(QThread):
    detail_ready = Signal(str, object)

    def __init__(self, appid, live_proc_info=None, parent=None):
        super().__init__(parent)
        self.appid = str(appid)
        self.live_proc_info = live_proc_info or {}

    def run(self):
        env_obj = GameEnvironment(
            appid=self.appid,
            game_name=f"AppID {self.appid}",
            is_running=bool(self.live_proc_info),
            pid=str(self.live_proc_info.get("pid", ""))
        )

        try:
            p = subprocess.run([str(CLI_PATH), "info", self.appid], capture_output=True, text=True, timeout=5)
            for line in p.stdout.splitlines():
                if "Game name:" in line:
                    env_obj.game_name = line.split(":", 1)[1].strip()
                elif "Steam root:" in line:
                    env_obj.steam_root = line.split(":", 1)[1].strip()
                elif "Game directory:" in line:
                    env_obj.install_path = line.split(":", 1)[1].strip()
                elif "Compatdata:" in line:
                    env_obj.compatdata_path = line.split(":", 1)[1].strip()
                elif "Wine prefix:" in line:
                    env_obj.wineprefix = line.split(":", 1)[1].strip()
                elif "Proton:" in line:
                    env_obj.proton_path = line.split(":", 1)[1].strip()
        except Exception:
            pass

        # Proton metadata
        if env_obj.proton_path and env_obj.proton_path != "Not detected":
            p_dir = Path(env_obj.proton_path).parent
            env_obj.proton_name = p_dir.name
            env_obj.proton_provider = classify_proton_provider(p_dir.name, env_obj.proton_path)

        # Filesystem checks
        if env_obj.install_path:
            env_obj.game_fs = detect_filesystem_type(env_obj.install_path)
        if env_obj.wineprefix:
            env_obj.pfx_fs = detect_filesystem_type(env_obj.wineprefix)

        env_obj.is_ntfs_warn = env_obj.game_fs in ("ntfs", "fuseblk", "vfat", "exfat") or \
                               env_obj.pfx_fs in ("ntfs", "fuseblk", "vfat", "exfat")

        # Steam Linux Runtime / Pressure-Vessel detection
        live_env = self.live_proc_info.get("env", {})
        if live_env:
            if "PRESSURE_VESSEL_CONTAINER_DIR" in live_env or "STEAM_LINUX_RUNTIME_CONTAINER" in live_env:
                env_obj.runtime_type = "Steam Linux Runtime (Pressure-Vessel Container)"
                env_obj.runtime_status = "Container-Attached"
            elif "STEAM_RUNTIME" in live_env:
                env_obj.runtime_type = "Steam Linux Runtime (Legacy Scout)"
                env_obj.runtime_status = "Partially Reproducible"
            else:
                env_obj.runtime_type = "Host Native"
                env_obj.runtime_status = "Direct"
            env_obj.env_vars = sanitize_env_vars(live_env)
        else:
            env_obj.runtime_type = "Host / Offline Environment"
            env_obj.runtime_status = "Reconstructed"

        self.detail_ready.emit(self.appid, env_obj)


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


# --- Dialogs: Environment Inspector & Doctor ---

class EnvironmentDialog(QDialog):
    def __init__(self, env: GameEnvironment, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Environment Inspector - {env.game_name} ({env.appid})")
        self.resize(720, 560)
        self.env = env

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Overview Card
        card = QFrame()
        card.setObjectName("panel")
        card_l = QVBoxLayout(card)
        card_l.setSpacing(6)

        header_lbl = QLabel(f"<b>{env.game_name}</b> (AppID {env.appid})")
        header_lbl.setStyleSheet("font-size: 14px; color: #60a5fa;")
        card_l.addWidget(header_lbl)

        status_text = f"<span style='color: #22c55e;'>● Running (PID {env.pid})</span>" if env.is_running else "<span style='color: #9ca3af;'>○ Offline</span>"
        card_l.addWidget(QLabel(f"<b>Process Status:</b> {status_text}"))
        card_l.addWidget(QLabel(f"<b>Steam Root:</b> {env.steam_root} ({env.steam_type})"))
        card_l.addWidget(QLabel(f"<b>Proton Provider:</b> {env.proton_provider} ({env.proton_name or 'Default'})"))
        card_l.addWidget(QLabel(f"<b>Runtime Container:</b> {env.runtime_type} [{env.runtime_status}]"))

        fs_warn_html = ""
        if env.is_ntfs_warn:
            fs_warn_html = " <span style='color: #f59e0b; font-weight: bold;'>⚠ NTFS Detected (symlink limitations)</span>"
        card_l.addWidget(QLabel(f"<b>Filesystems:</b> Game: <code>{env.game_fs}</code> | Prefix: <code>{env.pfx_fs}</code>{fs_warn_html}"))

        layout.addWidget(card)

        # Tabs: Paths & Environment Variables
        tabs = QTabWidget()

        # Tab 1: Key Paths
        tab_paths = QWidget()
        tp_l = QVBoxLayout(tab_paths)
        tp_l.setSpacing(8)

        for label_text, val_text in [
            ("Game Install Directory", env.install_path),
            ("Compatdata Directory", env.compatdata_path),
            ("Wine Prefix (pfx)", env.wineprefix),
            ("Proton Executable", env.proton_path)
        ]:
            row = QHBoxLayout()
            lbl = QLabel(f"<b>{label_text}:</b>")
            lbl.setFixedWidth(160)
            val_edit = QLineEdit(val_text)
            val_edit.setReadOnly(True)
            btn_copy = QPushButton("Copy")
            btn_copy.setFixedWidth(60)
            btn_copy.clicked.connect(lambda _, v=val_text: QApplication.clipboard().setText(v))
            row.addWidget(lbl)
            row.addWidget(val_edit, 1)
            row.addWidget(btn_copy)
            tp_l.addLayout(row)

        tp_l.addStretch()
        tabs.addTab(tab_paths, "Key Paths")

        # Tab 2: Environment Variables
        tab_env = QWidget()
        te_l = QVBoxLayout(tab_env)

        filter_box = QHBoxLayout()
        filter_input = QLineEdit()
        filter_input.setPlaceholderText("Filter environment variables...")
        filter_box.addWidget(filter_input)
        te_l.addLayout(filter_box)

        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Variable", "Value"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)

        rows = sorted(env.env_vars.items())
        table.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            k_item = QTableWidgetItem(k)
            v_item = QTableWidgetItem(v)
            table.setItem(i, 0, k_item)
            table.setItem(i, 1, v_item)

        def filter_table(text):
            query = text.lower()
            for r in range(table.rowCount()):
                match = query in table.item(r, 0).text().lower() or query in table.item(r, 1).text().lower()
                table.setRowHidden(r, not match)

        filter_input.textChanged.connect(filter_table)
        te_l.addWidget(table)

        btn_copy_all = QPushButton("Copy All Variables (Shell Export Format)")
        btn_copy_all.clicked.connect(self.copy_all_env)
        te_l.addWidget(btn_copy_all)

        tabs.addTab(tab_env, f"Environment Variables ({len(rows)})")
        layout.addWidget(tabs, 1)

        # Bottom Bar
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

    def copy_all_env(self):
        export_lines = [f'export {k}="{v}"' for k, v in sorted(self.env.env_vars.items())]
        QApplication.clipboard().setText("\n".join(export_lines))
        QMessageBox.information(self, "Copied", "Environment variables copied to clipboard in export format.")


class DoctorDialog(QDialog):
    def __init__(self, appid=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Diagnostics {f'- AppID {appid}' if appid else ''}")
        self.resize(640, 460)
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


# --- Main Window ---

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        t_init = time.perf_counter()
        self.setWindowTitle(f"Proton Runner v{VERSION}")
        self.resize(660, 540)
        self.setMinimumSize(580, 460)

        self.games = []
        self.protons = []
        self.roots = []
        self.running_map = {}
        self.selected_appid = None
        self.current_env = None
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

        # Load instant cache
        cached = SmartCache.load()
        if cached:
            self.games = cached.get("games", [])
            self.protons = cached.get("protons", [])
            self.update_combo()

        # Non-blocking process polling
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
            QTextEdit, QTableWidget {
                background: #141416;
                color: #9ca3af;
                border: 1px solid #2d3039;
                border-radius: 4px;
                font-family: monospace;
                font-size: 11px;
                padding: 6px;
            }
            QTabWidget::pane {
                border: 1px solid #2d3039;
                background: #18191d;
            }
            QTabBar::tab {
                background: #202228;
                color: #9ca3af;
                padding: 6px 12px;
                border: 1px solid #2d3039;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background: #2a2d36;
                color: #f3f4f6;
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

        # 1. Top Bar: Game Selector & Auto-detect
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

        # 2. Environment Summary Card
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

        # 4. Quick Actions + Inspect Env
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

        btn_pfx = QPushButton("Open Prefix")
        btn_pfx.clicked.connect(self.open_pfx)
        tools.addWidget(btn_pfx)

        btn_inspect = QPushButton("Inspect Env")
        btn_inspect.clicked.connect(self.open_env_inspector)
        tools.addWidget(btn_inspect)

        layout.addLayout(tools)

        # 5. Output Log
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
        """Trigger asynchronous discovery pipeline."""
        if self.discovery_worker and self.discovery_worker.isRunning():
            return
        self.discovery_worker = ProgressiveDiscoveryWorker(parent=self)
        self.discovery_worker.discovery_complete.connect(self.on_discovery_complete)
        self.discovery_worker.start()

        self.trigger_process_scan()

    def trigger_process_scan(self):
        """Asynchronously scan /proc for running Steam games."""
        if self.process_worker and self.process_worker.isRunning():
            return
        self.process_worker = ProcessScanWorker(parent=self)
        self.process_worker.running_ready.connect(self.on_running_processes_ready)
        self.process_worker.start()

    def on_discovery_complete(self, games, protons, roots, running):
        self.games = games
        self.protons = protons
        self.roots = roots
        self.running_map = running
        self.update_combo()

    def on_running_processes_ready(self, running_map):
        changed = (set(self.running_map.keys()) != set(running_map.keys()))
        self.running_map = running_map

        if changed:
            self.update_combo()

        # Auto-switch if enabled
        if self.auto_detect and running_map:
            first_running = next(iter(running_map))
            if self.selected_appid != first_running:
                for i in range(self.game_combo.count()):
                    if self.game_combo.itemData(i) == first_running:
                        self.game_combo.setCurrentIndex(i)
                        break

    def update_combo(self):
        current_data = self.selected_appid or self.game_combo.currentData()

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
        self.selected_appid = str(appid)
        proc_info = self.running_map.get(str(appid), {})
        is_running = bool(proc_info)
        pid = proc_info.get("pid", "")

        if is_running:
            self.status_line.setText(f"<span style='color: #22c55e; font-weight: bold;'>● Running (PID {pid})</span> - Proton active")
        else:
            self.status_line.setText("<span style='color: #9ca3af;'>○ Offline</span> - Environment reconstructed on run")

        # Check in-memory cache
        if appid in self.details_cache:
            env = self.details_cache[appid]
            self.current_env = env
            p_display = f"{env.proton_provider} ({env.proton_name})" if env.proton_provider else (env.proton_name or "-")
            self.env_line.setText(f"<b>Proton:</b> {p_display}  |  <b>Prefix:</b> {env.wineprefix or '-'}")
            return

        self.env_line.setText("<b>Proton:</b> loading...  |  <b>Prefix:</b> loading...")

        if self.detail_worker and self.detail_worker.isRunning():
            self.detail_worker.terminate()

        self.detail_worker = DetailFetchWorker(appid, live_proc_info=proc_info, parent=self)
        self.detail_worker.detail_ready.connect(self.on_detail_ready)
        self.detail_worker.start()

    def on_detail_ready(self, appid, env: GameEnvironment):
        self.details_cache[appid] = env
        if self.selected_appid == appid:
            self.current_env = env
            p_display = f"{env.proton_provider} ({env.proton_name})" if env.proton_provider else (env.proton_name or "-")
            self.env_line.setText(f"<b>Proton:</b> {p_display}  |  <b>Prefix:</b> {env.wineprefix or '-'}")

    def open_env_inspector(self):
        if not self.selected_appid:
            return
        env = self.current_env
        if not env:
            proc_info = self.running_map.get(str(self.selected_appid), {})
            env = GameEnvironment(
                appid=str(self.selected_appid),
                game_name=f"AppID {self.selected_appid}",
                is_running=bool(proc_info),
                pid=str(proc_info.get("pid", ""))
            )
        dlg = EnvironmentDialog(env, self)
        dlg.exec()

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
        if self.current_env and self.current_env.wineprefix:
            pfx = Path(self.current_env.wineprefix)
            target = pfx / "drive_c" if (pfx / "drive_c").exists() else pfx
            if target.exists():
                subprocess.Popen(["xdg-open", str(target)])
                self.log(f">> Opened: {target}")
                return

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

    # Progressive background discovery
    win.start_background_discovery()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
