"""应用配置：终端槽位上限。

Shell / CLI 预设原本硬编码在这里，已迁移到 ``store/shell_presets.py``，
通过 ``shell_presets.json`` 文件持久化、由「设置 → AI CLI 配置...」面板维护。
本文件只剩槽位上限相关的常量与 ``AppConfig`` 入口。

``_HARD_MAX_TERMINALS`` 表达「再大就不可用」的硬约束，跟用户偏好无关，所以仍写常量。
"""
from __future__ import annotations

import json
import logging
from enum import Enum

logger = logging.getLogger(__name__)


# 3×3 网格在默认窗口尺寸 (1100×650) 下每槽位约 360×210，
# 已是终端可读的下限。再大的网格槽位会拥挤到不可用，故强制 clamp。
_HARD_MAX_TERMINALS = 9

MAX_TERMINALS = 4


class LayoutMode(Enum):
    """终端网格布局模式。"""
    AUTO = "auto"
    QUAD = "quad"
    HORIZONTAL = "h"
    VERTICAL = "v"


def compute_grid_shape(n: int) -> tuple[int, int]:
    """求容纳 n 个 tile 的最接近正方形的 (rows, cols)，列优先（适合横向窗口）。

    1->1×1, 2->1×2, 3->2×2, 4->2×2, 5/6->2×3, 7/8/9->3×3。
    要求 rows*cols >= n；优先 |rows-cols| 最小，其次 rows*cols-n 最小,
    平手时偏好 rows<=cols（横向窗口下行少列多更舒服）。
    """
    if n <= 0:
        return (0, 0)
    best: tuple[int, int] | None = None
    for rows in range(1, n + 1):
        cols = (n + rows - 1) // rows  # ceil(n / rows)
        cur_diff = abs(rows - cols)
        cur_waste = rows * cols - n
        # rows 单调递增，cols 单调递减；rows>cols 之后 |diff| 不再改善，提前剪枝
        if best is not None:
            b_rows, b_cols = best
            b_diff = abs(b_rows - b_cols)
            b_waste = b_rows * b_cols - n
            if (cur_diff, cur_waste) < (b_diff, b_waste):
                best = (rows, cols)
        else:
            best = (rows, cols)
        if rows >= cols:
            break
    assert best is not None
    return best


def compute_grid_shape_for(n: int, mode: LayoutMode) -> tuple[int, int]:
    """根据布局模式计算 (rows, cols)。"""
    if mode == LayoutMode.QUAD:
        return (2, 2)
    elif mode == LayoutMode.HORIZONTAL:
        return (1, max(n, 1))
    elif mode == LayoutMode.VERTICAL:
        return (max(n, 1), 1)
    else:
        return compute_grid_shape(n)


class AppConfig:
    """应用配置入口。从 DataStore 读取，通过 DataWorker 持久化到 SQLite。"""

    def __init__(self, store=None) -> None:
        if store is None:
            # 兼容旧调用：直接从文件读取
            from store import paths
            self._config_path = paths.data_dir() / "config.json"
            data = self._load_json()
            self.layout_mode: LayoutMode = LayoutMode(data.get("layout_mode", "auto"))
            self._max_terminals = min(max(MAX_TERMINALS, 1), _HARD_MAX_TERMINALS)
            from store import shell_presets
            self._shell_presets = shell_presets.load()
        else:
            from store.data_store import DataStore  # type guard
            self._store: DataStore = store
            mode_str = store.get_config_value("layout_mode", "auto")
            self.layout_mode: LayoutMode = LayoutMode(mode_str)
            max_str = store.get_config_value("max_terminals", "4")
            self._max_terminals: int = min(max(int(max_str), 1), _HARD_MAX_TERMINALS)
            from store import shell_presets
            self._shell_presets: list = shell_presets.load(store=store)

        logger.info("配置加载完成: max_terminals=%d, layout_mode=%s, presets=%d",
                     self._max_terminals, self.layout_mode.value, len(self._shell_presets))

    def _load_json(self) -> dict:
        try:
            return json.loads(self._config_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save(self) -> None:
        """保存可写配置项。"""
        if hasattr(self, '_store'):
            self._store.set_config_value("layout_mode", self.layout_mode.value)
            self._store.set_config_value("max_terminals", str(self._max_terminals))
            return
        # 旧 API：写 config.json
        from store import paths
        data = self._load_json()
        data["layout_mode"] = self.layout_mode.value
        data["max_terminals"] = self._max_terminals
        fp = paths.data_dir() / "config.json"
        fp.parent.mkdir(parents=True, exist_ok=True)
        tmp = fp.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(fp)

    @property
    def shell_presets(self):
        return list(self._shell_presets)

    @property
    def max_terminals(self) -> int:
        return self._max_terminals

    def reload_shell_presets(self) -> None:
        """重新加载预设数据。"""
        from store import shell_presets
        if hasattr(self, '_store'):
            self._shell_presets = shell_presets.load(store=self._store)
        else:
            self._shell_presets = shell_presets.load()
        logger.info("预设重载完成, 共 %d 条", len(self._shell_presets))
