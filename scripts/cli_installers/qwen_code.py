"""阿里 Qwen Code CLI 安装脚本。

通过 npm 全局安装 ``@qwen-code/qwen-code``。要求用户已装 Node.js + npm。

设计要点：
- ``detect()`` 调 ``qwen --version``，输出格式没文档化，
  退出 0 且有非空首行即视为已装
- 其余实现策略同 codex.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Iterator

from scripts.cli_installers._base import InstallEvent, run_command


ID = "qwen_code"
NAME = "Qwen Code"
DESCRIPTION = "阿里 Qwen Code 命令行（通过 npm 全局安装）"
REQUIRES = ["node", "npm"]

LAUNCH = {
    "label": "Qwen Code",
    "host": "cmd",
    "raw_command": "qwen",
}


def detect() -> tuple[bool, str]:
    """探测 Qwen Code 是否已安装。"""
    path = shutil.which("qwen")
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
    """通过 npm 全局安装 Qwen Code。"""
    yield InstallEvent("info", "开始安装 Qwen Code（npm i -g @qwen-code/qwen-code）")
    yield from run_command(["npm", "i", "-g", "@qwen-code/qwen-code"])


def uninstall() -> Iterator[InstallEvent]:
    """通过 npm 全局卸载 Qwen Code。"""
    yield InstallEvent("info", "开始卸载 Qwen Code（npm uninstall -g @qwen-code/qwen-code）")
    yield from run_command(["npm", "uninstall", "-g", "@qwen-code/qwen-code"])
