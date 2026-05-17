"""应用配置：终端槽位上限与 shell 预设。

配置文件位于工程根目录 `config.json`，与 `path_history.json` 同档。
首次启动若文件不存在会主动写出一份默认配置，便于用户后续编辑。
配置改动需要重启 MyTerm 才会生效（不支持热加载）。
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any


# 3×3 网格在默认窗口尺寸 (1100×650) 下每槽位约 360×210，
# 已是终端可读的下限。再大的网格槽位会拥挤到不可用，故强制 clamp。
_HARD_MAX_TERMINALS = 9

_DEFAULT_MAX_TERMINALS = 4
_DEFAULT_SHELL_PRESETS: list[dict[str, Any]] = [
    {"label": "powershell",      "command": ["powershell.exe"]},
    {"label": "claude -r",       "command": ["powershell.exe", "-NoExit", "-Command", "claude -r"]},
    {"label": "codebuddy",       "command": ["powershell.exe", "-NoExit", "-Command", "codebuddy"]},
    {"label": "claude-internal", "command": ["powershell.exe", "-NoExit", "-Command", "claude-internal"]},
    {"label": "cmd",             "command": ["cmd.exe"]},
]


@dataclass(frozen=True)
class ShellPreset:
    """一个 shell 启动预设：下拉框显示用的 label + 实际启动的 argv。"""
    label: str
    command: list[str]


def compute_grid_shape(n: int) -> tuple[int, int]:
    """求容纳 n 个 tile 的最接近正方形的 (rows, cols)，列优先（适合横向窗口）。

    1->1×1, 2->1×2, 3->2×2, 4->2×2, 5/6->2×3, 7/8/9->3×3。
    要求 rows*cols >= n；优先 |rows-cols| 最小，其次 rows*cols-n 最小，
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
    """加载、规范化、必要时落盘默认配置。"""

    def __init__(self, filepath: str | None = None) -> None:
        if filepath is None:
            filepath = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config.json",
            )
        self._filepath = filepath
        self._max_terminals = _DEFAULT_MAX_TERMINALS
        self._shell_presets: list[ShellPreset] = [
            ShellPreset(p["label"], list(p["command"])) for p in _DEFAULT_SHELL_PRESETS
        ]
        self._load()

    @property
    def max_terminals(self) -> int:
        return self._max_terminals

    @property
    def shell_presets(self) -> list[ShellPreset]:
        return list(self._shell_presets)

    # --- internal ---

    def _load(self) -> None:
        if not os.path.exists(self._filepath):
            self._write_default()
            return
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(
                f"[config] 配置文件读取失败，将使用默认值（原文件未改动）: {e}",
                file=sys.stderr,
            )
            return

        if not isinstance(data, dict):
            print(
                "[config] 配置根节点必须是对象，已用默认值（原文件未改动）",
                file=sys.stderr,
            )
            return

        self._max_terminals = self._parse_max_terminals(data.get("max_terminals"))
        self._shell_presets = self._parse_shell_presets(data.get("shell_presets"))

    def _write_default(self) -> None:
        default = {
            "max_terminals": _DEFAULT_MAX_TERMINALS,
            "shell_presets": _DEFAULT_SHELL_PRESETS,
        }
        try:
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(default, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"[config] 写入默认配置失败，仅在内存使用默认值: {e}", file=sys.stderr)

    @staticmethod
    def _parse_max_terminals(value: Any) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            return _DEFAULT_MAX_TERMINALS
        if value < 1:
            return 1
        if value > _HARD_MAX_TERMINALS:
            return _HARD_MAX_TERMINALS
        return value

    @staticmethod
    def _parse_shell_presets(value: Any) -> list[ShellPreset]:
        if not isinstance(value, list):
            return [ShellPreset(p["label"], list(p["command"])) for p in _DEFAULT_SHELL_PRESETS]
        cleaned: list[ShellPreset] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            label = item.get("label")
            command = item.get("command")
            if not isinstance(label, str) or not label:
                continue
            if not isinstance(command, list) or not command:
                continue
            if not all(isinstance(arg, str) for arg in command):
                continue
            cleaned.append(ShellPreset(label, list(command)))
        if not cleaned:
            return [ShellPreset(p["label"], list(p["command"])) for p in _DEFAULT_SHELL_PRESETS]
        return cleaned
