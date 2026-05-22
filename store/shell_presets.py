"""Shell / CLI 预设：JSON 文件持久化的「启动下拉框」配置。

设计动机：
- AI CLI（claude / codebuddy / 其它）不属于「基础环境」，用户会随版本变化自由增删，
  写死在代码里每加一个就得改源码重打包，体验极差。
- 通用 shell（powershell / cmd）则是新装用户起步必备，作为兜底默认值。

数据流：
- ``load()``：从 ``shell_presets.json`` 读出列表；任何异常都降级到 ``default_presets()``，
  绝不抛异常挡住启动。
- ``save()``：原子写（先写 ``.tmp`` 再 ``os.replace``），失败仅 stderr。
- ``to_argv(host, command)``：把「宿主类型 + 用户命令字符串」翻译成可启动 argv。

宿主三选一（``host`` 字段）：
- ``"powershell"`` → ``["powershell.exe", "-NoExit", "-Command", command]``
- ``"cmd"``        → ``["cmd.exe", "/K", command]``（**用 /K 不是 /C**：/C 跑完即退导致黑屏闪退）
- ``"none"``       → ``shlex.split(command, posix=False)``（命令本身就是宿主，如 ``powershell.exe``、``bash.exe``）

``ShellPreset`` 仍 ``frozen=True``：``command: list[str]`` 在 ``__post_init__`` 由
``host + raw_command`` 算出，让 ``ui/main_window.py`` 等旧调用点透明。
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


SCHEMA_VERSION = 1

VALID_HOSTS = ("powershell", "cmd", "none")


@dataclass(frozen=True)
class ShellPreset:
    """一个启动预设。

    - ``label``：下拉框显示文字 + 「保存后回填 currentIndex」的匹配键。
    - ``host``：宿主类型，见模块 docstring。
    - ``raw_command``：用户原样填入的命令字符串。
    - ``command``：由 ``to_argv(host, raw_command)`` 自动算出的 argv，供后端启动直接用。
      这个字段是派生的，不要外部传入；保留它纯粹是为了不破坏 ``main_window.py`` 既有
      ``preset.command`` 调用点。
    """

    label: str
    host: str
    raw_command: str
    command: list[str] = field(default_factory=list, compare=False)

    def __post_init__(self) -> None:
        # frozen dataclass 不能直接赋值，必须走 object.__setattr__
        object.__setattr__(self, "command", to_argv(self.host, self.raw_command))


def default_presets() -> list[ShellPreset]:
    """新装/损坏降级时的最小预设。

    只放 powershell + cmd 两条「裸宿主」。AI CLI 都让用户自己加，避免
    「装了但命令名不一样」时下拉框里全是 ✗。
    """
    return [
        ShellPreset(label="powershell", host="none", raw_command="powershell.exe"),
        ShellPreset(label="cmd",        host="none", raw_command="cmd.exe"),
    ]


def to_argv(host: str, command: str) -> list[str]:
    """``host + command`` → ``list[str]`` argv。

    未知 host 视作 ``"none"`` 并 stderr 警告（让上层 load() 自行决定是否丢弃）。
    ``host="none"`` 下空字符串视作非法，返回 ``[]``：``load()`` 见到 ``[]`` 会跳过该条。
    """
    cmd = command.strip()

    if host == "powershell":
        # -NoExit 让命令跑完保留 shell；与 cmd /K 语义对齐
        return ["powershell.exe", "-NoExit", "-Command", cmd]

    if host == "cmd":
        # /K 而非 /C：/C 跑完即退会让 winpty 销毁 tile（黑屏闪退）
        return ["cmd.exe", "/K", cmd]

    if host != "none":
        print(f"[shell_presets] 未知 host {host!r}，按 'none' 处理", file=sys.stderr)

    if not cmd:
        # host=none 必须有可执行命令；空串无意义
        return []
    # posix=False：保留 Windows 反斜杠路径不被吃成转义；支持双引号包裹的带空格路径
    return shlex.split(cmd, posix=False)


def _shell_presets_path() -> Path:
    """实际配置文件位置；测试可通过 ``load(path=...)`` / ``save(presets, path=...)`` 注入。"""
    from store.paths import shell_presets_path
    return shell_presets_path()


def load(path: Optional[Path] = None) -> list[ShellPreset]:
    """读 ``shell_presets.json``。任何错误都降级到 ``default_presets()``，不抛异常。

    降级顺序：文件缺失 → 写入并返回默认；JSON 解析失败 / schema 错 → stderr 警告 +
    返回默认（**不覆盖坏文件**，保护用户手改）；单条非法 → 跳过该条。
    """
    target = path if path is not None else _shell_presets_path()

    if not target.exists():
        defaults = default_presets()
        # 首次启动顺手把默认值落盘，让用户能看到结构示例方便手改
        save(defaults, path=target)
        return defaults

    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[shell_presets] 解析失败 {target}: {e}；使用默认预设（坏文件保留不覆盖）",
              file=sys.stderr)
        return default_presets()

    if not isinstance(data, dict) or "presets" not in data:
        print(f"[shell_presets] 顶层结构不合法 {target}；使用默认预设", file=sys.stderr)
        return default_presets()

    raw_list = data.get("presets")
    if not isinstance(raw_list, list) or not raw_list:
        return default_presets()

    presets: list[ShellPreset] = []
    for i, item in enumerate(raw_list):
        preset = _parse_one(item, i)
        if preset is not None:
            presets.append(preset)

    if not presets:
        # 全部条目非法 → 兜底默认
        return default_presets()
    return presets


def _parse_one(item: object, index: int) -> Optional[ShellPreset]:
    """从一条原始 JSON 记录构造 ``ShellPreset``。任何字段问题都返回 None + stderr 警告。"""
    if not isinstance(item, dict):
        print(f"[shell_presets] 第 {index} 条不是对象，跳过", file=sys.stderr)
        return None

    label = item.get("label")
    host = item.get("host")
    command = item.get("command")

    if not isinstance(label, str) or not label.strip():
        print(f"[shell_presets] 第 {index} 条 label 缺失或空，跳过", file=sys.stderr)
        return None
    if host not in VALID_HOSTS:
        print(f"[shell_presets] 第 {index} 条 host={host!r} 非法，跳过 "
              f"(合法值 {VALID_HOSTS})", file=sys.stderr)
        return None
    if not isinstance(command, str):
        print(f"[shell_presets] 第 {index} 条 command 类型错误，跳过", file=sys.stderr)
        return None

    preset = ShellPreset(label=label, host=host, raw_command=command)
    if not preset.command:
        # to_argv 兜底返回 [] 表示该条无效（如 host=none 但 command 为空）
        print(f"[shell_presets] 第 {index} 条命令为空，跳过", file=sys.stderr)
        return None
    return preset


def save(presets: list[ShellPreset], path: Optional[Path] = None) -> None:
    """原子写到 ``shell_presets.json``。任何 OSError 仅 stderr，不抛。"""
    target = path if path is not None else _shell_presets_path()

    # 确保父目录存在（首次启动时 %LOCALAPPDATA%/MyTerm 可能还没建）
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[shell_presets] 创建目录失败 {target.parent}: {e}", file=sys.stderr)
        return

    payload = {
        "version": SCHEMA_VERSION,
        "presets": [
            {"label": p.label, "host": p.host, "command": p.raw_command}
            for p in presets
        ],
    }

    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    except OSError as e:
        print(f"[shell_presets] 写入失败 {target}: {e}", file=sys.stderr)
        # 清理可能残留的 .tmp
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
