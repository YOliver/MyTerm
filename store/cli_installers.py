"""CLI 安装项发现器。

扫描 ``scripts/cli_installers/`` 目录下所有非下划线开头的 ``.py`` 模块，
import 后收集模块级常量与函数，封装成 ``InstallerSpec`` 列表供 UI 使用。

为什么不直接 ``import scripts.cli_installers as pkg`` 然后枚举：
- pkg 不会 eager 导入子模块
- 需要兼容打包态：``sys._MEIPASS/scripts/cli_installers/*.py`` 也得能扫到

实现策略：用 ``pkgutil.iter_modules`` 遍历包搜索路径（开发态自然指向工程根，
打包态由 PyInstaller 把目录解压到 ``_MEIPASS``，包搜索路径会自动包含它），
然后用 ``importlib.import_module`` 按完整模块名加载。

错误策略：单个模块加载失败仅 stderr 打日志，不中断其它模块的发现，
确保用户至少能看到能用的 CLI。
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterator

# 包名（dotted）。运行期 import 用这个，发现器扫它的 __path__。
_PACKAGE_NAME = "scripts.cli_installers"


@dataclass(frozen=True)
class InstallerSpec:
    """一个 CLI 安装项的元数据 + 调用入口。

    UI 用 ``id``/``name``/``description``/``requires`` 渲染列表；
    点击按钮时调用 ``detect`` 查状态、``install`` 跑安装、``uninstall`` 跑卸载。

    ``uninstall`` 是可选的：模块未提供时为 None，UI 隐藏卸载按钮——
    有些 CLI（例如官方安装器装的）不一定有干净的命令行卸载方式，
    强行兜底反而误导用户。

    ``launch`` 也是可选的：模块声明 ``LAUNCH = {"label","host","raw_command"}``
    时透传过来；安装成功后 UI 会据此往 AI CLI 预设里追加一条启动项，
    卸载成功后用同一份 ``installer_id`` 反查并移除。模块没声明就保持 None，
    UI 不做联动。
    """
    id: str
    name: str
    description: str
    requires: tuple[str, ...]
    detect: Callable[[], tuple[bool, str]]
    install: Callable[[], Iterator]  # 返回 InstallEvent 迭代器
    uninstall: Callable[[], Iterator] | None = None  # 可选；None 表示不支持卸载
    launch: dict[str, Any] | None = None  # 可选；安装后写入 AI CLI 预设的元数据


def _iter_module_names() -> Iterator[str]:
    """枚举 ``scripts.cli_installers`` 包下的子模块完整名。

    跳过私有模块（``_`` 开头，例如 ``_base``）和子包，只取顶层 ``.py``。
    """
    try:
        package = importlib.import_module(_PACKAGE_NAME)
    except ImportError as e:
        print(f"[cli_installers] 无法 import 包 {_PACKAGE_NAME}: {e}", file=sys.stderr)
        return

    # __path__ 在打包态由 PyInstaller 注入到 _MEIPASS 解压目录，无需我们手动处理
    for info in pkgutil.iter_modules(package.__path__):
        if info.ispkg:
            continue
        if info.name.startswith("_"):
            continue
        yield f"{_PACKAGE_NAME}.{info.name}"


def _load_one(module_name: str) -> InstallerSpec | None:
    """import 一个模块并提取 InstallerSpec。

    校验必需的常量与可调用接口；缺任一项就跳过（仅 stderr 打日志）。
    这样写错的脚本只是不出现在列表里，不会让对话框打不开。
    """
    try:
        mod = importlib.import_module(module_name)
    except Exception as e:  # noqa: BLE001 — 子模块可能抛任何错
        print(f"[cli_installers] 加载 {module_name} 失败: {e}", file=sys.stderr)
        return None

    required = ("ID", "NAME", "DESCRIPTION", "REQUIRES", "detect", "install")
    missing = [a for a in required if not hasattr(mod, a)]
    if missing:
        print(
            f"[cli_installers] 模块 {module_name} 缺少属性 {missing}，跳过",
            file=sys.stderr,
        )
        return None

    if not callable(mod.detect) or not callable(mod.install):
        print(
            f"[cli_installers] 模块 {module_name} 的 detect/install 不可调用，跳过",
            file=sys.stderr,
        )
        return None

    # uninstall 可选：缺失或不可调用都视为"不支持卸载"，UI 据此隐藏按钮
    uninstall_fn = getattr(mod, "uninstall", None)
    if uninstall_fn is not None and not callable(uninstall_fn):
        uninstall_fn = None

    # LAUNCH 可选：必须是包含 label/host/raw_command 三个键的 dict，
    # 否则视为格式错误并忽略（同样只 stderr 警告，不让对话框崩）。
    launch_meta = getattr(mod, "LAUNCH", None)
    if launch_meta is not None:
        if not isinstance(launch_meta, dict) or not all(
            k in launch_meta for k in ("label", "host", "raw_command")
        ):
            print(
                f"[cli_installers] 模块 {module_name} 的 LAUNCH 格式不合法，已忽略",
                file=sys.stderr,
            )
            launch_meta = None
        else:
            launch_meta = dict(launch_meta)  # 拷贝一份避免外部改动污染缓存

    return InstallerSpec(
        id=str(mod.ID),
        name=str(mod.NAME),
        description=str(mod.DESCRIPTION),
        requires=tuple(mod.REQUIRES),
        detect=mod.detect,
        install=mod.install,
        uninstall=uninstall_fn,
        launch=launch_meta,
    )


def discover() -> list[InstallerSpec]:
    """返回当前可用的全部 CLI 安装项，按 ``id`` 字典序排序。

    UI 每次打开对话框可调一次。开销不大（每个模块一次 import），但
    如果未来脚本变多需要缓存，可以在外层包一层 lru_cache。
    """
    specs: list[InstallerSpec] = []
    for name in _iter_module_names():
        spec = _load_one(name)
        if spec is not None:
            specs.append(spec)
    specs.sort(key=lambda s: s.id)
    return specs
