"""滚动偏移夹紧的纯逻辑测试。

UI 行为（Shift+PageUp 等组合键拦截、`_scroll_by` 触发 widget update）依赖 Qt
事件系统，沿用项目"UI 不单测"的惯例不在此覆盖。
"""
import pytest

from ui.terminal_widget import (
    clamp_scroll_offset,
    follow_scroll_offset_after_feed,
    scroll_offset_to_slider_value,
    slider_value_to_scroll_offset,
)


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


class TestFollowScrollOffsetAfterFeed:
    """覆盖"任务跑动时鼠标滚轮可滚回历史"的核心逻辑。"""

    def test_at_bottom_keeps_following(self):
        # 贴在底部时新输出仍跟随
        assert follow_scroll_offset_after_feed(0, 100, 105) == 0

    def test_at_bottom_no_growth(self):
        # 贴在底部，本次输出没有滚出新历史行
        assert follow_scroll_offset_after_feed(0, 100, 100) == 0

    def test_paused_compensates_history_growth(self):
        # 用户上滑停在 offset=50，新输出又把 5 行挤进 history
        # 视野要保持静止 → offset 应该跟着 +5
        assert follow_scroll_offset_after_feed(50, 100, 105) == 55

    def test_paused_no_growth_stays_put(self):
        # 用户上滑后，新输出没有产生历史行（屏内刷新），offset 不动
        assert follow_scroll_offset_after_feed(50, 100, 100) == 50

    def test_paused_clamped_when_history_capped(self):
        # history 已经达到上限 2000，新行进来时旧行被 deque 挤掉，
        # new_history_len 不再增长。offset 仍然受 [0, history_len] 夹紧。
        assert follow_scroll_offset_after_feed(2000, 2000, 2000) == 2000

    def test_paused_negative_growth_treated_as_zero(self):
        # 极端兜底：history 因为某种重置反而变短，不应让 offset 倒退成负数
        assert follow_scroll_offset_after_feed(50, 100, 80) == 50


class TestScrollSliderConversion:
    """覆盖 _scroll_offset 与 QScrollBar.value 的反向映射。

    QScrollBar 习惯：value=0 在顶（看最旧），value=max 在底（看最新）。
    项目内部反过来：scroll_offset=0 看最新，scroll_offset=history_len 看最旧。
    所以两边互为反向。
    """

    def test_offset_zero_means_slider_at_bottom(self):
        # 贴底（看最新）→ slider value 应该是最大
        assert scroll_offset_to_slider_value(0, 100) == 100

    def test_offset_max_means_slider_at_top(self):
        # 顶端（看最旧）→ slider value 应该是 0
        assert scroll_offset_to_slider_value(100, 100) == 0

    def test_offset_middle_maps_to_middle(self):
        # 中间值
        assert scroll_offset_to_slider_value(30, 100) == 70

    def test_slider_to_offset_is_inverse(self):
        # 来回换算应该回到原值
        for offset in (0, 1, 50, 99, 100):
            slider = scroll_offset_to_slider_value(offset, 100)
            assert slider_value_to_scroll_offset(slider, 100) == offset

    def test_empty_history_clamps_to_zero(self):
        assert scroll_offset_to_slider_value(0, 0) == 0
        assert slider_value_to_scroll_offset(0, 0) == 0

    def test_slider_value_clamped(self):
        # slider 值越界（超大 / 负数）也要 clamp 到合法 offset
        assert slider_value_to_scroll_offset(9999, 100) == 0  # 越大 → offset 越小，下夹到 0
        assert slider_value_to_scroll_offset(-5, 100) == 100  # 负值 → offset 越大，上夹到 history_len
