"""Claude Code CLI 安装脚本。

通过 npm 全局安装 ``@anthropic-ai/claude-code``。要求用户已装 Node.js + npm
（环境检测页可看到）。

设计要点：
- ``detect()`` 调 ``claude --version``，超时 3s 内拿不到版本就视为未装
- ``install()`` 直接 yield 出 ``run_command`` 的事件流，UI 实时打印 npm 输出
- npm 全局装的命令在 Windows 上是 ``claude.cmd``，``shutil.which`` 会按
  PATHEXT 自动匹配，所以 detect 里直接用 ``claude``
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Iterator

from scripts.cli_installers._base import InstallEvent, run_command


ID = "claude_code"
NAME = "Claude Code"
DESCRIPTION = "Anthropic 官方命令行（通过 npm 全局安装）"
REQUIRES = ["node", "npm"]

# 安装成功后自动追加到 AI CLI 配置的预设。
# claude 是 npm 全局装的 .cmd，host="cmd" 走 cmd /K 启动；用户可在设置里改 label。
# UI 通过 store.shell_presets.add_for_installer() 处理重复（同 raw_command 跳过）
# 与卸载时回收（按 installer_id 匹配）。
LAUNCH = {
    "label": "Claude Code",
    "host": "cmd",
    "raw_command": "claude",
}


def detect() -> tuple[bool, str]:
    """探测 Claude Code 是否已安装。

    返回 ``(is_installed, version_or_detail)``：
    - 已装 → ``(True, "1.0.123")``（版本字符串，提取失败时返回原始首行）
    - 未装 / 调用失败 → ``(False, "")``

    任何异常都吞掉，确保 UI 能稳定渲染列表。
    """
    path = shutil.which("claude")
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

    # claude --version 输出形如 "1.0.123 (Claude Code)"；取首行做展示
    output = (result.stdout or result.stderr or "").strip()
    first_line = output.splitlines()[0] if output else ""
    return True, first_line


def install() -> Iterator[InstallEvent]:
    """通过 npm 全局安装 Claude Code。

    用户必须已装 npm；缺 npm 时 ``run_command`` 会 yield 出 127 退出码，
    UI 据此显示"未找到 npm"的失败状态，无需脚本自己额外校验。
    """
    yield InstallEvent("info", "开始安装 Claude Code（npm i -g @anthropic-ai/claude-code）")
    yield from run_command(["npm", "i", "-g", "@anthropic-ai/claude-code"])


def uninstall() -> Iterator[InstallEvent]:
    """通过 npm 全局卸载 Claude Code。

    npm uninstall 即使包不存在也会返回 0，所以"卸载未安装的包"对用户不会失败，
    UI 会照常显示成功——这与"卸载"按钮只在已装时可见的设计一致，正常用户碰不到。
    """
    yield InstallEvent("info", "开始卸载 Claude Code（npm uninstall -g @anthropic-ai/claude-code）")
    yield from run_command(["npm", "uninstall", "-g", "@anthropic-ai/claude-code"])
