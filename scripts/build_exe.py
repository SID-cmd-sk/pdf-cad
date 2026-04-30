#!/usr/bin/env python3
"""One-command Windows EXE build for CAD Assist.
Usage: python scripts/build_exe.py
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DESKTOP = ROOT / "desktop"
BIN_DIR = DESKTOP / "bin"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("[build-exe]", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd or ROOT))
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def ensure(cmd: str) -> None:
    if shutil.which(cmd) is None:
        raise SystemExit(f"[build-exe] Missing required command: {cmd}")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("[build-exe] This script builds Windows .exe and must run on Windows.")
    if sys.version_info < (3, 10):
        raise SystemExit("[build-exe] Python 3.10+ required.")

    ensure("npm")
    ensure("pyinstaller")

    BIN_DIR.mkdir(parents=True, exist_ok=True)

    run([sys.executable, "-m", "pip", "install", "-r", str(BACKEND / "requirements.txt")])
    run(["npm", "install"], cwd=DESKTOP)
    run(["npm", "install"], cwd=FRONTEND)

    run([
        "pyinstaller", "--noconfirm", "--onefile", "--name", "cadassist-backend",
        "--add-data", "processing;processing",
        "--add-data", "learning;learning",
        "--add-data", "storage;storage",
        "server.py",
    ], cwd=BACKEND)

    backend_exe = BACKEND / "dist" / "cadassist-backend.exe"
    if not backend_exe.exists():
        raise SystemExit("[build-exe] Missing backend exe after pyinstaller build.")
    shutil.copy2(backend_exe, BIN_DIR / backend_exe.name)

    run(["npm", "run", "build"], cwd=FRONTEND)
    frontend_build = FRONTEND / "build"
    desktop_frontend = DESKTOP / "frontend-build"
    if desktop_frontend.exists():
        shutil.rmtree(desktop_frontend)
    shutil.copytree(frontend_build, desktop_frontend)

    run(["npx", "electron-builder", "--win", "--x64"], cwd=DESKTOP)

    print("[build-exe] Done. Installer in desktop/dist/")


if __name__ == "__main__":
    main()
