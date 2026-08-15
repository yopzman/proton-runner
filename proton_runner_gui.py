#!/usr/bin/env python3
"""
Proton Runner - Compact, minimalist Qt6 interface for Steam Proton environments.
"""

import sys
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

IGNORED_KEYWORDS = [
    "steam linux runtime", "proton experimental", "proton hotfix",
    "proton easyanticheat", "steamworks common", "proton 10.",
    "proton 9.", "proton 8.", "proton 7.", "steamworks"
]


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
        self.setWindowTitle("Proton Runner")
        self.resize(640, 520)
        self.setMinimumSize(560, 440)

        self.games = []
        self.selected_appid = None
        self.auto_detect = True
        self.worker = None

        self.apply_theme()
        self.setup_ui()
        self.refresh_games()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_running)
        self.timer.start(1500)

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

        # 1. Top Bar: Target Game Selector & Auto-detect
        top = QHBoxLayout()
        top.setSpacing(8)

        lbl = QLabel("Game:")
        lbl.setStyleSheet("font-weight: 600; color: #9ca3af;")
        top.addWidget(lbl)

        self.game_combo = QComboBox()
        self.game_combo.currentIndexChanged.connect(self.on_combo_changed)
        top.addWidget(self.game_combo, 1)

        self.auto_cb = QCheckBox("Auto-detect")
        self.auto_cb.setChecked(True)
        self.auto_cb.toggled.connect(lambda v: setattr(self, "auto_detect", v))
        top.addWidget(self.auto_cb)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh_games)
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

        self.status_line = QLabel("Status: Idle")
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

    def refresh_games(self):
        self.games = []
        running_map = {}

        try:
            p = subprocess.run([str(CLI_PATH), "list"], capture_output=True, text=True)
            for line in p.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0].isdigit():
                    running_map[parts[0]] = parts[1]
        except Exception:
            pass

        steam_roots = [
            Path.home() / ".local/share/Steam",
            Path.home() / ".steam/steam",
            Path.home() / ".steam/root"
        ]

        libs = set()
        for root in steam_roots:
            if root.exists():
                libs.add(root)
                vdf = root / "steamapps/libraryfolders.vdf"
                if vdf.exists():
                    try:
                        with open(vdf, "r", encoding="utf-8", errors="ignore") as f:
                            for line in f:
                                if '"path"' in line:
                                    parts = line.split('"')
                                    if len(parts) >= 4 and Path(parts[3]).exists():
                                        libs.add(Path(parts[3]))
                    except Exception:
                        pass

        seen = set()
        for lib in libs:
            steamapps = lib / "steamapps"
            if steamapps.exists():
                for acf in steamapps.glob("appmanifest_*.acf"):
                    appid = acf.stem.replace("appmanifest_", "")
                    if appid in seen or not appid.isdigit():
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

                    seen.add(appid)
                    self.games.append({
                        "appid": appid,
                        "name": name,
                        "running": appid in running_map,
                        "pid": running_map.get(appid, ""),
                        "last_played": last_played
                    })

        self.games.sort(key=lambda g: (not g["running"], -g["last_played"], g["name"].lower()))

        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        for g in self.games:
            prefix = "● " if g["running"] else "○ "
            label = f"{prefix}{g['name']} ({g['appid']})"
            self.game_combo.addItem(label, g["appid"])
        self.game_combo.blockSignals(False)

        if self.game_combo.count() > 0:
            self.game_combo.setCurrentIndex(0)
            self.update_info(self.game_combo.currentData())

    def poll_running(self):
        if not self.auto_detect:
            return

        try:
            p = subprocess.run([str(CLI_PATH), "list"], capture_output=True, text=True, timeout=2)
            for line in p.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0].isdigit():
                    running_appid = parts[0]
                    if self.selected_appid != running_appid:
                        for i in range(self.game_combo.count()):
                            if self.game_combo.itemData(i) == running_appid:
                                self.game_combo.setCurrentIndex(i)
                                return
        except Exception:
            pass

    def on_combo_changed(self, idx):
        if idx >= 0:
            appid = self.game_combo.itemData(idx)
            self.selected_appid = appid
            self.update_info(appid)

    def update_info(self, appid):
        self.selected_appid = appid
        if not appid:
            return

        game = next((g for g in self.games if g["appid"] == appid), None)
        is_running = game["running"] if game else False
        pid = game.get("pid", "") if game else ""

        if is_running:
            self.status_line.setText(f"<span style='color: #22c55e; font-weight: bold;'>● Running (PID {pid})</span> - Proton active")
        else:
            self.status_line.setText("<span style='color: #9ca3af;'>○ Offline</span> - Environment will be reconstructed")

        try:
            p = subprocess.run([str(CLI_PATH), "info", str(appid)], capture_output=True, text=True)
            pfx = "-"
            proton = "-"
            for line in p.stdout.splitlines():
                if "Wine prefix:" in line:
                    pfx = line.split(":", 1)[1].strip()
                elif "Proton:" in line:
                    proton = Path(line.split(":", 1)[1].strip()).parent.name
            self.env_line.setText(f"<b>Proton:</b> {proton}  |  <b>Prefix:</b> {pfx}")
        except Exception:
            pass

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

        if self.worker and self.worker.isRunning():
            self.worker.stop()

        cmd = [str(CLI_PATH), "run", str(self.selected_appid), exe]
        args = self.args_input.text().strip()
        if args:
            import shlex
            cmd.extend(shlex.split(args))

        self.log(f">> {' '.join(cmd)}")
        self.btn_run.setEnabled(False)

        self.worker = CommandWorker(cmd, parent=self)
        self.worker.output.connect(self.log)
        self.worker.finished.connect(lambda: self.btn_run.setEnabled(True))
        self.worker.start()

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
            if self.worker and self.worker.isRunning():
                self.worker.stop()
            self.worker = CommandWorker([str(CLI_PATH), "cmd", str(self.selected_appid)], parent=self)
            self.worker.output.connect(self.log)
            self.worker.start()

    def run_wine(self, tool):
        if not self.selected_appid:
            return
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        self.log(f">> Running {tool} in prefix...")
        self.worker = CommandWorker([str(CLI_PATH), "wine", str(self.selected_appid), tool], parent=self)
        self.worker.output.connect(self.log)
        self.worker.start()

    def open_pfx(self):
        if not self.selected_appid:
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
        self.timer.stop()
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Proton Runner")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
