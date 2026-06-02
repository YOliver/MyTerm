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
import logging
import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

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
    - ``readonly``：True 表示设置面板不允许"删除"该项（label/host/command 仍可改）。
      内置 powershell / cmd 用这个标记防误删；用户/installer 加的预设默认 False。
    - ``installer_id``：若非 None，表明这条预设是某个 CLI 安装脚本添加的。
      用于卸载时精准回收（不会因为用户改了 label/command 就找不到来源）。
      用户手加的预设此字段为 None。
    """

    label: str
    host: str
    raw_command: str
    command: list[str] = field(default_factory=list, compare=False)
    readonly: bool = False
    installer_id: Optional[str] = None

    def __post_init__(self) -> None:
        # frozen dataclass 不能直接赋值，必须走 object.__setattr__
        object.__setattr__(self, "command", to_argv(self.host, self.raw_command))


def default_presets() -> list[ShellPreset]:
    """新装/损坏降级时的最小预设。

    只放 powershell + cmd 两条「裸宿主」，标记 readonly 防误删。AI CLI
    都让用户自己加（或由"CLI 安装"菜单装完后自动加），避免「装了但
    命令名不一样」时下拉框里全是 ✗。
    """
    return [
        ShellPreset(label="powershell", host="none",
                    raw_command="powershell.exe", readonly=True),
        ShellPreset(label="cmd", host="none",
                    raw_command="cmd.exe", readonly=True),
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
        logger.warning("未知 host %r，按 'none' 处理", host)

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
        logger.warning("解析失败 %s: %s；使用默认预设（坏文件保留不覆盖）", target, e)
        return default_presets()

    if not isinstance(data, dict) or "presets" not in data:
        logger.warning("顶层结构不合法 %s；使用默认预设", target)
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
    logger.debug("预设加载成功: %s, 共 %d 条", target, len(presets))
    return presets


def _parse_one(item: object, index: int) -> Optional[ShellPreset]:
    """从一条原始 JSON 记录构造 ``ShellPreset``。任何字段问题都返回 None + stderr 警告。

    向后兼容：``readonly`` / ``installer_id`` 是 v1.x 增量字段，旧 json 缺失时
    走默认值（False / None）；为了让首次升级的用户也能立刻保护到内置项，
    label 是 "powershell" / "cmd" 且 installer_id=None 时自动补 readonly=True。
    """
    if not isinstance(item, dict):
        logger.warning("第 %d 条不是对象，跳过", index)
        return None

    label = item.get("label")
    host = item.get("host")
    command = item.get("command")

    if not isinstance(label, str) or not label.strip():
        logger.warning("第 %d 条 label 缺失或空，跳过", index)
        return None
    if host not in VALID_HOSTS:
        logger.warning("第 %d 条 host=%r 非法，跳过 (合法值 %s)", index, host, VALID_HOSTS)
        return None
    if not isinstance(command, str):
        logger.warning("第 %d 条 command 类型错误，跳过", index)
        return None

    # 新字段：缺失则默认 False / None；类型错按缺失处理
    raw_readonly = item.get("readonly", False)
    readonly = bool(raw_readonly) if isinstance(raw_readonly, bool) else False

    raw_inst = item.get("installer_id", None)
    installer_id: Optional[str]
    if raw_inst is None:
        installer_id = None
    elif isinstance(raw_inst, str) and raw_inst:
        installer_id = raw_inst
    else:
        installer_id = None

    # 升级兼容：内置 powershell/cmd 自动获得 readonly 保护，无论旧 json 是否带该字段
    if not readonly and installer_id is None and label in ("powershell", "cmd"):
        readonly = True

    preset = ShellPreset(
        label=label, host=host, raw_command=command,
        readonly=readonly, installer_id=installer_id,
    )
    if not preset.command:
        # to_argv 兜底返回 [] 表示该条无效（如 host=none 但 command 为空）
        logger.warning("第 %d 条命令为空，跳过", index)
        return None
    return preset


def _serialize_one(p: ShellPreset) -> dict:
    """ShellPreset → JSON 可序列化 dict。

    ``readonly`` / ``installer_id`` 仅在非默认值时写入，让 json 在大多数
    情况下保持简洁，也避免被旧版 MyTerm 读到时出现陌生字段（虽然
    ``_parse_one`` 已经能容忍未知键，仍以最小变更为优）。
    """
    obj: dict = {"label": p.label, "host": p.host, "command": p.raw_command}
    if p.readonly:
        obj["readonly"] = True
    if p.installer_id is not None:
        obj["installer_id"] = p.installer_id
    return obj


def save(presets: list[ShellPreset], path: Optional[Path] = None) -> None:
    """原子写到 ``shell_presets.json``。任何 OSError 仅 stderr，不抛。"""
    target = path if path is not None else _shell_presets_path()

    # 确保父目录存在（首次启动时 %LOCALAPPDATA%/MyTerm 可能还没建）
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("创建目录失败 %s: %s", target.parent, e)
        return

    payload = {
        "version": SCHEMA_VERSION,
        "presets": [_serialize_one(p) for p in presets],
    }

    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    except OSError as e:
        logger.warning("写入失败 %s: %s", target, e)
        # 清理可能残留的 .tmp
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def add_for_installer(
    presets: list[ShellPreset],
    installer_id: str,
    launch: dict,
) -> tuple[list[ShellPreset], bool]:
    """安装成功后把 CLI 启动项追加到预设列表。

    纯函数：不读不写文件，调用方拿到新列表后自行决定是否 ``save()``。

    去重策略：按 ``raw_command`` 比对——用户可能手动加过同名命令，
    没必要再叠一条。命中已有项时直接返回原列表（``changed=False``），
    让调用方据此跳过保存。命中但旧条目缺 ``installer_id`` 时，会原地
    打上当前 installer_id 并标 ``changed=True``，方便后续卸载回收。

    返回 ``(new_presets, changed)``：``new_presets`` 永远是新列表
    （即使没改动也是浅拷贝），不会就地修改入参。
    """
    label = str(launch.get("label", "")).strip()
    host = str(launch.get("host", "")).strip()
    raw_command = str(launch.get("raw_command", "")).strip()

    if not label or host not in VALID_HOSTS or not raw_command:
        # launch 元数据残缺时静默跳过：installer 模块声明问题不应阻塞安装流
        logger.warning(
            "add_for_installer: 启动项元数据不合法 "
            "installer_id=%r launch=%r，跳过", installer_id, launch,
        )
        return list(presets), False

    new_list: list[ShellPreset] = []
    changed = False
    matched = False

    for p in presets:
        if not matched and p.raw_command == raw_command:
            matched = True
            if p.installer_id is None:
                # 同命令但没归属：补上 installer_id，便于卸载时一并清理
                new_list.append(ShellPreset(
                    label=p.label, host=p.host, raw_command=p.raw_command,
                    readonly=p.readonly, installer_id=installer_id,
                ))
                changed = True
            else:
                # 已归属（无论是不是当前 installer）：保持原样，避免抢占
                new_list.append(p)
        else:
            new_list.append(p)

    if not matched:
        new_list.append(ShellPreset(
            label=label, host=host, raw_command=raw_command,
            readonly=False, installer_id=installer_id,
        ))
        changed = True

    return new_list, changed


def remove_for_installer(
    presets: list[ShellPreset],
    installer_id: str,
) -> tuple[list[ShellPreset], bool]:
    """卸载成功后回收当初由该 installer 添加的预设。

    纯函数。仅匹配 ``installer_id`` 严格相等的条目；用户手加的同命令
    预设（``installer_id=None``）不动——他们自己加的他们自己负责。

    返回 ``(new_presets, changed)``。同 ``add_for_installer`` 的语义。
    """
    new_list = [p for p in presets if p.installer_id != installer_id]
    changed = len(new_list) != len(presets)
    return new_list, changed
