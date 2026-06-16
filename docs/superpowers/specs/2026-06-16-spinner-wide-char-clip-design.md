# spinner / 宽字符渲染截断修复

> 行首 spinner（Braille 旋转符号 `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏` / `⣾⣽⣻⢿⡿⣟⣯⣷`）右侧被截断，只显示一半。根因是字体实际像素宽度超出终端列宽 `_char_width`，相邻列的背景 fillRect 覆盖了溢出像素。

## 根因

### 列宽基准

`_char_width = QFontMetrics("A").horizontalAdvance()`（`terminal_widget.py:262`），所有列的像素宽度统一为 `_char_width * cell_width(ch)`。

### 字体渲染不一致

部分等宽字体的 Braille / 符号字符渲染宽度大于 ASCII 字母：

| 字体 | A 像素宽 | Braille 像素宽 | 溢出 |
|------|---------|--------------|------|
| Cascadia Code | 9 | 9 | 0% ✓ |
| Consolas | 9 | 12 | 33% ✗ |
| Courier New | 10 | 12 | 20% ✗ |
| JetBrains Mono | 11 | 12 | 9% ✗ |

### 渲染循环问题

当前 `paintEvent`（`terminal_widget.py:308-357`）逐列交织渲染：

```
for col:
    画当前列背景 fillRect(x, y, px_width, h)
    画当前列文字 drawText(x, y+ascent, ch)
    col += w
```

当 braille 字符实际像素宽度（12px）超出背景填充宽度 `px_width`（9px），**下一列的背景 fillRect 会覆盖掉当前列字符右侧溢出的 3px**，造成截断。

`_EAST_ASIAN_AMBIGUOUS_WIDE` 白名单（`terminal_widget.py:115-117`）解决了 CJK 宽字符问题（返回 `cell_width=2`，`px_width=18`），但 braille 在 Unicode 定义为窄字符（`wcwidth=1`），不在该集合中。

---

## 方案 A：两遍渲染分层绘制（推荐）

### 思路

将逐列交织改为两遍遍历：第一遍画所有背景，第二遍画所有文字。文字溢出像素落在已画好的背景之上，不会被覆盖。

### 改动位置

`ui/terminal_widget.py` — `paintEvent` 方法，行 308-357。

### 修改前

```python
# 行 308-357（简化）
for idx, y, line in rows:
    col = 0
    while col < self._screen.columns:
        x = col * self._char_width
        # ... 获取 char, has_real_char, is_reverse_space ...

        # ---- 背景 ----
        if has_real_char or is_reverse_space:
            w = cell_width(char.data) if has_real_char else 1
            px_width = self._char_width * w
            # ... 计算 bg ...
            painter.fillRect(x, y, px_width, self._char_height, bg)
        else:
            w = 1
            px_width = self._char_width
            bg = SEL_COLOR if self._in_selection(idx, col) else DEFAULT_BG
            painter.fillRect(x, y, px_width, self._char_height, bg)

        # ---- 前景文字 ----
        if has_real_char:
            # ... 设置颜色、字体 ...
            painter.drawText(x, y + self._fm.ascent(), char.data)
            if char.underscore:
                painter.drawLine(...)

        col += w
```

### 修改后

```python
# 第一遍：背景层
for idx, y, line in rows:
    col = 0
    while col < self._screen.columns:
        x = col * self._char_width
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

### 优点

- **不改列宽**：列网格完全不动，`_char_width`、`cell_width` 均不变
- **不改白名单**：不需要向 `_EAST_ASIAN_AMBIGUOUS_WIDE` 添加新字符
- **语义正确**：真实终端模拟器就是背景层在下、文字层在上
- **性能无影响**：每帧只多一次 `<200` 列的循环，开销可忽略
- **对所有字体通用**：解决了所有字符渲染宽度不一致的问题

### 缺点

- 两遍遍历略增代码量，但逻辑更清晰
- 文字层按左→右顺序绘制，若 col=0 是 braille（溢出 3px）、col=1 是可视字符，col=1 的字形像素会覆盖 col=0 的溢出部分。这属于可接受行为——col=1 的字符"拥有"自己的列，溢出被覆盖是合理的。实际场景中 spinner 后面通常是空格（`drawText` 无可见像素），溢出保留，功能正常。

### 风险

- **低风险**：仅重构 `paintEvent` 中的渲染顺序，不改变任何坐标或尺寸计算
- 需确认光标绘制仍在最后（当前已在两遍循环之外，不受影响）
- 需确认现有测试仍通过（选区、背景色、reverse 效果等）

---

## 方案 B：按 QFontMetrics 实际宽度填充背景（不可独立使用）

### 思路

背景 fillRect 宽度改用 `QFontMetrics.horizontalAdvance(ch.data)` 的实际像素值，精确匹配每个字形的渲染宽度。

### 改动位置

`ui/terminal_widget.py` — 行 320-321 及 background else 分支。

### 修改前

```python
w = cell_width(char.data) if has_real_char else 1
px_width = self._char_width * w
```

### 修改后

```python
w = cell_width(char.data) if has_real_char else 1
# 用实际字形宽度替代列宽乘积，确保背景不裁剪溢出像素
glyph_width = self._fm.horizontalAdvance(char.data) if has_real_char else self._char_width
px_width = max(self._char_width, glyph_width)
```

### 优点

- **最小改动**：只改一行
- **精确**：每个字符按自身宽度填充背景

### 致命缺陷：不能独立使用

即使 col=0 的 `px_width` 扩大到实际渲染宽度，当前**交织渲染**仍会在文字后绘制下一列背景：

```
col=0: fillRect(0, 0-12) → drawText("⠏", 0)
col=1: fillRect(9, 9-18) → ...  ← 背景覆盖 x=9~12 的 braille 溢出！
```

col=1 的 fillRect 在 col=0 的 drawText **之后**执行，仍然会覆盖溢出像素。方案 B 必须配合方案 A（两遍渲染）才能生效，但配合后方案 A 单独就足够了，方案 B 是多余代码。

### 缺点

- **破坏列网格对齐**：同一列不同行的背景 rect 宽度可能不同（取决于该位置是什么字符）
- **视觉锯齿**：列边界不再垂直对齐，尤其是多行文本中混有 braille 和 ASCII 时
- **语义错位**：与 pyte 屏幕模型的列宽语义冲突（`cell_width` 返回列数，实际像素与该列数脱钩）

### 结论

❌ **不可独立使用**。仅当与方案 A 同时实施时可有微弱增强效果（减少溢出像素量），但性价比极低，不推荐。

---

## 方案 C：扩大列宽基准

### 思路

将 `_char_width` 从 `QFontMetrics("A")` 改为取所有可渲染字符的最大水平 advance，确保 `_char_width >= 任何字符的实际像素宽度`。

### 改动位置

`ui/terminal_widget.py` — `_update_font_metrics` 方法，行 260-263。

### 实现方式

```python
def _update_font_metrics(self):
    self._fm = QFontMetricsF(self._font)  # 改用浮点精度
    # 取一个宽字符的宽度作为列宽上限
    self._char_width = int(
        max(
            self._fm.horizontalAdvance("A"),
            self._fm.horizontalAdvance("W"),
            self._fm.horizontalAdvance("M"),
        )
    )
    # 或更暴力：直接遍历整个字体的最大 advance
    # self._char_width = int(self._fm.maxWidth())
    self._char_height = self._fm.height()
```

### 优点

- **改动最小**：只改一个方法
- **一劳永逸**：所有字符都不会溢出列宽
- **符合等宽字体设计意图**：大多数等宽字体的 `maxWidth` 覆盖了所有字符

### `maxWidth()` 覆盖面不可靠，推荐采样集

`QFontMetrics.maxWidth()` 不一定覆盖 braille——等宽字体设计者未必让 braille 成为"最宽字符"（它本应是窄字符，渲染偏宽是字体 bug）。

推荐改用**字符采样集**取最大值：

```python
def _update_font_metrics(self):
    self._fm = QFontMetrics(self._font)
    # 采样已知会溢出的字符 + emoji/CJK，取最大像素宽
    self._char_width = int(max(
        self._fm.horizontalAdvance("A"),
        self._fm.horizontalAdvance("W"),
        self._fm.horizontalAdvance("⠏"),     # braille spinner
        self._fm.horizontalAdvance("⣾"),     # braille square spinner
        self._fm.horizontalAdvance("⚠"),      # 已在歧义宽白名单中
        self._fm.horizontalAdvance("中"),
        self._fm.horizontalAdvance("🎉"),
    ))
    self._char_height = self._fm.height()
```

### 缺点

- **终端面积膨胀**：列宽增大，整体窗口变大。JetBrains Mono 中 braille=12px vs A=11px，宽度增 ~9%
- **不优雅**：为少数特殊字符让所有字符间距变宽
- 采样集维护成本：新字体或新 Unicode 符号可能需要追加

### 风险

- **低风险**：仅改变一个度量值，不影响其他逻辑
- 需在目标字体（Consolas、Courier New、JetBrains Mono）下验证采样集覆盖面的实际列宽

---

## 方案对比

| 维度 | 方案 A（分层渲染） | 方案 B（实际宽度） | 方案 C（扩大基准） |
|------|-------------------|-------------------|-------------------|
| 独立可行 | ✅ | ❌（必须配合 A） | ✅ |
| 改动量 | 中等（重构 paintEvent 循环） | 小（改 1 行） | 小（改 1 个方法 + 采样集） |
| 列网格对齐 | 保持 ✓ | 破坏 ✗ | 保持 ✓ |
| 窗口面积 | 不变 ✓ | 不变 ✓ | 膨胀 ~9% ✗ |
| 覆盖范围 | 所有字符 | 所有字符 | 取决于采样集 |
| 侵入性 | 低 | 中 | 低 |
| 可维护性 | 好（语义清晰） | 差（语义冲突） | 好 |
| 推荐度 | ★★★ | ☆☆☆（无效） | ★★☆ |

---

## 影响

| 维度 | 影响 |
|------|------|
| Braille / 符号渲染 | ✅ 不再截断 |
| 现有 CJK 宽字符 | ✅ 不受影响（`cell_width=2` 照常） |
| 选区高亮 | 方案 A：✅ 分层后背景仍正确覆盖 |
| 光标显示 | ✅ 光标渲染在两层之后，不受影响 |
| 性能 | ✅ 无感知差异（<200 列两次循环） |

## 测试

每个方案实现后需要：

1. **spinner 截断回归**：在 Consolas / Courier New 字体下运行 codebuddy / claude CLI，确认 spinner 完整显示
2. **CJK 行为不变**：中文、emoji、`_EAST_ASIAN_AMBIGUOUS_WIDE` 字符行为不变
3. **选区不变**：鼠标圈选文本、复制粘贴行为正常
4. **reverse 颜色不变**：黑白反色控制字符显示正常
5. **方案 B 额外**：确认列边界不对齐不会造成视觉问题
6. **方案 C 额外**：确认 `maxWidth()` 在目标字体下覆盖 braille，且窗口面积可接受
