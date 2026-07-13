"""路径历史：内存操作委托给 DataStore，不再直接读写文件。

当 ``store=None`` 时回退到旧版文件读写（向后兼容需要无 DataStore 的调用方）。
"""
from __future__ import annotations

import json
import logging
import os

from store.data_store import DataStore

logger = logging.getLogger(__name__)


class PathHistory:
    """路径历史管理器。add/all 委托给 DataStore 内存缓存（新），或直接读写文件（旧）。"""

    def __init__(self, store: DataStore | None = None) -> None:
        if store is not None:
            self._store: DataStore = store
        else:
            from store.paths import ensure_dir, local_data_dir, path_history_path
            ensure_dir(local_data_dir())
            self._filepath = str(path_history_path())
            self._paths = self._load()

    def _load(self) -> list[str]:
        try:
            file_size = os.path.getsize(self._filepath)
        except OSError:
            file_size = -1
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.debug("路径历史加载: file=%s size=%d 条目=%d",
                          self._filepath, file_size, len(data))
            return data
        except FileNotFoundError:
            logger.debug("路径历史文件不存在: %s", self._filepath)
            return []
        except json.JSONDecodeError as e:
            logger.warning("路径历史文件损坏: file=%s size=%d err=%s",
                            self._filepath, file_size, e)
            return []

    def _save(self) -> None:
        logger.debug("路径历史保存: file=%s 条目=%d",
                      self._filepath, len(self._paths))
        try:
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(self._paths, f, ensure_ascii=False)
        except OSError:
            logger.exception("路径历史保存失败: %s", self._filepath)

    def add(self, path: str) -> None:
        """添加路径到历史。有 store 时走纯内存操作，否则走旧版文件 I/O。"""
        path = os.path.normpath(path)
        if hasattr(self, '_store'):
            self._store.add_path(path)
        else:
            existed = path in self._paths
            if existed:
                self._paths.remove(path)
            self._paths.insert(0, path)
            if len(self._paths) > 10:
                self._paths = self._paths[:10]
            logger.debug("路径历史 add: path=%s existed=%s 结果=%d 条",
                          path, existed, len(self._paths))
            self._save()

    def all(self) -> list[str]:
        """返回当前路径历史副本。"""
        if hasattr(self, '_store'):
            return self._store.get_paths()
        return list(self._paths)
