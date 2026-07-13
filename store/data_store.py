"""线程安全的内存数据缓存。

主线程读写，DataWorker 线程通过 take_snapshot_for_flush 获取快照并 flush 到 SQLite。
所有公开方法内部用 threading.Lock 保护。
"""
from __future__ import annotations

import threading


class DataStore:
    """线程安全的内存数据缓存。"""

    def __init__(self) -> None:
        self._path_history: list[str] = []
        self._shell_presets_data: dict = {}
        self._config_data: dict[str, str] = {}
        self._dirty_paths = False
        self._dirty_presets = False
        self._dirty_config = False
        self._lock = threading.Lock()
        # snapshot 状态记录（供 rollback_snapshot 精确恢复）
        self._snapshot_was_dirty: tuple[bool, bool, bool] = (False, False, False)

    # ── Path History ──────────────────────────────────────

    def add_path(self, path: str) -> None:
        """添加路径：去重 + 插头部 + 截断至 10 条。"""
        with self._lock:
            if path in self._path_history:
                self._path_history.remove(path)
            self._path_history.insert(0, path)
            del self._path_history[10:]
            self._dirty_paths = True

    def get_paths(self) -> list[str]:
        """返回路径历史副本。"""
        with self._lock:
            return list(self._path_history)

    def set_paths(self, paths: list[str]) -> None:
        """整量替换（迁移用）。"""
        with self._lock:
            self._path_history = list(paths)
            self._dirty_paths = True

    # ── Shell Presets ─────────────────────────────────────

    def get_shell_presets_data(self) -> dict:
        """返回 shell_presets 数据的浅拷贝。"""
        with self._lock:
            return dict(self._shell_presets_data)

    def set_shell_presets_data(self, data: dict) -> None:
        """整量替换 shell_presets 数据。"""
        with self._lock:
            self._shell_presets_data = dict(data)
            self._dirty_presets = True

    # ── Config ────────────────────────────────────────────

    def get_config_value(self, key: str, default: str | None = None) -> str | None:
        """读取单个配置项。"""
        with self._lock:
            return self._config_data.get(key, default)

    def set_config_value(self, key: str, value: str) -> None:
        """设置单个配置项。"""
        with self._lock:
            self._config_data[key] = value
            self._dirty_config = True

    def get_config_all(self) -> dict[str, str]:
        """返回全部配置副本。"""
        with self._lock:
            return dict(self._config_data)

    # ── Worker 线程接口 ───────────────────────────────────

    def is_any_dirty(self) -> bool:
        """持锁读取三个 dirty flag。"""
        with self._lock:
            return self._dirty_paths or self._dirty_presets or self._dirty_config

    def load_initial_data(
        self, paths: list[str], presets: dict, config: dict[str, str]
    ) -> None:
        """仅用于 DataWorker Phase 1 加载，不标记 dirty。"""
        with self._lock:
            self._path_history = list(paths)
            self._shell_presets_data = dict(presets)
            self._config_data = dict(config)

    def take_snapshot_for_flush(self) -> tuple[list | None, dict | None, dict | None]:
        """原子操作：复制脏数据 + 清除 dirty flag + 记录 snapshot 状态。"""
        with self._lock:
            paths = (
                list(self._path_history) if self._dirty_paths else None
            )
            presets = (
                dict(self._shell_presets_data) if self._dirty_presets else None
            )
            config = (
                dict(self._config_data) if self._dirty_config else None
            )
            self._snapshot_was_dirty = (
                self._dirty_paths,
                self._dirty_presets,
                self._dirty_config,
            )
            self._dirty_paths = False
            self._dirty_presets = False
            self._dirty_config = False
        return (paths, presets, config)

    def rollback_snapshot(self) -> None:
        """flush 失败时恢复原本 dirty 的 flag（不恢复全量）。"""
        with self._lock:
            dp, dpr, dc = self._snapshot_was_dirty
            if dp:
                self._dirty_paths = True
            if dpr:
                self._dirty_presets = True
            if dc:
                self._dirty_config = True
