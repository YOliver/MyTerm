import json
import os


class PathHistory:
    def __init__(self, filepath=None):
        if filepath is None:
            filepath = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "path_history.json"
            )
        self._filepath = filepath
        self._paths = self._load()

    def _load(self):
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self):
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump(self._paths, f, ensure_ascii=False)

    def add(self, path):
        path = os.path.normpath(path)
        if path in self._paths:
            self._paths.remove(path)
        self._paths.insert(0, path)
        if len(self._paths) > 10:
            self._paths = self._paths[:10]
        self._save()

    def all(self):
        return list(self._paths)
