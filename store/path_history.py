import json
import logging
import os

logger = logging.getLogger(__name__)


class PathHistory:
    def __init__(self, filepath=None):
        if filepath is None:
            from store.paths import ensure_dir, local_data_dir, path_history_path
            ensure_dir(local_data_dir())
            filepath = str(path_history_path())
        self._filepath = filepath
        self._paths = self._load()

    def _load(self):
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

    def _save(self):
        logger.debug("路径历史保存: file=%s 条目=%d paths=%s",
                      self._filepath, len(self._paths), self._paths)
        tmp_path = self._filepath + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._paths, f, ensure_ascii=False)
            os.replace(tmp_path, self._filepath)
        except OSError:
            logger.exception("路径历史保存失败: %s", self._filepath)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def add(self, path):
        path = os.path.normpath(path)
        existed = path in self._paths
        if existed:
            self._paths.remove(path)
        self._paths.insert(0, path)
        if len(self._paths) > 10:
            self._paths = self._paths[:10]
        logger.debug("路径历史 add: path=%s existed=%s 结果=%d 条",
                      path, existed, len(self._paths))
        self._save()

    def all(self):
        return list(self._paths)
