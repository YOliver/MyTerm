# 菜单项 → 后台任务 → 表格对话框 模式

「环境 → 检测依赖」走通了一套可复用的方案：菜单触发一个会跑一会儿的任务，
弹窗里逐项更新结果。本文把这套模式抽出来，方便后续往菜单里加新项，或者搬到
别的 PySide6 工程。

## 适用场景

任何「**点一下菜单 → 执行 N 个独立子任务 → 把结果排成一张表展示**」的需求。
典型例子：

- 检测一组外部 CLI 是否安装（当前 实现）
- 批量 ping 一组主机 / 探测一组端口
- 列出本机已安装的字体、查看其元信息
- 拉一组 git 仓库的最新状态
- 校验一组配置文件是否合法

只要每一项任务**互相独立**、**结果能排成几列**，就能直接套这个模式。

## 三层结构

```
ui/main_window.py          ← 菜单项注册（轻）
    │  triggered
    ▼
ui/<feature>_dialog.py     ← 对话框 + QThread Worker（UI 层）
    │  调用
    ▼
store/<feature>.py         ← 纯逻辑：EnvSpec / 检测函数（无 Qt 依赖）
```

**铁律**：`store/` 下不许 `from PySide6 import ...`。这条规则保证业务逻辑可以
脱离 UI 单测。当前 `tests/test_env_check.py` 就直接 import `store/env_check.py`
跑 `parse_version` 和 `check_one`，全程没启动 QApplication。

## 三层各自的职责

### 1. `store/<feature>.py` —— 纯逻辑

- 用 `@dataclass(frozen=True)` 定义 **Spec**（一项任务的输入参数）和
  **Result**（结果数据），不可变 + 易序列化。
- `check_one(spec) -> Result`：跑单项,**永不抛异常**,所有失败模式编码进
  Result 字段（`installed=False` / `error="..."` / `version=None`）。
  让上层不用 `try/except` 包裹。
- `check_all() -> Iterable[Result]`：用 `yield` 串行跑所有 spec。生成器形态
  让 Worker 拿到第一项就能立刻 emit，不用等全部完成。
- `SPECS: list[Spec]` 写死在模块里。除非真的有用户配置需求，**不要**搞
  `config.json` 配置化 —— 加一行 dataclass 比加一套配置 schema 便宜得多。

参考：`store/env_check.py` 的 `EnvSpec` / `EnvResult` / `check_one` /
`check_all` / `ENV_SPECS`。

### 2. `ui/<feature>_dialog.py` —— Worker + Dialog

#### Worker（QThread 子类）

```python
class XxxWorker(QThread):
    item_done = Signal(object)   # 每完成一项 emit 一次 Result

    def run(self) -> None:
        for result in check_all():
            if self.isInterruptionRequested():
                return
            self.item_done.emit(result)
```

要点：

- `item_done` 用 `Signal(object)` 携带 Result，Qt 跨线程信号会自动
  marshal 到 UI 线程，UI 端直接 connect 一个 slot 即可。
- 循环里检查 `isInterruptionRequested()`，让对话框关闭时能干净退出。
- 不要在 `run()` 里碰 widget。Worker 只产出数据,UI 渲染交给主线程 slot。

#### Dialog

- 构造时**预填行数和"检测中…"占位**,用户点开就能看见整张表的骨架,
  不会出现"空对话框 → 突然填满"的突兀感。
- `_on_item_done(result)` 通过 `result.name` 反查行号,**不要**依赖 emit 顺序
  与表格行序一致 —— 万一以后改成并发执行,这里就崩了。
- `_fill_row` 把状态/版本/路径塞进去,失败/异常用不同前缀符号区分:
  - `✓ 已安装` / `✗ 未安装` / `⚠ 异常`
  - 这三个符号在中文终端字体下都能正常渲染（`⚠` 这种歧义宽字符在终端里
    会撞中文,但**对话框是 Qt 原生渲染,不受影响**）。
- `closeEvent` 必须处理 worker 还没跑完的情况:

```python
def closeEvent(self, event) -> None:
    if self._worker.isRunning():
        self._worker.requestInterruption()
        self._worker.wait(4000)   # > 单项最坏耗时
    super().closeEvent(event)
```

不写这段,关对话框时 Qt 会打印 `QThread: Destroyed while thread is still
running` 警告,严重时崩溃。

#### 样式

把 stylesheet 放成模块级常量 `_DIALOG_STYLE`,集中改色不用翻 layout 代码。
颜色与 topbar 对齐(`#1e1e1e` / `#252526` / `#2d2d2d` / `#094771`)。

参考：`ui/env_check_dialog.py`。

### 3. `ui/main_window.py` —— 注册菜单项

```python
def __init__(self):
    ...
    self._build_menubar()       # central widget 之前调,菜单栏占据顶部
    central = QWidget()
    ...

def _build_menubar(self) -> None:
    menubar = self.menuBar()
    menubar.setStyleSheet(_MENUBAR_STYLE)        # 深色主题
    env_menu = menubar.addMenu("环境")
    act = env_menu.addAction("检测依赖")
    act.triggered.connect(self._on_check_env)

def _on_check_env(self) -> None:
    # 延迟 import：对话框模块只在用户点开时加载,启动期不付代价
    from ui.env_check_dialog import EnvCheckDialog
    EnvCheckDialog(self).exec()
```

要点：

- `_build_menubar` 必须在 `setCentralWidget` 之前调用,否则菜单栏与中央
  widget 的 layout 顺序会错。
- **延迟 import 对话框模块**:启动期主窗口 `__init__` 不去 import 任何
  feature 对话框,用户没点菜单就不付加载成本。
- 一个 feature 占一个 menu action,不要往一个 action 里塞多个功能。

## 加新菜单项的 5 步流水

假设要加一个「**工具 → ping 主机组**」:

1. **写 spec/result/逻辑** —— `store/ping_check.py`
   ```python
   @dataclass(frozen=True)
   class PingSpec: name: str; host: str; timeout: float
   @dataclass(frozen=True)
   class PingResult: name: str; reachable: bool; rtt_ms: float | None; error: str | None
   PING_SPECS = [PingSpec("Gateway", "192.168.1.1", 1.0), ...]
   def check_one(spec) -> PingResult: ...
   def check_all() -> Iterable[PingResult]: ...
   ```

2. **配套测试** —— `tests/test_ping_check.py`
   纯函数无 Qt 依赖,直接 parametrize。`check_one` 用真本机或 mock
   `subprocess.run`。

3. **对话框** —— `ui/ping_check_dialog.py`
   照抄 `env_check_dialog.py` 改 4 处:`COLUMNS` / `_fill_row` 字段映射 /
   `from store.ping_check import ...` / 标题。

4. **菜单注册** —— `ui/main_window.py`
   ```python
   tools_menu = menubar.addMenu("工具")
   ping_act = tools_menu.addAction("Ping 主机组")
   ping_act.triggered.connect(self._on_ping_check)

   def _on_ping_check(self) -> None:
       from ui.ping_check_dialog import PingCheckDialog
       PingCheckDialog(self).exec()
   ```

5. **跑测试** —— `pytest -q`,确保新逻辑覆盖且老用例没回归。

整个过程,UI 模板代码基本是复制粘贴,**新代码集中在 `store/` 那一层**——
这正是把 Qt 隔开的目的。

## 关键陷阱（已经踩过的）

### Windows 子进程闪黑窗

`subprocess.run([cli, "--version"])` 在 Windows 默认会弹一个 cmd 黑窗,检测
6 项就闪 6 下。修法：

```python
flags = 0
if sys.platform == "win32":
    flags = subprocess.CREATE_NO_WINDOW
subprocess.run([...], creationflags=flags)
```

`CREATE_NO_WINDOW` 是 Windows 专属常量,跨平台时必须 if-else 包一下。

### Windows 上 npm 全局命令是 .cmd

`where npm` / `where claude` 不带扩展名找不到,因为它们其实是 `npm.cmd`。
**用 `shutil.which`**,会按 `PATHEXT` 自动匹配 `.cmd` `.exe` `.bat`,无需
显式带扩展名。这也是 cross-platform 写法。

### `QThread` 必须等 worker 退出

`closeEvent` 不调 `wait()` 直接 `super().closeEvent()`,Qt 会打印
`QThread: Destroyed while thread is still running` 警告甚至崩溃。
`wait(timeout_ms)` 的 timeout 要 ≥ 单项最坏耗时(当前 6 项 × 3s 超时,但
中断只影响当前一项的循环判断,所以 4s 足够)。

### 子进程超时不能阻塞 UI

如果某个 CLI 装坏了 `--version` 卡住,`check_one` 必须有 `timeout=`,不然
worker 会僵死、对话框关不掉。当前 3s 是经验值,够普通工具响应,又不至于
让用户等太久。

### 不要把 Qt import 渗到 store/

每写一行 `from PySide6 import ...` 之前问一句:这个能放 `ui/` 吗?能就放
那边。`store/` 一旦碰 Qt,后续单测就要 `QApplication([])` 起来,既慢又
脆弱。

## 测试策略

| 层级               | 测什么                                | 怎么测                              |
|------------------|------------------------------------|-----------------------------------|
| `store/` 纯函数     | parse_version / check_one 边界       | parametrize 各种输出 + tmp_path 隔离环境 |
| `store/` 集成      | check_one 对真实工具(python)            | 直接调,断言 installed=True              |
| `ui/` Worker     | 一般不单测,行为简单                          | —                                 |
| `ui/` Dialog 渲染  | 一般不单测(成本高,价值低)                      | 实测                                |

参考 `tests/test_env_check.py` 的 8 个用例:6 个 parametrize 测正则解析,
1 个测找不到命令,1 个测真本机 python。

## 实测验收清单

加完一个新菜单项,至少手动跑过这 5 步:

1. 启动后菜单栏能看到新菜单,点开能看到 action。
2. 点 action 弹对话框,**马上**看到表格骨架(行数对、显示"检测中…")。
3. 逐行刷新成结果,顺序与列对齐正确。
4. 命令不存在的项显示 `✗ 未安装`,异常项显示 `⚠ 异常` + 原因。
5. 检测过程中关闭对话框,**不弹任何 Qt 警告**。

## 参考实现

- 逻辑层:`store/env_check.py`
- UI 层:`ui/env_check_dialog.py`
- 注册:`ui/main_window.py:_build_menubar` / `_on_check_env`
- 测试:`tests/test_env_check.py`
- 提交:`6f2acd6` 新增：菜单栏「环境 → 检测依赖」
