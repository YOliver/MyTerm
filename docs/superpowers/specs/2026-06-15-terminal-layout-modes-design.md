# 终端布局模式切换

> 新增「视图」菜单，支持四种终端布局自由切换：自动 / 四象限 / 横排 / 竖排。

## 目标

- 用户可通过菜单栏「视图」在四种布局模式间自由切换
- 固定模式下空槽位显示灰色占位区域
- 布局选择持久化到配置，重启后恢复

## 布局模式

| 模式 | 枚举值 | 行列 | 说明 |
|------|--------|------|------|
| 自动 | `AUTO` | `compute_grid_shape(n)` | 现有行为，按终端数算最接近正方形 |
| 四象限 | `QUAD` | `2 × 2` | 固定四象限，最大 4 终端 |
| 横排 | `HORIZONTAL` | `1 × n` | 单行，终端等宽 |
| 竖排 | `VERTICAL` | `n × 1` | 单列，终端等高 |

## 数据层变更

### `store/config.py`

**新增 `LayoutMode` 枚举：**

```python
from enum import Enum

class LayoutMode(Enum):
    AUTO = "auto"
    QUAD = "quad"
    HORIZONTAL = "h"
    VERTICAL = "v"
```

**`AppConfig` 新增字段：**

```python
class AppConfig:
    def __init__(self) -> None:
        self.layout_mode: LayoutMode = LayoutMode.AUTO
        # ... 从 config.json 读取，无记录时默认 AUTO
```

config.json 存储示例：
```json
{
  "layout_mode": "quad",
  "max_terminals": 4
}
```

**`compute_grid_shape()` 扩展（可选：保留原函数，新增带 mode 参数的版本）：**

```python
def compute_grid_shape_for(n: int, mode: LayoutMode) -> tuple[int, int]:
    if mode == LayoutMode.QUAD:
        return (2, 2)
    elif mode == LayoutMode.HORIZONTAL:
        return (1, max(n, 1))
    elif mode == LayoutMode.VERTICAL:
        return (max(n, 1), 1)
    else:
        return compute_grid_shape(n)
```

## UI 层变更

### `ui/main_window.py`

**菜单栏新增「视图」菜单：**

现有菜单顺序：`环境 | 设置 | Skills | 日志 | 帮助`

新增后：`视图 | 环境 | 设置 | Skills | 日志 | 帮助`

```python
view_menu = menubar.addMenu("视图")

self._layout_actions: dict[LayoutMode, QAction] = {}
for mode, label in [
    (LayoutMode.AUTO, "自动布局"),
    (LayoutMode.QUAD, "四象限 2×2"),
    (LayoutMode.HORIZONTAL, "横排 1×N"),
    (LayoutMode.VERTICAL, "竖排 N×1"),
]:
    action = view_menu.addAction(label)
    action.setCheckable(True)
    action.triggered.connect(
        lambda _checked, m=mode: self._on_layout_switch(m)
    )
    self._layout_actions[mode] = action

self._update_layout_menu_check()
```

**`_relayout()` 修改：**

```python
def _relayout(self) -> None:
    # 收集活跃 tile
    tiles = [s for s in self._slots if s is not None]
    count = len(tiles)
    if count == 0:
        return

    # 根据当前布局模式计算行列
    rows, cols = compute_grid_shape_for(count, self._config.layout_mode)
    total_cells = rows * cols

    # 清空旧 widgets
    # ... (不变) ...

    # 设置 stretch
    for r in range(rows):
        self._grid.setRowStretch(r, 1)
    for c in range(cols):
        self._grid.setColumnStretch(c, 1)

    # 放置 tile
    for i, slot in enumerate(tiles):
        self._grid.addWidget(slot.tile, i // cols, i % cols)

    # 固定模式下填占位符
    if self._config.layout_mode != LayoutMode.AUTO:
        for i in range(count, total_cells):
            placeholder = QWidget()
            placeholder.setStyleSheet(
                "background: #1a1a1a; border: 1px solid #333; border-radius: 2px;"
            )
            self._grid.addWidget(placeholder, i // cols, i % cols)
```

**空槽位灰色占位符规格：**

| 属性 | 值 |
|------|-----|
| 背景色 | `#1a1a1a` |
| 边框 | `1px solid #333` |
| 圆角 | `2px` |

**布局切换处理：**

```python
def _on_layout_switch(self, mode: LayoutMode) -> None:
    """视图菜单切换布局模式。"""
    self._config.layout_mode = mode
    self._config.save()
    self._update_layout_menu_check()
    self._relayout()
```

**菜单选中状态同步：**

```python
def _update_layout_menu_check(self) -> None:
    for mode, action in self._layout_actions.items():
        action.setChecked(mode == self._config.layout_mode)
```

## 配置持久化

`AppConfig` 新增 `_config_path` 和 `save()` 方法（当前仅读取 shell_presets，无写回机制）：

```python
class AppConfig:
    _CONFIG_FILE = "config.json"

    def __init__(self) -> None:
        self._config_path = data_dir() / self._CONFIG_FILE
        data = self._load_json()
        self.layout_mode: LayoutMode = LayoutMode(data.get("layout_mode", "auto"))
        self._max_terminals = min(max(MAX_TERMINALS, 1), _HARD_MAX_TERMINALS)

    def save(self) -> None:
        """保存可写配置项到 config.json。"""
        data = self._load_json()  # 合并已有字段
        data["layout_mode"] = self.layout_mode.value
        data["max_terminals"] = self._max_terminals
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._config_path)  # 原子替换

    def _load_json(self) -> dict:
        try:
            return json.loads(self._config_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
```

`layout_mode` 以 `LayoutMode.value`（`"auto"` / `"quad"` / `"h"` / `"v"`）写入 `config.json`。

启动时用 `LayoutMode(data.get("layout_mode", "auto"))` 反序列化，无记录时默认 `AUTO`。

## 影响分析

- `compute_grid_shape()` 原函数保持不变（AUTO 模式继续使用）
- 固定模式下方格数 ≤ 活跃终端数时无占位符，行为与当前一致
- `_relayout()` 每次切换会重建占位符 widget，旧占位符由 `deleteLater()` 自动清理
- 菜单栏新增一个「视图」菜单，不影响现有菜单结构

## 测试

新增测试用例（`tests/test_config.py` 和 `tests/test_layout.py`）：

1. `test_compute_grid_shape_for_quad` — QUAD 模式固定返回 (2, 2)
2. `test_compute_grid_shape_for_horizontal` — 单行，cols=n
3. `test_compute_grid_shape_for_vertical` — 单列，rows=n
4. `test_compute_grid_shape_for_auto` — 与 `compute_grid_shape` 结果一致
5. `test_layout_mode_persist_roundtrip` — 序列化再反序列化不丢信息
6. `test_relayout_quad_placeholder` — 2 终端选 QUAD，验证 grid 含 2 tile + 2 占位符
