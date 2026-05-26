"""Google Gemini CLI 安装脚本。

通过 npm 全局安装 ``@google/gemini-cli``。要求用户已装 Node.js + npm。

设计要点：
- ``detect()`` 调 ``gemini --version``，输出格式没文档化，
  退出 0 且有非空首行即视为已装
- 其余实现策略同 codex.py，差异只在包名与命令名
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Iterator

from scripts.cli_installers._base import InstallEvent, run_command


ID = "gemini"
NAME = "Gemini CLI"
DESCRIPTION = "Google 官方命令行（通过 npm 全局安装）"
REQUIRES = ["node", "npm"]

LAUNCH = {
    "label": "Gemini CLI",
    "host": "cmd",
    "raw_command": "gemini",
}


def detect() -> tuple[bool, str]:
    """探测 Gemini CLI 是否已安装。"""
    path = shutil.which("gemini")
    if path is None:
        return False, ""

    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            timeout=3.0,
            creationflags=flags,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, OSError):
        return False, ""

    if result.returncode != 0:
        return False, ""

    output = (result.stdout or result.stderr or "").strip()
    first_line = output.splitlines()[0] if output else ""
    if not first_line:
        return False, ""
    return True, first_line


def install() -> Iterator[InstallEvent]:
    """通过 npm 全局安装 Gemini CLI。"""
    yield InstallEvent("info", "开始安装 Gemini CLI（npm i -g @google/gemini-cli）")
    yield from run_command(["npm", "i", "-g", "@google/gemini-cli"])


def uninstall() -> Iterator[InstallEvent]:
    """通过 npm 全局卸载 Gemini CLI。"""
    yield InstallEvent("info", "开始卸载 Gemini CLI（npm uninstall -g @google/gemini-cli）")
    yield from run_command(["npm", "uninstall", "-g", "@google/gemini-cli"])
