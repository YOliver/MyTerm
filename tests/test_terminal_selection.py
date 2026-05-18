"""选区判定纯逻辑测试。

`is_real_selection` 用来区分"用户真的拖出了一段范围"与"左键单击留下的
单点 sel_start"。后者必须被当作"无选区"，否则右键粘贴会被假选区吞掉
一次（表现为需要右键两下才能粘上）。
"""
import pytest

from ui.terminal_widget import is_real_selection


@pytest.mark.parametrize("sel_start,sel_end,expected", [
    # 两端都没设：从未点击过
    (None, None, False),
    # 只有 start：左键单击后未拖动（"假选区"，bug 来源）
    ((5, 10), None, False),
    # 只有 end：理论上不会出现，但也按"无选区"处理
    (None, (5, 10), False),
    # 起止相同：拖了但没动，等价于单击
    ((5, 10), (5, 10), False),
    # 真选区：同行不同列
    ((5, 10), (5, 20), True),
    # 真选区：跨行
    ((5, 10), (8, 3), True),
    # 真选区：反向（end 在 start 前面）—— normalize 是别处的事，这里只看是否有范围
    ((8, 3), (5, 10), True),
])
def test_is_real_selection(sel_start, sel_end, expected):
    assert is_real_selection(sel_start, sel_end) is expected
