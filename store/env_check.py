"""环境依赖检测：判断 Node.js / npm / Python / Git 等基础工具是否安装。

设计成不依赖 Qt 的纯逻辑模块，UI 层（EnvCheckWorker）通过 check_all 生成器
拿到结果。版本号正则化提取，避免硬编码不同工具的输出格式。

AI CLI（claude / codebuddy 等）由用户自由选装，归到「设置 → AI CLI 配置」管理，
不在此处检测——能不能启动，下拉框选完点启动就知道。

Windows 注意：
- 通过 npm 全局安装的命令在 Windows 上是 .cmd 形态，
  shutil.which 会按 PATHEXT 匹配（不必显式带扩展名）
- 子进程必须用 CREATE_NO_WINDOW，否则每检测一项闪一个 cmd 黑窗
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class EnvSpec:
    """一项待检测的环境工具定义。"""
    name: str                # 显示名："Node.js"
    command: str             # which 查找的命令名："node"
    version_args: list[str]  # 取版本的子命令：["--version"]
    version_pattern: str     # 从输出里提版本的正则（首组捕获 X.Y.Z）


@dataclass(frozen=True)
class EnvResult:
    """单项检测结果。"""
    name: str
    installed: bool
    version: str | None      # 未安装/解析失败时 None
    path: str | None         # 未安装时 None
    error: str | None        # --version 超时或失败时填原因


# 检测项写死在这里：基础环境用户场景明确，不做配置化。
# AI CLI 单独走 shell_presets.json，不在此列。
ENV_SPECS: list[EnvSpec] = [
    EnvSpec("Node.js",   "node",      ["--version"], r"v?(\d+\.\d+\.\d+)"),
    EnvSpec("npm",       "npm",       ["--version"], r"(\d+\.\d+\.\d+)"),
    EnvSpec("Python",    "python",    ["--version"], r"Python\s+(\d+\.\d+\.\d+)"),
    EnvSpec("Git",       "git",       ["--version"], r"git\s+version\s+(\d+\.\d+\.\d+)"),
]


def parse_version(output: str, pattern: str) -> str | None:
    """从命令行输出里提取版本号；找不到返回 None（不抛异常）。"""
    m = re.search(pattern, output)
    return m.group(1) if m else None


def _decode_output(data: bytes) -> str:
    """把子进程原始字节解码成文本：UTF-8 优先，失败回退 GBK，再失败用 replace 兜底。

    背景：Windows 上 subprocess(text=True) 默认按系统 locale（中文环境多为 cp936/GBK）
    解码 stdout。但越来越多的现代 CLI 输出 UTF-8 字节流，在 GBK 下会变成乱码，
    导致中文锚点失配、版本号提取失败。这里手动解码绕开。
    """
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def check_one(spec: EnvSpec, timeout: float = 3.0) -> EnvResult:
    """探测单个工具：先 shutil.which 找路径，再调 --version 拿版本。

    返回值约定：
    - 找不到命令：installed=False，其他字段全 None
    - 找到了但 --version 超时：installed=True，version=None，error 填超时说明
    - 找到了但子进程异常（OSError）：同上，error 填异常字符串
    - 一切正常：installed=True，version 与 path 都填，error=None
    """
    path = shutil.which(spec.command)
    if path is None:
        return EnvResult(spec.name, False, None, None, None)

    try:
        # CREATE_NO_WINDOW 仅在 Windows 上有，其他平台用 0（无标志）
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW
        # 不传 text=True：自己拿 bytes 再按 UTF-8/GBK 顺序解码，
        # 避免 GUI/EXE 环境下用系统 locale（GBK）误读 UTF-8 工具输出。
        result = subprocess.run(
            [path, *spec.version_args],
            capture_output=True,
            timeout=timeout,
            creationflags=flags,
        )
    except subprocess.TimeoutExpired:
        return EnvResult(spec.name, True, None, path, f"--version 超时 {timeout}s")
    except OSError as e:
        return EnvResult(spec.name, True, None, path, str(e))

    # stdout 与 stderr 都看：有些工具把版本号写到 stderr（比如老版 java）
    out = _decode_output(result.stdout or b"") + "\n" + _decode_output(result.stderr or b"")
    version = parse_version(out, spec.version_pattern)
    return EnvResult(spec.name, True, version, path, None)


def check_all() -> Iterable[EnvResult]:
    """串行检测全部 ENV_SPECS，逐项 yield。Worker 在后台线程消费。"""
    for spec in ENV_SPECS:
        yield check_one(spec)
