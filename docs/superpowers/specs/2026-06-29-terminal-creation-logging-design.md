# 终端创建流程逐节点日志设计

**日期**: 2026-06-29
**状态**: 待实现
**动机**: 用户遇到终端创建完全无响应的实际问题，需要逐节点耗时日志定位卡点。

---

## 一、背景

当前终端创建流程（`_on_launch` → `_add_terminal`）已有分散的 INFO/DEBUG 日志，但存在两个问题：

1. **日志无耗时信息**：各步骤之间有日志，但无法判断哪一步耗时异常
2. **盲区**：`TerminalWidget.__init__` 和 `_relayout` 两个关键步骤完全无日志

真实场景中，用户点击启动按钮后终端完全不出现，且现有日志无法精确定位卡在哪个节点。

## 二、方案

采用 **逐节点时间戳** 策略：

- 在 `_on_launch` 入口用 `time.perf_counter()` 记录起点
- 每个步骤输出 INFO 日志，附带距起点的累计耗时（毫秒）
- 所有新增日志 INFO 级别，不做开关，保证排查时始终可见

## 三、日志节点设计

### 3.1 `_on_launch()` — `main_window.py`

```
t0 = perf_counter()
├── [0ms]   入口（隐式，不需要日志）
├── [~0ms]  路径校验通过  "路径校验通过 path=%s"
├── [~1ms]  预设读取完成  "预设读取完成: label=%s cmd=%s"
├── [~2ms]  路径历史写入  "路径历史已写入"
├── [~3ms]  下拉框刷新    "下拉框已刷新"
└── [~3ms]  进入 add      "校验通过，进入 _add_terminal"
```

### 3.2 `_add_terminal()` — `main_window.py`

```
├── [~4ms]  找到空槽位    "空槽位 idx=%d (已用=%d/%d)"
├── [~4ms]  构造 backend  "TerminalBackend 构造完成"
├── [~5ms]  构造 widget   "TerminalWidget 构造完成: cols=%d rows=%d char=%dx%d font=%s pt=%d"
├── [~6ms]  调用 start    "调用 backend.start_shell() columns=%d rows=%d cwd=%s cmd=%s"
│   ├── [inside]  spawn 耗时  (由 TerminalBackend 内部记录，见 3.3)
├── [~Xms]  start 返回    "backend.start_shell() 返回，耗时 %dms"（关键！spawn 是最可能的卡点）
├── [~Xms]  信号连接      "process_exited 信号已连接"
├── [~Xms]  tile 创建     "_make_tile 完成"
├── [~Xms]  布局完成      "_relayout 完成: count=%d mode=%s grid=%dx%d total=%d"
├── [~Xms]  设置焦点      "setFocus 完成"
└── [~Xms]  创建完成      "终端会话创建完成 slot=%d"
```

### 3.3 `TerminalBackend.start_shell()` — `terminal_backend.py`

```
├── [before]  准备 spawn    "准备 PtyProcess.spawn: cmd=%s cwd=%s size=%dx%d"  (已有，保留并增加耗时计算)
├── [inside]  spawn 中      (无日志，系统调用阻塞中)
├── [after]   spawn 完成    "PtyProcess.spawn 完成，耗时 %dms，pid=%s"
└── [after]   QThread 启动  "QThread.start() 已调用"
```

### 3.4 `TerminalWidget.__init__()` — `terminal_widget.py`

在 `__init__` 末尾新增一条 INFO 日志，汇总关键初始化参数：

```python
logger.info(
    "TerminalWidget 初始化完成: screen=%dx%d history=%d "
    "font=%s size=%d char_wh=%dx%d",
    cols, rows, history,
    self._font.family(), self._font.pointSize(),
    self._char_width, self._char_height,
)
```

## 四、改动清单

| 文件 | 新增行数 | 关键改动 |
|------|---------|---------|
| `main_window.py` `_on_launch` | ~10 行 | 加 t0 + 逐节点耗时日志 |
| `main_window.py` `_add_terminal` | ~12 行 | 细化子步骤为 INFO + 记录 spawn 耗时 |
| `main_window.py` `_relayout` | ~1 行 | 新增布局参数日志 |
| `terminal_backend.py` `start_shell` | ~3 行 | spawn 前后加计时 |
| `terminal_widget.py` `__init__` | ~3 行 | 新增初始化参数汇总日志 |

总计约 **30 行新增代码**，不删不改现有逻辑。

## 五、不做的

- 不引入新的工具类或计时器封装，直接 `perf_counter()` 内联使用
- 不添加日志开关或命令行参数，INFO 级别始终输出
- 不修改 `_make_tile` 日志（纯 UI 装饰，非阻塞路径）
- 不修改 `PathHistory` 日志（已有 `_load/_save` DEBUG 足够）
- 不修改 `TerminalBackend.__init__`（构造体极简，无操作可卡住）

## 六、期望效果

正常创建终端时，日志形如：

```
[INFO] _on_launch [0.2ms] 路径校验通过 path=C:\Users
[INFO] _on_launch [0.4ms] 预设读取完成: label=PowerShell cmd=['powershell.exe']
[INFO] _on_launch [0.6ms] 路径历史已写入
[INFO] _on_launch [0.8ms] 下拉框已刷新
[INFO] _on_launch [1.0ms] 校验通过，进入 _add_terminal
[INFO] _add_terminal [1.1ms] 空槽位 idx=0 (已用=0/4)
[INFO] _add_terminal [1.2ms] TerminalBackend 构造完成
[INFO] TerminalWidget 初始化完成: screen=80x24 history=2000 font=Consolas size=14 char_wh=9x21
[INFO] _add_terminal [2.5ms] TerminalWidget 构造完成
[INFO] 准备 PtyProcess.spawn: cmd=['powershell.exe'] cwd=C:\Users size=24x80
[INFO] PtyProcess.spawn 完成，耗时 45ms，pid=12345
[INFO] QThread.start() 已调用
[INFO] _add_terminal [49.0ms] backend.start_shell() 返回，耗时 45ms
[INFO] _add_terminal [49.1ms] process_exited 信号已连接
[INFO] _add_terminal [49.5ms] _make_tile 完成
[INFO] _relayout 完成: count=1 mode=grid grid=1x1 total=1
[INFO] _add_terminal [50.0ms] setFocus 完成
[INFO] _add_terminal [50.1ms] 终端会话创建完成 slot=0
```

异常时，最后一行日志之前就是卡住的节点。例如：

```
[INFO] PtyProcess.spawn 完成，耗时 45ms，pid=12345
[INFO] QThread.start() 已调用
[INFO] _add_terminal [49.0ms] backend.start_shell() 返回，耗时 45ms
（后面没了 — 说明卡在 _add_terminal 的 start_shell 返回后的某个步骤）
```

或者：

```
[INFO] 准备 PtyProcess.spawn: cmd=['powershell.exe'] cwd=C:\Users size=24x80
（后面没了 — 说明卡在 PtyProcess.spawn() 系统调用中）
```
