"""应用配置：终端槽位上限。

Shell / CLI 预设原本硬编码在这里，已迁移到 ``store/shell_presets.py``，
通过 ``shell_presets.json`` 文件持久化、由「设置 → AI CLI 配置...」面板维护。
本文件只剩槽位上限相关的常量与 ``AppConfig`` 入口。

``_HARD_MAX_TERMINALS`` 表达「再大就不可用」的硬约束，跟用户偏好无关，所以仍写常量。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# 3×3 网格在默认窗口尺寸 (1100×650) 下每槽位约 360×210，
# 已是终端可读的下限。再大的网格槽位会拥挤到不可用，故强制 clamp。
_HARD_MAX_TERMINALS = 9

MAX_TERMINALS = 4


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


class AppConfig:
    """聚合槽位上限 + shell 预设入口。预设来自 ``shell_presets.json``。"""

    def __init__(self) -> None:
        self._max_terminals = min(max(MAX_TERMINALS, 1), _HARD_MAX_TERMINALS)
        # 延迟 import 避免 store 内部循环依赖（shell_presets 也用 store.paths）
        from store import shell_presets
        self._shell_presets_module = shell_presets
        self._shell_presets = shell_presets.load()
        logger.info("配置加载完成: max_terminals=%d, presets=%d",
                     self._max_terminals, len(self._shell_presets))

    @property
    def max_terminals(self) -> int:
        return self._max_terminals

    @property
    def shell_presets(self):
        """返回当前预设的拷贝列表。外部 mutate 不会污染内部状态。"""
        return list(self._shell_presets)

    def reload_shell_presets(self) -> None:
        """重新读盘刷新预设。设置面板保存后由信号触发。"""
        self._shell_presets = self._shell_presets_module.load()
        logger.info("预设重载完成, 共 %d 条", len(self._shell_presets))
