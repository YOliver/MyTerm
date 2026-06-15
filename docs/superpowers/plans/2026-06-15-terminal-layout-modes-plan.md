# 终端布局模式切换 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「视图」菜单，支持自动 / 四象限 / 横排 / 竖排四种终端布局自由切换，持久化到配置

**Architecture:** 数据层新增 `LayoutMode` 枚举 + `compute_grid_shape_for()` + `AppConfig` 持久化；UI 层新增菜单 + `_relayout()` 适配 + 占位符渲染

**Tech Stack:** Python + PySide6 + pytest

---

### Task 1: `LayoutMode` 枚举 + `compute_grid_shape_for()` 函数

**Files:**
- Modify: `store/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 编写测试**

在 `tests/test_config.py` 末尾新增：

```python
# ── compute_grid_shape_for ──

from store.config import compute_grid_shape_for, LayoutMode, compute_grid_shape


def test_compute_grid_shape_for_auto():
    """AUTO 模式与 compute_grid_shape 结果一致。"""
    for n in range(1, 10):
        assert compute_grid_shape_for(n, LayoutMode.AUTO) == compute_grid_shape(n)


def test_compute_grid_shape_for_quad():
    """QUAD 模式固定返回 (2, 2)。"""
    assert compute_grid_shape_for(4, LayoutMode.QUAD) == (2, 2)
    assert compute_grid_shape_for(2, LayoutMode.QUAD) == (2, 2)
    assert compute_grid_shape_for(1, LayoutMode.QUAD) == (2, 2)


def test_compute_grid_shape_for_horizontal():
    """横排模式：rows=1，cols=n（至少 1）。"""
    assert compute_grid_shape_for(4, LayoutMode.HORIZONTAL) == (1, 4)
    assert compute_grid_shape_for(1, LayoutMode.HORIZONTAL) == (1, 1)
    assert compute_grid_shape_for(0, LayoutMode.HORIZONTAL) == (1, 1)


def test_compute_grid_shape_for_vertical():
    """竖排模式：cols=1，rows=n（至少 1）。"""
    assert compute_grid_shape_for(4, LayoutMode.VERTICAL) == (4, 1)
    assert compute_grid_shape_for(1, LayoutMode.VERTICAL) == (1, 1)
    assert compute_grid_shape_for(0, LayoutMode.VERTICAL) == (1, 1)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_config.py::test_compute_grid_shape_for_quad -v
```

预期：`ImportError: cannot import name 'LayoutMode'`

- [ ] **Step 3: 实现 `LayoutMode` + `compute_grid_shape_for`**

在 `store/config.py` 顶部新增 import：

```python
from enum import Enum
```

在 `_HARD_MAX_TERMINALS` 之后新增枚举：

```python
class LayoutMode(Enum):
    """终端网格布局模式。"""
    AUTO = "auto"
    QUAD = "quad"
    HORIZONTAL = "h"
    VERTICAL = "v"
```

在 `compute_grid_shape()` 之后新增函数：

```python
def compute_grid_shape_for(n: int, mode: LayoutMode) -> tuple[int, int]:
    """根据布局模式计算 (rows, cols)。"""
    if mode == LayoutMode.QUAD:
        return (2, 2)
    elif mode == LayoutMode.HORIZONTAL:
        return (1, max(n, 1))
    elif mode == LayoutMode.VERTICAL:
        return (max(n, 1), 1)
    else:
        return compute_grid_shape(n)
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_config.py::test_compute_grid_shape_for_auto tests/test_config.py::test_compute_grid_shape_for_quad tests/test_config.py::test_compute_grid_shape_for_horizontal tests/test_config.py::test_compute_grid_shape_for_vertical -v
```

预期：4 passed

- [ ] **Step 5: 确认已有测试不受影响**

```bash
python -m pytest tests/test_config.py -v
```

预期：全部 passing（包括 `test_compute_grid_shape`）

- [ ] **Step 6: 提交**

```bash
git add store/config.py tests/test_config.py
git commit -m "feat: 新增 LayoutMode 枚举 + compute_grid_shape_for 函数"
```

---

### Task 2: `AppConfig` 持久化 `layout_mode`

**Files:**
- Modify: `store/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 编写持久化测试**

```python
# ── AppConfig layout_mode 持久化 ──

def test_app_config_layout_mode_default(tmp_path: Path, monkeypatch):
    """无 config.json 时默认 AUTO。"""
    import store.paths as _paths
    monkeypatch.setattr(_paths, "data_dir", lambda: tmp_path)
    from store.config import AppConfig
    cfg = AppConfig()
    assert cfg.layout_mode == LayoutMode.AUTO


def test_app_config_layout_mode_persist(tmp_path: Path, monkeypatch):
    """写入 QUAD 后重新加载，layout_mode 不变。"""
    import store.paths as _paths
    monkeypatch.setattr(_paths, "data_dir", lambda: tmp_path)
    from store.config import AppConfig, LayoutMode
    cfg = AppConfig()
    cfg.layout_mode = LayoutMode.QUAD
    cfg.save()

    cfg2 = AppConfig()
    assert cfg2.layout_mode == LayoutMode.QUAD


def test_app_config_save_preserves_existing_keys(tmp_path: Path, monkeypatch):
    """save() 不会覆盖 config.json 中已有字段。"""
    import store.paths as _paths
    monkeypatch.setattr(_paths, "data_dir", lambda: tmp_path)
    (tmp_path / "config.json").write_text(
        '{"max_terminals": 4, "layout_mode": "auto"}', encoding="utf-8",
    )
    from store.config import AppConfig
    cfg = AppConfig()
    cfg.layout_mode = LayoutMode.VERTICAL
    cfg.save()

    saved = tmp_path / "config.json"
    import json
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["layout_mode"] == "v"
    assert data["max_terminals"] == 4
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_config.py::test_app_config_layout_mode_default -v
```

预期：`AttributeError: 'AppConfig' object has no attribute 'layout_mode'`

- [ ] **Step 3: 实现 `AppConfig` 持久化**

修改 `store/config.py` 中的 `AppConfig` 类（`from __future__ import annotations` 已在文件顶部）：

```python
import json
# ... 现有 imports ...

class AppConfig:
    _CONFIG_FILE = "config.json"

    def __init__(self) -> None:
        from store import paths
        self._config_path = paths.data_dir() / self._CONFIG_FILE
        data = self._load_json()
        self.layout_mode: LayoutMode = LayoutMode(data.get("layout_mode", "auto"))
        self._max_terminals = min(max(MAX_TERMINALS, 1), _HARD_MAX_TERMINALS)
        from store import shell_presets
        self._shell_presets_module = shell_presets
        self._shell_presets = shell_presets.load()
        logger.info("配置加载完成: max_terminals=%d, layout_mode=%s, presets=%d",
                     self._max_terminals, self.layout_mode.value, len(self._shell_presets))

    def _load_json(self) -> dict:
        try:
            return json.loads(self._config_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save(self) -> None:
        """保存可写配置项到 config.json（原子写入）。"""
        data = self._load_json()
        data["layout_mode"] = self.layout_mode.value
        data["max_terminals"] = self._max_terminals
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._config_path)
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_config.py::test_app_config_layout_mode_default tests/test_config.py::test_app_config_layout_mode_persist tests/test_config.py::test_app_config_save_preserves_existing_keys -v
```

预期：3 passed

- [ ] **Step 5: 确认已有测试不受影响**

已有 `test_compute_grid_shape` 测试使用 `compute_grid_shape()`（不依赖 AppConfig），不受影响。

```bash
python -m pytest tests/test_config.py -v
```

- [ ] **Step 6: 提交**

```bash
git add store/config.py tests/test_config.py
git commit -m "feat: AppConfig 持久化 layout_mode，新增 save/load 机制"
```

---

### Task 3: 菜单栏「视图」+ `_relayout()` 适配

**Files:**
- Modify: `ui/main_window.py`

- [ ] **Step 1: 修改 `_build_menubar()` 新增「视图」菜单**

在 `_build_menubar` 方法开头获取 menubar 后，第一个位置插入「视图」菜单（当前菜单顺序调整）：

```python
def _build_menubar(self):
    menubar = self.menuBar()

    # ── 视图 ──
    from store.config import LayoutMode
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

    # ── 环境 ──
    env_menu = menubar.addMenu("环境")
    # ... 原有代码 ...
```

- [ ] **Step 2: 修改 `_relayout()` 使用布局模式**

修改 `_relayout()`（原第 331-364 行）：

```python
def _relayout(self) -> None:
    from store.config import compute_grid_shape_for, LayoutMode

    # 1) 移除旧 widgets（包括占位符）
    for i in reversed(range(self._grid.count())):
        item = self._grid.itemAt(i)
        if item and item.widget():
            self._grid.removeWidget(item.widget())

    # 2) 收集非空 tile
    tiles = [s for s in self._slots if s is not None]
    count = len(tiles)
    if count == 0:
        return

    # 3) 根据布局模式计算行列
    rows, cols = compute_grid_shape_for(count, self._config.layout_mode)
    total_cells = rows * cols

    # 4) 清掉所有旧 stretch
    for r in range(self._grid.rowCount()):
        self._grid.setRowStretch(r, 0)
    for c in range(self._grid.columnCount()):
        self._grid.setColumnStretch(c, 0)

    # 5) 按新维度设置 stretch
    for r in range(rows):
        self._grid.setRowStretch(r, 1)
    for c in range(cols):
        self._grid.setColumnStretch(c, 1)

    # 6) 放置 tile
    for i, slot in enumerate(tiles):
        self._grid.addWidget(slot.tile, i // cols, i % cols)

    # 7) 固定模式下填占位符
    if self._config.layout_mode != LayoutMode.AUTO:
        for i in range(count, total_cells):
            placeholder = QWidget()
            placeholder.setStyleSheet(
                "background: #1a1a1a; border: 1px solid #333; border-radius: 2px;"
            )
            self._grid.addWidget(placeholder, i // cols, i % cols)
```

- [ ] **Step 3: 新增 `_on_layout_switch` + `_update_layout_menu_check`**

在 `MainWindow` 类中新增两个方法：

```python
def _on_layout_switch(self, mode) -> None:
    """视图菜单切换布局模式。"""
    self._config.layout_mode = mode
    self._config.save()
    self._update_layout_menu_check()
    self._relayout()


def _update_layout_menu_check(self) -> None:
    """同步菜单选中状态。"""
    for mode, action in self._layout_actions.items():
        action.setChecked(mode == self._config.layout_mode)
```

- [ ] **Step 4: 初始化时调用一次 `_update_layout_menu_check`**

`_build_menubar` 末尾已有调用（见 Step 1）。

- [ ] **Step 5: 运行全量测试确认无回归**

```bash
python -m pytest tests/ -v
```

- [ ] **Step 6: 提交**

```bash
git add ui/main_window.py
git commit -m "feat: 新增视图菜单 + _relayout 适配四种布局模式"
```

---

### Task 4: 全量测试 + 手动验证

- [ ] **Step 1: 运行全量测试**

```bash
python -m pytest tests/ -v
```

预期：全部通过

- [ ] **Step 2: 手动验证**

1. 启动 MyTerm，打开 2 个终端
2. 视图菜单 → 四象限，确认 2×2 网格，空位灰框占位
3. 视图菜单 → 横排，确认 1×2 横排
4. 视图菜单 → 自动，确认恢复默认行为
5. 关闭重开，确认布局恢复上次选择

