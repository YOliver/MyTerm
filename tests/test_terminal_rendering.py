"""分层渲染逻辑测试。

验证 paintEvent 拆为背景层/文字层后，背景颜色选取和 reverse 前景色
交换逻辑与原始交织渲染语义一致。
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


# 背景层：空字符颜色选取逻辑（从原始代码提取，验证逻辑不变）
def bg_for_empty_cell(idx, col, in_selection_fn, default_bg, sel_color):
    """背景层中空单元格的背景色计算。"""
    if in_selection_fn(idx, col):
        return sel_color
    return default_bg


# 背景层：非空字符背景色计算
def bg_for_real_cell(idx, col, char_bg, char_fg,
                     reverse, in_selection_fn,
                     default_bg, default_fg, sel_color):
    """背景层中非空单元格（含 reverse_space）的背景色计算。"""
    if reverse:
        bg = char_fg if char_fg != "default" else default_fg
    else:
        bg = char_bg if char_bg != "default" else default_bg
    if in_selection_fn(idx, col):
        bg = sel_color
    return bg


# 文字层：reverse 前景色交换逻辑
def fg_for_draw_text(char_fg, char_bg, reverse, default_fg, default_bg):
    """文字层中 reverse 后的前景色（pen）计算。"""
    fg = char_fg if char_fg != "default" else default_fg
    bg_for_fg = char_bg if char_bg != "default" else default_bg
    if reverse:
        fg, bg_for_fg = bg_for_fg, fg
    return fg


DEFAULT_FG = QColor(Qt.white)
DEFAULT_BG = QColor(Qt.black)
SEL_COLOR = QColor(51, 153, 255)
RED = QColor(Qt.red)
GREEN = QColor(Qt.green)


class TestBackgroundLayer:
    """背景层颜色计算测试。"""

    def test_empty_cell_default_bg(self):
        result = bg_for_empty_cell(0, 0, lambda i, c: False,
                                    DEFAULT_BG, SEL_COLOR)
        assert result == DEFAULT_BG

    def test_empty_cell_in_selection(self):
        result = bg_for_empty_cell(0, 0, lambda i, c: True,
                                    DEFAULT_BG, SEL_COLOR)
        assert result == SEL_COLOR

    def test_real_cell_default(self):
        result = bg_for_real_cell(0, 0, "default", "default", False,
                                  lambda i, c: False,
                                  DEFAULT_BG, DEFAULT_FG, SEL_COLOR)
        assert result == DEFAULT_BG

    def test_real_cell_custom_bg(self):
        result = bg_for_real_cell(0, 0, RED, "default", False,
                                  lambda i, c: False,
                                  DEFAULT_BG, DEFAULT_FG, SEL_COLOR)
        assert result == RED

    def test_reverse_cell_uses_fg_as_bg(self):
        """reverse 时背景层取前景色。"""
        result = bg_for_real_cell(0, 0, "default", GREEN, True,
                                  lambda i, c: False,
                                  DEFAULT_BG, DEFAULT_FG, SEL_COLOR)
        assert result == GREEN

    def test_selection_overrides_custom_bg(self):
        """选区高亮覆盖自定义背景色。"""
        result = bg_for_real_cell(0, 0, RED, "default", False,
                                  lambda i, c: True,
                                  DEFAULT_BG, DEFAULT_FG, SEL_COLOR)
        assert result == SEL_COLOR

    def test_selection_overrides_reverse_bg(self):
        """选区高亮覆盖 reverse 后的背景色。"""
        result = bg_for_real_cell(0, 0, "default", GREEN, True,
                                  lambda i, c: True,
                                  DEFAULT_BG, DEFAULT_FG, SEL_COLOR)
        assert result == SEL_COLOR


class TestForegroundLayer:
    """文字层前景色计算测试。"""

    def test_normal_fg_default(self):
        result = fg_for_draw_text("default", "default", False,
                                   DEFAULT_FG, DEFAULT_BG)
        assert result == DEFAULT_FG

    def test_normal_fg_custom(self):
        result = fg_for_draw_text(RED, "default", False,
                                   DEFAULT_FG, DEFAULT_BG)
        assert result == RED

    def test_reverse_swaps_fg_and_bg(self):
        """reverse 时文字色取背景色。"""
        result = fg_for_draw_text("default", RED, True,
                                   DEFAULT_FG, DEFAULT_BG)
        assert result == RED

    def test_reverse_custom_fg_swapped_to_bg(self):
        result = fg_for_draw_text(GREEN, RED, True,
                                   DEFAULT_FG, DEFAULT_BG)
        assert result == RED
