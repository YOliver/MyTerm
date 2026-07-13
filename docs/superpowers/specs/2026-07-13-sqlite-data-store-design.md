# SQLite 数据存储重构设计

> 状态: 设计阶段 | 日期: 2026-07-13

## 1. 问题陈述

当前 `path_history.json`、`shell_presets.json`、`config.json` 的所有读写均在主线程同步执行。
每次 `path_history.add()` 都会触发完整的 `json.dump` 磁盘写入，导致：

- **主线程 I/O 阻塞**：磁盘写入时 UI 冻结
- **数据损坏风险**：快速连续写入可能导致 JSON 文件被截断或清空
- **不可并发**：未来若增加后台线程写数据，无任何保护

## 2. 架构概览

```
┌─ Main Thread (Qt Event Loop) ───────────────────────────────────┐
│                                                                  │
│  main.py                                                        │
│  ├─ DataStore (内存唯一数据源)                                    │
│  └─ DataWorker(QThread) → 定时 flush                             │
│                                                                  │
│  MainWindow ─── DataStore                                        │
│    ├─ path_history ── store.get_paths() / store.add_path()       │
│    ├─ shell_presets ─ store.get_shell_presets_data()             │
│    │                  store.set_shell_presets_data()              │
│    └─ config ──────── store.get_config_value()                   │
│                       store.set_config_value()                   │
└──────────────────────────────────────────────────────────────────┘
                    │ mark_dirty_xxx() 写入主线程，无锁竞争
                    │ is_any_dirty() DataWorker 读取
                    ▼
┌─ Worker Thread (QThread.run) ────────────────────────────────────┐
│                                                                  │
│  DataWorker.run()                                                │
│  ├─ Phase 1: 初始化                                              │
│  │   ├─ sqlite3.connect(myterm.db, WAL)                          │
│  │   ├─ 建表 (path_history / shell_presets / config)             │
│  │   ├─ 迁移 JSON → SQLite（需要时）                              │
│  │   └─ 加载 SQLite → DataStore → emit data_loaded               │
│  │                                                               │
│  ├─ Phase 2: 定时 Flush 循环                                      │
│  │   └─ 每 100ms 检查 isInterruptionRequested                     │
│  │       每 3s 检查 store.is_any_dirty() → _flush_if_dirty()      │
│  │                                                               │
│  └─ Phase 3: 退出时强制 Flush                                     │
│      └─ _flush_if_dirty() → conn.close()                         │
└──────────────────────────────────────────────────────────────────┘
```

## 3. 组件设计

### 3.1 DataStore — 线程安全内存缓存

文件: `store/data_store.py`（新增）

```python
class DataStore:
    """线程安全的内存数据缓存，主线程写，Worker 线程读（flush 时复制快照）。"""

    def __init__(self):
        self._path_history: list[str] = []       # 路径历史
        self._shell_presets_data: dict = {}      # 完整 JSON（含 version + presets）
        self._config_data: dict[str, str] = {}   # 键值对
        self._dirty_paths = False
        self._dirty_presets = False
        self._dirty_config = False
        self._lock = threading.Lock()

    # ── Path History ──────────────────────────────
    def add_path(self, path: str):   # 去重 + 插头部 + 截断 10 条 → mark_dirty_paths()
    def get_paths(self) -> list[str]: # 返回副本
    def set_paths(self, paths):      # 整量替换（迁移用）→ mark_dirty_paths()

    # ── Shell Presets ─────────────────────────────
    def get_shell_presets_data(self) -> dict:  # 返回副本，调用方不会污染内部状态
    def set_shell_presets_data(self, data):    # 整量替换 → mark_dirty_presets()

    # ── Config ───────────────────────────────────
    def get_config_value(self, key, default=None):
    def set_config_value(self, key, value):     # mark_dirty_config()
    def get_config_all(self) -> dict:           # 返回副本，调用方不会污染内部状态

    # ── Worker 线程���口 ──────────────────────────
    def is_any_dirty(self) -> bool:
        """持锁读取三个 dirty flag，任一个为 True 即返回 True。"""
    def load_initial_data(self, paths: list[str], presets: dict, config: dict[str, str]):
        """仅用于 DataWorker Phase 1 加载：批量写入全部数据，不标记 dirty。
        与 set_paths/set_shell_presets_data/set_config_value 的区别：
        后者每调用一次就 mark_dirty，会导致启动后第一个 flush 无意义回写。
        此方法直接覆盖内存，不设任何 dirty flag。"""
    def take_snapshot_for_flush(self) -> tuple[list|None, dict|None, dict|None]:
        """原子操作：返回脏数据副本 + 清除对应 dirty flag + 记录 snapshot 状态供 rollback 使用。
        返回值: (paths, presets, config)——仅脏的项非 None。
        Worker flush 失败时必须调用 rollback_snapshot() 恢复 dirty flag。"""
    def rollback_snapshot(self):
        """flush 失败时调用：仅恢复 take_snapshot_for_flush() 中原本为 True 的 dirty flag，
        而非全量恢复，避免下个周期不必要的全表写入。"""
```

**设计要点**：
- 三个独立 dirty flag（`_dirty_paths` / `_dirty_presets` / `_dirty_config`），Worker 只 flush 有变更的表
- 所有公开方法内部用 `self._lock` 保护（含 `is_any_dirty()`），锁持有时间极短（仅在内存拷贝）
- `load_initial_data()` 提供不标记 dirty 的批量写入通道，专用于 Worker 启动加载，避免首次 flush 无意义回写
- `take_snapshot_for_flush()` 原子地复制脏数据并清除 dirty flag，同时记录 snapshot 状态（`_snapshot_was_dirty`），供 `rollback_snapshot()` 精确恢复
- `rollback_snapshot()` 只恢复原本就是 True 的 dirty flag，避免一次 flush 失败导致下个周期全量写入
- **并发安全**：主线程在 worker 清除 dirty flag 后仍可设置新的 dirty flag（`True → True` 无影响，`False → True` 下次 flush 捕获），无数据丢失风险
- 数据以 **Python 原生类型**（list/dict/str）存储，无 Qt 依赖

### 3.2 DataWorker — 后台存储线程

文件: `store/data_worker.py`（新增）

```python
class DataWorker(QThread):
    data_loaded = Signal()      # 初始数据加载完毕
    data_flushed = Signal()     # 每次 flush 完成（可选，供调试用）

    def __init__(self, store: DataStore, db_path: Path, parent=None):
        super().__init__(parent)
        self._store = store
        self._db_path = db_path
        self._flush_interval = 3000  # ms

    def run(self):
        # Phase 1: 初始化数据库 + 加载数据
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")  # 5秒超时，防锁定阻塞
        self._create_tables()
        try:
            self._migrate_from_json()  # JSON → SQLite（逐表独立判断，失败则跳过）
        except Exception:
            logger.exception("JSON 迁移失败，从空表继续")
        try:
            self._load_all_to_store()  # SQLite → DataStore
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.exception("SQLite 数据加载失败: %s", e)
            # 数据损坏 → 重建数据库 + 尝试从 JSON 恢复
            try:
                self._conn.close()
                self._db_path.unlink(missing_ok=True)
                self._conn = sqlite3.connect(str(self._db_path))
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
                self._conn.execute("PRAGMA busy_timeout=5000")
                self._create_tables()
                self._migrate_from_json()
                self._load_all_to_store()
            except Exception:
                logger.exception("恢复失败，空表启动")
        self.data_loaded.emit()

        # Phase 2: 定时 flush 循环
        last_flush = time.monotonic()
        while not self.isInterruptionRequested():
            now = time.monotonic()
            if now - last_flush >= self._flush_interval / 1000.0:
                self._flush_if_dirty()
                last_flush = now
            self.msleep(100)  # 每 100ms 检查一次

        # Phase 3: 退出时强制 flush（仅 flush 尚未持久化的脏数据）
        self._flush_if_dirty()
        self._conn.close()

    def _migrate_from_json(self):
        """逐表判断是否需要从旧 JSON 迁移到 SQLite。
        路径使用 store/paths.py 提供的函数（见 §4.4）。
        每表独立检查（表为空 AND JSON 存在），整个迁移在一个事务中。"""
        # implementation per §3.4

    def _load_all_to_store(self):
        """从 SQLite 读取全部数据，通过 DataStore.load_initial_data() 写入内存。
        不标记 dirty —— 刚加载的数据无需回写。"""
        paths_rows = self._conn.execute(
            "SELECT path FROM path_history ORDER BY sort_order").fetchall()
        paths = [row[0] for row in paths_rows]

        presets_row = self._conn.execute(
            "SELECT data FROM shell_presets WHERE id = 1").fetchone()
        presets_data = json.loads(presets_row[0]) if presets_row else {}

        config_rows = self._conn.execute("SELECT key, value FROM config").fetchall()
        config_data = {row[0]: row[1] for row in config_rows}

        self._store.load_initial_data(paths, presets_data, config_data)

    def _flush_if_dirty(self):
        """检查并仅 flush 有变更的数据类型"""
        if not self._store.is_any_dirty():
            return
        paths, presets, config = self._store.take_snapshot_for_flush()
        try:
            if paths is not None:
                self._conn.execute("DELETE FROM path_history")
                for i, p in enumerate(paths):
                    self._conn.execute(
                        "INSERT INTO path_history (path, sort_order) VALUES (?, ?)",
                        (p, i))
            if presets is not None:
                self._conn.execute("DELETE FROM shell_presets")
                self._conn.execute(
                    "INSERT INTO shell_presets (id, data) VALUES (1, ?)",
                    (json.dumps(presets, ensure_ascii=False),))
            if config is not None:
                self._conn.execute("DELETE FROM config")
                for k, v in config.items():
                    self._conn.execute(
                        "INSERT INTO config (key, value) VALUES (?, ?)", (k, v))
            self._conn.commit()
            self.data_flushed.emit()  # 通知主线程 flush 完成（调试/日志用）
        except sqlite3.Error:
            logger.exception("flush 失败，下次重试")
            self._store.rollback_snapshot()  # 仅恢复原本 dirty 的 flag，确保重试
```

### 3.3 数据库 Schema

文件: `myterm.db`，存储在 `local_data_dir()`（`%LOCALAPPDATA%/MyTerm`）

```sql
-- WAL 模式，支持读写并发
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;  -- 平衡安全与性能

CREATE TABLE IF NOT EXISTS path_history (
    path TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS shell_presets (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL  -- JSON blob: {"version": 2, "presets": [...]}
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

**刷新策略**：每次 flush 仅写入有变更的表（通过 `take_snapshot_for_flush()` 返回的非 None 值判断）。
- path_history: `DELETE + INSERT` 全量替换（最多 10 条）
- shell_presets: `DELETE + INSERT` 单行替换
- config: `DELETE + INSERT` 全量替换（2-3 条）

### 3.4 JSON → SQLite 迁移

DataWorker 在 Phase 1 自动执行，逐表独立判断是否需要迁移：

```
1. path_history 表为空 AND path_history.json 存在
   → 读取 JSON 数组 → INSERT INTO path_history
2. shell_presets 表为空 AND shell_presets.json 存在
   → 读取 JSON → INSERT INTO shell_presets（单行 JSON blob）
3. config 表为空 AND config.json 存在
   → 读取 JSON → 逐键 INSERT INTO config
4. 整个迁移过程在一个事务中执行
5. 迁移完成后不删除旧 JSON（作为备份）
```

**幂等性**：每个表独立检查，已存在数据则跳过该表的迁移。例如 `path_history` 在 SQLite 有数据但 `shell_presets` 表仍为空时，只迁移 `shell_presets` 和 `config`。

## 4. 现有代码改造

### 4.1 `store/path_history.py`

**改动量**：小幅

```python
class PathHistory:
    def __init__(self, store: DataStore):
        self._store = store

    def add(self, path: str):
        self._store.add_path(path)       # 以前是 self._paths.append + _save()

    def all(self) -> list[str]:
        return self._store.get_paths()   # 以前是 return list(self._paths)

    # 删除 _load() / _save() — 不再直接读写文件
```

### 4.2 `store/shell_presets.py`

**改动量**：load/save 函数改为 DataStore 后端

```python
def load(store: DataStore) -> list[ShellPreset]:
    data = store.get_shell_presets_data()
    preset_dicts = data.get("presets", [])
    if not preset_dicts:
        # 全新安装 / 空数据：回退到内置默认预设，写入内存（不产生 I/O）
        defaults = default_presets()
        save(defaults, store)  # 仅写内存，由 Worker 定时 flush 到 SQLite
        return list(defaults)
    return [_parse_one(item, i) for i, item in enumerate(preset_dicts)]

def save(presets: list[ShellPreset], store: DataStore):
    payload = {
        "version": SCHEMA_VERSION,
        "presets": [_serialize_one(p) for p in presets],
    }
    store.set_shell_presets_data(payload)
```

**注意**：`load()` 在数据为空时调用 `save()` 写入内置默认预设，`save()` 仅写内存（DataStore），不触发磁盘 I/O。首次 flush 周期将自动持久化到 SQLite。

### 4.3 `store/config.py`

**改动量**：AppConfig 读写改为 DataStore 后端

```python
class AppConfig:
    def __init__(self, store: DataStore):
        self._store = store
        # layout_mode
        mode_str = store.get_config_value("layout_mode", "auto")
        self.layout_mode = LayoutMode(mode_str)
        # max_terminals: 读取并钳位到 [1, 9]
        max_str = store.get_config_value("max_terminals", "4")
        self._max_terminals = min(max(int(max_str), 1), 9)
        # shell_presets: 初始化加载
        self._shell_presets = shell_presets.load(store)

    def save(self):
        self._store.set_config_value("layout_mode", self.layout_mode.value)
        self._store.set_config_value("max_terminals", str(self._max_terminals))

    def reload_shell_presets(self):
        self._shell_presets = shell_presets.load(self._store)

    # 以下 property 保持不变，MainWindow 依赖它们：
    @property
    def shell_presets(self):
        """返回预设的拷贝列表。"""
        return list(self._shell_presets)

    @property
    def max_terminals(self) -> int:
        return self._max_terminals

    # 移除的成员：
    # - _shell_presets_module（不再需要，直接 import shell_presets 调用）
    # - _load_json()（配置走 DataStore，不再直接读文件）
    # - _config_path（不再需要文件路径）
```

### 4.4 `store/paths.py`

**新增**：`database_path()` 和 `config_json_path()` 函数

```python
def database_path() -> Path:
    return local_data_dir() / "myterm.db"

def config_json_path() -> Path:
    """config.json 全路径（与 AppConfig 当前使用的路径一致）。"""
    return local_data_dir() / "config.json"
```

`_migrate_from_json()` 中的路径获取统一使用 `store/paths.py` 提供的函数：
- `path_history_path()` — path_history.json
- `shell_presets_path()` — shell_presets.json
- `config_json_path()` — config.json

### 4.5 `main.py`

```python
def main():
    migrate_legacy_files()   # 保留：处理旧 JSON 位置迁移
    setup_logging()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    store = DataStore()
    worker = DataWorker(store, paths.database_path())
    window = MainWindow(store)         # 传入 DataStore 而非自建 PathHistory/AppConfig
    worker.data_loaded.connect(window.on_data_loaded)
    worker.start()

    window.show()

    # 退出时强制 flush
    def on_about_to_quit():
        worker.requestInterruption()
        worker.wait(5000)             # 等待 worker 完成最后 flush

    app.aboutToQuit.connect(on_about_to_quit)

    watchdog = MainThreadWatchdog(timeout=3.0, check_interval=1.0)
    watchdog.start(parent=window)

    rc = app.exec()
    sys.exit(rc)
```

### 4.6 `ui/main_window.py`

**改动量**：构造器接收 DataStore，不再自行创建 PathHistory/AppConfig

```python
class MainWindow(QMainWindow):
    def __init__(self, store: DataStore):
        super().__init__()
        self._store = store
        self._history = PathHistory(store)
        self._config = AppConfig(store)
        # ... 其余不变

    def on_data_loaded(self):
        """DataWorker 数据加载完毕后刷新 UI"""
        self._load_history()
        self._config.reload_shell_presets()
        self._rebuild_shell_combo()

    def _rebuild_shell_combo(self):
        """重建 shell 下拉框（抽取自当前 __init__ 的填充循环）。
        清空并重新填入 self._config.shell_presets，保留当前选中项。"""
```

**注意**：`_rebuild_shell_combo()` 是从当前 `__init__` 中手动循环 `self._shell_combo.addItem(...)` 抽取出的独立方法，用于数据加载后刷新和预设变更后刷新两个场景。

`_load_history()` 的改动：新增 `self._path_combo.clear()` 调用防止重复追加（当前只在 `__init__` 中调用一次无此风险，重构后 `on_data_loaded()` 也会调用）。

`_on_presets_changed` 的改动：增加 `shell_presets.save(new_presets, self._store)` 调用，替换原来由 `ShellPresetsDialog` 内部直接写文件的逻辑。`reload_shell_presets()` + combo 重建改用 `_rebuild_shell_combo()` 复用，消除重复代码。

## 5. 数据生命周期

### 5.1 启动序列

```
main()
  ├─ DataStore()              # 空内存
  ├─ DataWorker(store, path)  # 创建 Worker
  ├─ MainWindow(store)         # 创建窗口（此时 store 为空）
  ├─ worker.start()            # QThread 启动
  │   └─ run():
  │       ├─ sqlite3.connect()
  │       ├─ CREATE TABLE IF NOT EXISTS
  │       ├─ migrate JSON（若需要）
  │       ├─ load SQLite → DataStore
  │       └─ emit data_loaded ─┐
  │                             │ (queued signal)
  ├─ window.show()             │
  └─ app.exec() ◄──────────────┘
      └─ on_data_loaded():
          ├─ _load_history()             # 填充目录下拉框
          ├─ _config.reload_shell_presets()  # 刷新预设数据
          └─ _rebuild_shell_combo()      # 重建终端选择下拉框
```

### 5.2 运行时操作

```
用户点击"启动" / "浏览"
  → MainWindow._on_launch() / _on_browse()
  → self._history.add(path)
  → store.add_path(path)           # 纯内存操作，瞬时完成
  → store._dirty_paths = True

Worker 线程 (每 3s)
  → store.is_any_dirty() → True
  → store.take_snapshot_for_flush()  # 返回 (paths_list, None, None)，原子清除 dirty
  → DELETE + INSERT → path_history 表（仅此表，presets/config 跳过）
  → conn.commit()
```

### 5.3 关闭序列

```
用户关闭窗口
  → app.aboutToQuit
  → worker.requestInterruption()
  → worker.wait(5000)
    └─ run():
        ├─ _flush_if_dirty()        # 强制 flush 尚未持久化的脏数据
        └─ conn.close()
  → app.exit()
```

## 6. 错误处理

| 场景 | 策略 |
|---|---|
| SQLite 文件损坏 | 删除 `.db`，重新建表 + 尝试从旧 JSON 备份重新迁移（若 JSON 仍存在）。如果 JSON 也不可用则空表启动 |
| SQLite 写入失败（磁盘满） | 调用 `rollback_snapshot()` 恢复 dirty flag，下次 flush 重试，记录日志 |
| JSON 迁移失败 | 跳过迁移，SQLite 从空表开始 |
| 退出时 flush 失败 | wait(5000) 超时后强制退出，数据丢失但有日志 |
| 主线程操作在 worker 加载前 | DataStore 初始为空，UI 显示空状态，加载后刷新 |

## 7. 测试策略

### 7.1 需新增的测试

| 测试文件 | 内容 |
|---|---|
| `tests/test_data_store.py` | DataStore 线程安全：并发读写、take_snapshot 原子性、边界条件 |
| `tests/test_data_worker.py` | DataWorker：建表、迁移、定时 flush、退出 flush、损坏恢复 |
| `tests/test_migration.py` | JSON → SQLite 迁移：三种数据类型、幂等性、损坏 JSON 降级 |

### 7.2 需修改的测试

`tests/test_path_history.py`：PathHistory 现需 DataStore 注入，所有测试用例逻辑不变但需传入 store fixture。

## 8. 文件变更清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `store/data_store.py` | **新增** | DataStore 线程安全内存缓存 |
| `store/data_worker.py` | **新增** | DataWorker(QThread) + SQLite 持久化 |
| `store/path_history.py` | **修改** | 委托给 DataStore，删除 `_load/_save` |
| `store/shell_presets.py` | **修改** | `load/save` 签名改为接受 DataStore |
| `store/config.py` | **修改** | AppConfig 改为 DataStore 后端 |
| `store/paths.py` | **修改** | 新增 `database_path()` 和 `config_json_path()` |
| `main.py` | **修改** | 创建 DataStore/DataWorker，管理生命周期 |
| `ui/main_window.py` | **修改** | 接受 DataStore，连接 data_loaded |
| `ui/shell_presets_dialog.py` | **修改** | 移除内部 `shell_presets.save(presets)` 调用，仅 emit 信号，保存逻辑移至 `MainWindow._on_presets_changed()` 中调用 `save(presets, self._store)` |
| `ui/cli_install_dialog.py` | **修改** | 构造器增加 `store: DataStore` 参数，内部 `save_presets(new_list, store)` 写入内存 |
| `tests/test_path_history.py` | **修改** | 注入 DataStore fixture |
| `tests/test_data_store.py` | **新增** | 线程安全测试 |
| `tests/test_data_worker.py` | **新增** | Worker 功能测试 |
| `tests/test_migration.py` | **新增** | JSON 迁移测试 |

## 9. 兼容性说明

- **升级路径**：旧 JSON 文件在首次启动时自动迁移到 SQLite，用户无感知
- **回滚风险**：迁移后 JSON 文件保留不删除，回滚到旧版本后可继续读取 JSON。但 **不支持降级后再次升级的 round-trip**：降级期间用户对 JSON 的修改不会同步回 SQLite（因为迁移只执行一次，表已有数据时会跳过）。建议降级期间手动备份 SQLite 文件
- **数据库格式版本**：不定义版本号，通过表结构 `IF NOT EXISTS` 向前兼容
