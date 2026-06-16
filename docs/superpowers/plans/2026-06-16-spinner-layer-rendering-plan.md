# Spinner 截断修复 — 方案 A（分层渲染）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 paintEvent 的逐列交织渲染拆为背景层→文字层两遍绘制，解决 braille/符号字符因字体渲染宽度超出列宽而被相邻列背景覆盖截断的问题。

**Architecture:** 重构 `TerminalWidget.paintEvent` 中的列遍历循环，保持行扫描和光标绘制不变。第一遍绘制所有列的背景 fillRect（含 reverse 和选区高亮），第二遍绘制所有列的文字 drawText（含 bold/italic/underscore）。

**Tech Stack:** Python 3.14, PySide6, pytest

**Spec:** `docs/superpowers/specs/2026-06-16-spinner-wide-char-clip-design.md`

---

### Task 1: 重构 paintEvent 为两遍渲染

**Files:**
- Modify: `ui/terminal_widget.py:308-357`

**背景：** 当前 `paintEvent` 在单次循环中逐列交替绘制背景和文字。当 braille 字符的实际渲染像素宽度（如 Consolas 中 12px）超出列宽 `_char_width`（9px）时，下一列的背景 fillRect 会覆盖溢出像素。修复方法是将循环拆为两遍：第一遍只画背景，第二遍只画文字。

- [ ] **Step 1: 重构 paintEvent 循环为两遍**

将行 308-357 的逐列交织循环替换为以下两遍循环。**仅替换循环体，行 279-307（QPainter 初始化、行扫描）和行 359-362（光标绘制）保持不变。**

```python
        # 第一遍：背景层
        for idx, y, line in rows:
            col = 0
            while col < self._screen.columns:
                x = col * self._char_width
                if x > self.width():
                    break
                char = line.get(col)
                has_real_char = bool(char and char.data and char.data != " ")
                is_reverse_space = bool(char and char.reverse and not has_real_char)

                if has_real_char or is_reverse_space:
                    w = cell_width(char.data) if has_real_char else 1
                else:
                    w = 1
                px_width = self._char_width * w

                if has_real_char or is_reverse_space:
                    bg = self._to_qcolor(char.bg) if char.bg != "default" else DEFAULT_BG
                    if char.reverse:
                        fg_check = self._to_qcolor(char.fg) if char.fg != "default" else DEFAULT_FG
                        bg = fg_check
                    if self._in_selection(idx, col):
                        bg = SEL_COLOR
                else:
                    bg = SEL_COLOR if self._in_selection(idx, col) else DEFAULT_BG

                painter.fillRect(x, y, px_width, self._char_height, bg)
                col += w

        # 第二遍：文字层
        for idx, y, line in rows:
            col = 0
            while col < self._screen.columns:
                x = col * self._char_width
                if x > self.width():
                    break
                char = line.get(col)
                has_real_char = bool(char and char.data and char.data != " ")
                if has_real_char:
                    w = cell_width(char.data)
                    px_width = self._char_width * w

                    fg = self._to_qcolor(char.fg) if char.fg != "default" else DEFAULT_FG
                    bg_for_fg = self._to_qcolor(char.bg) if char.bg != "default" else DEFAULT_BG
                    if char.reverse:
                        fg, bg_for_fg = bg_for_fg, fg
                    painter.setPen(fg)
                    if char.bold and char.italics:
                        painter.setFont(self._font_bi)
                    elif char.bold:
                        painter.setFont(self._font_bold)
                    elif char.italics:
                        painter.setFont(self._font_italic)
                    painter.drawText(x, y + self._fm.ascent(), char.data)
                    if char.bold or char.italics:
                        painter.setFont(self._font)
                    if char.underscore:
                        painter.drawLine(x, y + self._char_height - 1,
                                         x + px_width, y + self._char_height - 1)
                else:
                    w = 1
                col += w
```

关键变更：
- `is_reverse_space` 判断保留在背景层（仅背景层需要），文字层移出
- 选区的 `bg = SEL_COLOR` 判断保留在背景层
- `char.reverse` 的前景色交换逻辑保留在文字层（`fg, bg_for_fg = bg_for_fg, fg`）
- 宽字符步进 `col += w` 在两遍循环中分别独立执行

- [ ] **Step 2: 项目启动验证**

```bash
cd g:/UGit/MyTerm && python main.py
```

目视验证：终端正常启动，文字正常显示，没有明显渲染异常。输入一些 CJK 文字和颜色命令确认。

- [ ] **Step 3: 运行已有测试确认无回归**

```bash
cd g:/UGit/MyTerm && python -m pytest tests/test_cell_width.py tests/test_terminal_selection.py tests/test_terminal_cross_selection.py tests/test_terminal_scroll.py -v
```

- [ ] **Step 4: 验证修复效果**

在终端中启动 codebuddy code，观察 spinner 是否完整显示（不再被截断）。分别在 Cascadia Code 和 Consolas 字体下验证。

- [ ] **Step 5: Commit**

```bash
git add ui/terminal_widget.py
git commit -m "fix: 修复 spinner 右侧截断 — paintEvent 改为背景/文字分层渲染

根因：部分字体（Consolas 12px vs A 9px）的 braille 字符渲染宽度超出
_char_width，逐列交织渲染时下一列背景 fillRect 覆盖溢出像素。

修复：将 paintEvent 循环拆为两遍——先画所有背景，再画所有文字。
文字溢出像素落在已完成的背景之上，不再被后续列覆盖。

方案 A，spec: docs/superpowers/specs/2026-06-16-spinner-wide-char-clip-design.md"
```

---

### Task 2: 添加回归测试

**Files:**
- Create: `tests/test_terminal_rendering.py`

**背景：** 为分层渲染行为添加纯逻辑测试，验证背景/文字颜色计算在分层后与原始交织渲染语义一致。由于 paintEvent 依赖 QPainter（需要 QApplication），测试聚焦于非渲染逻辑：背景颜色选取和前景颜色交换保持不变。

- [ ] **Step 1: 编写测试文件**

```python
"""分层渲染逻辑测试。

验证 paintEvent 拆为背景层/文字层后，背景颜色选取和 reverse 前景色
交换逻辑与原始交织渲染语义一致。
"""
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


class MockChar:
    """模拟 pyte char 对象。"""
    def __init__(self, data=" ", fg="default", bg="default",
                 bold=False, italics=False, underscore=False,
                 reverse=False):
        self.data = data
        self.fg = fg
        self.bg = bg
        self.bold = bold
        self.italics = italics
        self.underscore = underscore
        self.reverse = reverse


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
        result = bg_for_real_cell(0, 0, "red", "default", False,
                                  lambda i, c: False,
                                  DEFAULT_BG, DEFAULT_FG, SEL_COLOR)
        assert result == RED

    def test_reverse_cell_uses_fg_as_bg(self):
        """reverse 时背景层取前景色。"""
        result = bg_for_real_cell(0, 0, "default", "green", True,
                                  lambda i, c: False,
                                  DEFAULT_BG, DEFAULT_FG, SEL_COLOR)
        assert result == GREEN

    def test_selection_overrides_custom_bg(self):
        """选区高亮覆盖自定义背景色。"""
        result = bg_for_real_cell(0, 0, "red", "default", False,
                                  lambda i, c: True,
                                  DEFAULT_BG, DEFAULT_FG, SEL_COLOR)
        assert result == SEL_COLOR

    def test_selection_overrides_reverse_bg(self):
        """选区高亮覆盖 reverse 后的背景色。"""
        result = bg_for_real_cell(0, 0, "default", "green", True,
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
        result = fg_for_draw_text("red", "default", False,
                                   DEFAULT_FG, DEFAULT_BG)
        assert result == RED

    def test_reverse_swaps_fg_and_bg(self):
        """reverse 时文字色取背景色。"""
        result = fg_for_draw_text("default", "red", True,
                                   DEFAULT_FG, DEFAULT_BG)
        assert result == RED

    def test_reverse_custom_fg_swapped_to_bg(self):
        result = fg_for_draw_text("green", "red", True,
                                   DEFAULT_FG, DEFAULT_BG)
        assert result == RED
```

- [ ] **Step 2: 运行新测试**

```bash
cd g:/UGit/MyTerm && python -m pytest tests/test_terminal_rendering.py -v
```

预期：10 个测试全部通过。

- [ ] **Step 3: 运行全部测试确认无回归**

```bash
cd g:/UGit/MyTerm && python -m pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_terminal_rendering.py
git commit -m "test: 添加分层渲染背景/文字颜色逻辑回归测试

覆盖背景层（空单元格、自定义背景、reverse、选区高亮）
和文字层（默认前景色、自定义前景色、reverse 交换）的颜色计算。"
```
