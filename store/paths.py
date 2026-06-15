"""应用数据路径解析。

区分两种运行模式：

- **打包模式**（PyInstaller，``sys.frozen=True``）
  历史/缓存落到 Windows 标准目录，避免污染安装目录。

  - 本机数据（``path_history.json`` 等）→ ``%LOCALAPPDATA%/MyTerm``
  - 缓存（粘贴图片等可随时删的）→ ``%LOCALAPPDATA%/MyTerm/Cache/<sub>``

- **开发模式**（直接 ``python main.py``）
  全部落到工程根，git 里能直接看到、调试方便，不污染 AppData。

shell 预设与槽位上限不通过文件配置（见 ``store/config.py``），所以这里
不再有 ``config_path()``。

任何 IO 失败都不抛异常：能做就做、做不了打 stderr，让上层各自决定降级。
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "MyTerm"

# 仅在打包模式做迁移；在被迁移过一次后写入空哨兵，避免反复尝试。
_MIGRATION_SENTINEL = ".migrated"


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包后的 exe 里。"""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """开发模式下的工程根：本文件父目录的父目录。"""
    return Path(__file__).resolve().parent.parent


def resource_path(name: str) -> Path:
    """读取 PyInstaller 内嵌资源（spec 里 datas 字段声明的文件）。

    - 打包模式：从 ``sys._MEIPASS`` 临时解压目录读
    - 开发模式：从工程根读

    ``name`` 用 POSIX 风格相对路径，例如 ``"helpdocs/welcome.md"``。
    路径分隔符在 Path 拼接时由系统自适配，不必手动处理。

    与 ``local_data_dir`` 的区别：那个管「用户运行时数据」（可读写），
    这个管「应用内嵌资源」（只读、随 EXE 发布）。两套机制各管一摊。
    """
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else project_root()
    return root / name


def _exe_dir() -> Path:
    """打包模式下 exe 所在目录；开发模式同 project_root。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return project_root()


def _env_dir(var: str, fallback: Path) -> Path:
    """读环境变量为目录路径；空/缺失则用 fallback。"""
    raw = os.environ.get(var)
    if raw:
        return Path(raw)
    return fallback


def data_dir() -> Path:
    """数据目录（config.json 等配置文件）。与 local_data_dir 同义。"""
    return local_data_dir()


def local_data_dir() -> Path:
    """本机数据目录（不漫游）。

    打包模式：``%LOCALAPPDATA%/MyTerm``。
    开发模式：工程根。
    """
    if is_frozen():
        local = _env_dir("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        return local / APP_NAME
    return project_root()


def cache_dir(sub: str = "") -> Path:
    """缓存目录。``sub`` 是子目录名，例如 ``"paste"``。

    打包模式：``%LOCALAPPDATA%/MyTerm/Cache[/<sub>]``。
    开发模式：工程根下的隐藏目录，沿用历史命名 ``.paste_cache``（仅 sub=='paste'），
    其它 sub 使用 ``.cache/<sub>``。
    """
    if is_frozen():
        base = local_data_dir() / "Cache"
        return base / sub if sub else base
    # 开发模式：保持向后兼容
    if sub == "paste":
        return project_root() / ".paste_cache"
    return project_root() / ".cache" / sub if sub else project_root() / ".cache"


def log_dir() -> Path:
    """日志目录。

    打包模式：``%LOCALAPPDATA%/MyTerm/Logs``。
    开发模式：工程根下 ``logs/``。
    """
    if is_frozen():
        return ensure_dir(local_data_dir() / "Logs")
    return ensure_dir(project_root() / "logs")


def path_history_path() -> Path:
    """``path_history.json`` 全路径。"""
    return local_data_dir() / "path_history.json"


def shell_presets_path() -> Path:
    """``shell_presets.json`` 全路径。"""
    return local_data_dir() / "shell_presets.json"


def ensure_dir(p: Path) -> Path:
    """mkdir -p；失败 stderr 后照样把 Path 还回去（让上层决定降级）。"""
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[paths] 目录创建失败 {p}: {e}", file=sys.stderr)
    return p


def migrate_legacy_files() -> None:
    """打包后首次启动，把旧位置的用户文件搬到 LOCALAPPDATA。

    搬迁源（按优先级）：exe 同目录 → 工程根（仅开发态升级路径，理论上 frozen 时为空）。
    搬迁目标：``local_data_dir``。
    搬完后写一个空哨兵 ``.migrated``，下次直接跳过。

    仅迁 ``path_history.json``——MyTerm 现在没有用户级配置文件了，
    shell 预设/槽位上限都硬编码在 ``store/config.py`` 里。

    任何失败都吞掉、打 stderr。绝不让迁移挡住程序启动。
    """
    if not is_frozen():
        return

    target = local_data_dir()
    sentinel = target / _MIGRATION_SENTINEL
    if sentinel.exists():
        return

    ensure_dir(target)

    # (源相对名, 目标绝对路径)
    plan: list[tuple[str, Path]] = [
        ("path_history.json", path_history_path()),
    ]

    sources = [_exe_dir(), project_root()]
    for rel, dst in plan:
        if dst.exists():
            continue  # 目标已有，不覆盖
        for src_dir in sources:
            src = src_dir / rel
            if src.is_file():
                try:
                    shutil.copy2(src, dst)
                    print(f"[paths] 迁移 {src} -> {dst}", file=sys.stderr)
                except OSError as e:
                    print(f"[paths] 迁移失败 {src} -> {dst}: {e}", file=sys.stderr)
                break

    # 写哨兵（即便没搬任何东西也写，避免每次启动重扫）
    try:
        sentinel.write_text("", encoding="utf-8")
    except OSError as e:
        print(f"[paths] 哨兵写入失败 {sentinel}: {e}", file=sys.stderr)
