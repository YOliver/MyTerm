"""OpenAI Codex CLI 安装脚本。

通过 npm 全局安装 ``@openai/codex``。要求用户已装 Node.js + npm
（环境检测页可看到）。

设计要点：
- ``detect()`` 调 ``codex --version``：官方文档没固定版本输出格式，
  只要退出码 0 且有非空首行就视为已装，把首行原文给 UI 展示
- ``install()``/``uninstall()`` 套 _base.run_command 流式 yield npm 输出
- npm 全局装的命令在 Windows 上是 ``codex.cmd``，``shutil.which`` 会按
  PATHEXT 自动匹配，detect 里直接传 ``codex``
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Iterator

from scripts.cli_installers._base import InstallEvent, run_command


ID = "codex"
NAME = "Codex CLI"
DESCRIPTION = "OpenAI 官方命令行（通过 npm 全局安装）"
REQUIRES = ["node", "npm"]

# 安装成功后追加进 AI CLI 启动预设；卸载时按 installer_id 反查回收。
# host=cmd 与 claude_code 一致：npm 全局命令是 .cmd 包装器，cmd /K 启动最稳。
LAUNCH = {
    "label": "Codex CLI",
    "host": "cmd",
    "raw_command": "codex",
}


def detect() -> tuple[bool, str]:
    """探测 Codex CLI 是否已安装。

    返回 ``(is_installed, version_or_detail)``：
    - 已装 → ``(True, "<首行原文>")``
    - 未装 / 调用失败 / 退出非零 → ``(False, "")``

    --version 输出格式 OpenAI 没有公开稳定文档，这里不做强格式校验，
    任何非空首行都直接展示给用户——错杀概率极低，命令本身不存在的话
    shutil.which 已经先把它挡掉了。
    """
    path = shutil.which("codex")
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
    """通过 npm 全局安装 Codex CLI。"""
    yield InstallEvent("info", "开始安装 Codex CLI（npm i -g @openai/codex）")
    yield from run_command(["npm", "i", "-g", "@openai/codex"])


def uninstall() -> Iterator[InstallEvent]:
    """通过 npm 全局卸载 Codex CLI。

    npm uninstall 即使包不存在也返回 0；UI 卸载按钮只在已装时露出，
    正常用户不会触发"卸载未装包"的边界。
    """
    yield InstallEvent("info", "开始卸载 Codex CLI（npm uninstall -g @openai/codex）")
    yield from run_command(["npm", "uninstall", "-g", "@openai/codex"])
