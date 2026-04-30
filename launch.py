#!/usr/bin/env python3
"""Cross-platform local launcher for CAD/Assist.
Double-click on Windows/macOS/Linux or run `python launch.py`.
"""
from __future__ import annotations
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    proc = subprocess.run(cmd, cwd=str(cwd or ROOT), env=env)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> None:
    if sys.version_info < (3, 10):
        print("[cadassist] Python 3.10+ is required.")
        raise SystemExit(1)

    if platform.system().lower().startswith("win"):
        run(["cmd", "/c", "run_windows.bat"], cwd=ROOT)
        return

    env = os.environ.copy()
    start_sh = ROOT / "start.sh"
    if not start_sh.exists():
        print("[cadassist] start.sh is missing.")
        raise SystemExit(1)
    run(["bash", str(start_sh)], cwd=ROOT, env=env)


if __name__ == "__main__":
    main()
