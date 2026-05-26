"""CLI 安装脚本通用基础设施。

提供两件事：

1. ``InstallEvent`` —— 安装过程中的事件载荷（一行 stdout / stderr / 进程退出）。
   UI 把它逐条追加到日志窗口，遇到 ``kind == "exit"`` 时根据 ``returncode``
   判断成功失败。

2. ``run_command()`` —— 把 ``subprocess.Popen`` 包装成"流式逐行 yield"的生成器。
   - Windows 上必须带 ``CREATE_NO_WINDOW``，否则打包后会闪黑窗
   - 把 stderr 合并到 stdout，避免输出穿插乱序
   - 解码失败兜底 ``replace``，绝不让安装脚本因为编码崩溃

各厂商 CLI 的 ``install()`` 通常长成这样：

    def install():
        yield from run_command(["npm", "i", "-g", "<package>"])
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterator, Literal


EventKind = Literal["stdout", "stderr", "exit", "info"]


@dataclass(frozen=True)
class InstallEvent:
    """安装过程一次事件。

    字段说明：
    - ``kind``：事件种类。``stdout``/``stderr`` 是子进程实时输出一行；
      ``exit`` 是子进程结束（``returncode`` 必填，``text`` 可空）；
      ``info`` 是脚本自己的提示（例如"开始安装 X"），不来自子进程。
    - ``text``：事件文本，已去掉行尾换行。
    - ``returncode``：仅 ``kind == "exit"`` 时有值；非零视为安装失败。
    """
    kind: EventKind
    text: str = ""
    returncode: int | None = None


def _no_window_flags() -> int:
    """Windows 上返回 CREATE_NO_WINDOW，其他平台返回 0。

    打包成 GUI EXE 后，子进程默认会弹出黑色 cmd 窗口，必须显式抑制。
    """
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


def run_command(
    cmd: list[str],
    cwd: str | None = None,
) -> Iterator[InstallEvent]:
    """运行命令并按行 yield 输出，结束时 yield exit 事件。

    - stderr 合并到 stdout（``stderr=subprocess.STDOUT``），UI 单流显示
    - ``encoding='utf-8', errors='replace'``：现代 CLI 普遍 UTF-8 输出，
      解码失败兜底替换字符，不让一个非法字节炸掉整个安装
    - ``bufsize=1, text=True``：行缓冲，用户能看到实时进度
    - ``Popen`` 找不到命令时（``FileNotFoundError``）yield 一条 stderr +
      exit(returncode=127)，让 UI 走统一的失败分支

    退出码约定：
    - 0 → 成功
    - 非 0 → 失败
    - 127 → 命令本身找不到（约定俗成的"command not found"码）
    """
    # shutil.which 让 ``cmd[0]`` 即使是 npm 这种 .cmd 也能跑通：
    # Windows 上 Popen(["npm", ...]) 默认不展开 PATHEXT，which 替我们做了。
    resolved = shutil.which(cmd[0])
    if resolved is None:
        yield InstallEvent("stderr", f"找不到命令：{cmd[0]}")
        yield InstallEvent("exit", "", returncode=127)
        return

    full_cmd = [resolved, *cmd[1:]]
    try:
        proc = subprocess.Popen(
            full_cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_no_window_flags(),
        )
    except OSError as e:
        # 极少数情况：which 找到了但 Popen 仍失败（权限/可执行损坏）
        yield InstallEvent("stderr", f"启动失败：{e}")
        yield InstallEvent("exit", "", returncode=127)
        return

    # 逐行读取直到 EOF。stdout 不会为 None（我们设了 PIPE）。
    assert proc.stdout is not None
    for line in proc.stdout:
        yield InstallEvent("stdout", line.rstrip("\r\n"))

    proc.wait()
    yield InstallEvent("exit", "", returncode=proc.returncode)
