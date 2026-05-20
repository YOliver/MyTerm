"""应用配置：终端槽位上限与 shell 预设。

设计取舍：MyTerm 是单用户工具，"通过 config.json 让用户自定义预设"这种
通用化能力没有真实需求，反而带来"代码默认值与磁盘文件双份"的维护成本。
所以这里把配置直接硬编码在常量里——要改预设就改这个文件再重新打包。

`max_terminals` 同理写常量。`_HARD_MAX_TERMINALS` 仍保留是因为它表达的是
"再大就不可用"的硬约束，跟用户偏好无关。
"""
from __future__ import annotations

from dataclasses import dataclass


# 3×3 网格在默认窗口尺寸 (1100×650) 下每槽位约 360×210，
# 已是终端可读的下限。再大的网格槽位会拥挤到不可用，故强制 clamp。
_HARD_MAX_TERMINALS = 9

MAX_TERMINALS = 4

SHELL_PRESETS_RAW: list[tuple[str, list[str]]] = [
    ("powershell",      ["powershell.exe"]),
    ("claude -r",       ["powershell.exe", "-NoExit", "-Command", "claude -r"]),
    ("codebuddy",       ["powershell.exe", "-NoExit", "-Command", "codebuddy"]),
    ("claude-internal", ["powershell.exe", "-NoExit", "-Command", "claude-internal"]),
    ("cmd",             ["cmd.exe"]),
]


@dataclass(frozen=True)
class ShellPreset:
    """一个 shell 启动预设：下拉框显示用的 label + 实际启动的 argv。"""
    label: str
    command: list[str]


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
    """从模块常量构造配置。保留类形态是为了 main_window 的现有调用点不变。"""

    def __init__(self) -> None:
        self._max_terminals = min(max(MAX_TERMINALS, 1), _HARD_MAX_TERMINALS)
        self._shell_presets: list[ShellPreset] = [
            ShellPreset(label, list(cmd)) for label, cmd in SHELL_PRESETS_RAW
        ]

    @property
    def max_terminals(self) -> int:
        return self._max_terminals

    @property
    def shell_presets(self) -> list[ShellPreset]:
        return list(self._shell_presets)
