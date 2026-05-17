"""滚动偏移夹紧的纯逻辑测试。

UI 行为（Shift+PageUp 等组合键拦截、`_scroll_by` 触发 widget update）依赖 Qt
事件系统，沿用项目"UI 不单测"的惯例不在此覆盖。
"""
import pytest

from ui.terminal_widget import clamp_scroll_offset


@pytest.mark.parametrize("offset,history_len,expected", [
    # 正常区间
    (0, 100, 0),
    (50, 100, 50),
    (100, 100, 100),
    # 下越界 → 0
    (-1, 100, 0),
    (-9999, 100, 0),
    # 上越界 → history_len
    (101, 100, 100),
    (9999, 100, 100),
    # 历史为空时（没翻屏空间）
    (0, 0, 0),
    (5, 0, 0),
    (-5, 0, 0),
])
def test_clamp_scroll_offset(offset, history_len, expected):
    assert clamp_scroll_offset(offset, history_len) == expected
