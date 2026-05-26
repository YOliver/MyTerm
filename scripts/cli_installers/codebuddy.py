"""腾讯 CodeBuddy Code CLI 安装脚本。

通过 npm 全局安装 ``@tencent-ai/codebuddy-code``。要求用户已装 Node.js 18+ 与 npm。

设计要点：
- 主命令名是 ``codebuddy``（官方文档也提供短别名 ``cbc``，但启动预设走主命令
  更直观——下拉框里出现"cbc"用户会困惑这是啥）
- ``detect()`` 调 ``codebuddy --version``，官方文档未固定版本输出格式，
  退出 0 且首行非空即视为已装，把首行原样展示
- 其余实现策略同 codex/gemini/qwen_code，差异只在包名与命令名
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Iterator

from scripts.cli_installers._base import InstallEvent, run_command


ID = "codebuddy"
NAME = "CodeBuddy Code"
DESCRIPTION = "腾讯 CodeBuddy Code 命令行（通过 npm 全局安装）"
REQUIRES = ["node", "npm"]

LAUNCH = {
    "label": "CodeBuddy Code",
    "host": "cmd",
    "raw_command": "codebuddy",
}


def detect() -> tuple[bool, str]:
    """探测 CodeBuddy Code 是否已安装。"""
    path = shutil.which("codebuddy")
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
    """通过 npm 全局安装 CodeBuddy Code。"""
    yield InstallEvent("info", "开始安装 CodeBuddy Code（npm i -g @tencent-ai/codebuddy-code）")
    yield from run_command(["npm", "i", "-g", "@tencent-ai/codebuddy-code"])


def uninstall() -> Iterator[InstallEvent]:
    """通过 npm 全局卸载 CodeBuddy Code。"""
    yield InstallEvent("info", "开始卸载 CodeBuddy Code（npm uninstall -g @tencent-ai/codebuddy-code）")
    yield from run_command(["npm", "uninstall", "-g", "@tencent-ai/codebuddy-code"])
