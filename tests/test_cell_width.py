"""字符在终端中的占列数判定测试。

`cell_width` 处理三类字符：
1. ASCII / 半角字符 → 1 格
2. CJK 全角 / emoji → 2 格（wcwidth 已正确返回 2）
3. East Asian Ambiguous（⚠ ✓ ✗ ● ★ → 等）→ 中文环境下应取 2 格
   wcwidth 默认返回 1，需要白名单覆盖，否则在 CJK 终端会和后续文字重叠
   （bug 报告：claude 输出 "⚠ 本身没有..." 时 ⚠ 与"本"挤在同一格）
"""
import pytest

from ui.terminal_widget import cell_width


@pytest.mark.parametrize("ch,expected", [
    # 空 / 无效输入：保守取 1
    ("", 1),

    # ASCII：1 格
    ("A", 1),
    ("a", 1),
    ("0", 1),
    (" ", 1),
    ("!", 1),

    # CJK 全角：wcwidth 返回 2，正常工作
    ("中", 2),
    ("文", 2),
    ("。", 2),  # 全角句号
    ("　", 2),  # 全角空格

    # East Asian Ambiguous：本次修复重点
    ("⚠", 2),  # 警告三角（claude/codebuddy 常用）
    ("✓", 2),  # 对号
    ("✗", 2),  # 错号
    ("●", 2),  # 实心圆点（列表项常用）
    ("○", 2),  # 空心圆点
    ("★", 2),
    ("☆", 2),
    ("■", 2),
    ("□", 2),
    ("→", 2),  # 右箭头
    ("←", 2),  # 左箭头
    ("↑", 2),
    ("↓", 2),
    ("◆", 2),
    ("◇", 2),

    # emoji：wcwidth 返回 2
    ("🎉", 2),
    ("✅", 2),

    # 多字符串只看第一个字符
    ("AB", 1),
    ("中A", 2),
    ("⚠ warn", 2),
])
def test_cell_width(ch, expected):
    assert cell_width(ch) == expected
