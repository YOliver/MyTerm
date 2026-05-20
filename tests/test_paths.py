"""路径解析测试。

通过 monkeypatch 翻转 ``sys.frozen`` 与 ``%APPDATA%/%LOCALAPPDATA%`` 来覆盖打包/开发两条分支，
不真正打包，也不污染用户 AppData。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from store import paths as paths_mod


# ---- 开发模式（默认 sys.frozen=False） ----


def test_dev_mode_uses_project_root(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    root = paths_mod.project_root()
    assert paths_mod.app_data_dir() == root
    assert paths_mod.local_data_dir() == root
    assert paths_mod.config_path() == root / "config.json"
    assert paths_mod.path_history_path() == root / "path_history.json"


def test_dev_mode_paste_cache_keeps_legacy_name(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths_mod.cache_dir("paste") == paths_mod.project_root() / ".paste_cache"


def test_dev_mode_other_cache_under_dot_cache(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths_mod.cache_dir("env") == paths_mod.project_root() / ".cache" / "env"
    assert paths_mod.cache_dir() == paths_mod.project_root() / ".cache"


# ---- 打包模式 ----


def _freeze(monkeypatch, appdata: Path, local: Path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("LOCALAPPDATA", str(local))


def test_frozen_uses_appdata(monkeypatch, tmp_path):
    appdata = tmp_path / "Roaming"
    local = tmp_path / "Local"
    _freeze(monkeypatch, appdata, local)
    assert paths_mod.app_data_dir() == appdata / "MyTerm"
    assert paths_mod.local_data_dir() == local / "MyTerm"
    assert paths_mod.cache_dir("paste") == local / "MyTerm" / "Cache" / "paste"
    assert paths_mod.cache_dir() == local / "MyTerm" / "Cache"


def test_frozen_missing_env_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Path.home() 在 Windows 读 USERPROFILE
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert paths_mod.app_data_dir() == tmp_path / "AppData" / "Roaming" / "MyTerm"
    assert paths_mod.local_data_dir() == tmp_path / "AppData" / "Local" / "MyTerm"


def test_ensure_dir_creates(tmp_path):
    target = tmp_path / "deep" / "nested"
    assert not target.exists()
    paths_mod.ensure_dir(target)
    assert target.is_dir()


def test_ensure_dir_idempotent(tmp_path):
    paths_mod.ensure_dir(tmp_path)
    paths_mod.ensure_dir(tmp_path)  # 第二次不应抛
    assert tmp_path.is_dir()


# ---- 迁移逻辑 ----


def test_migrate_noop_in_dev_mode(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    # 不应触发任何 IO；这里只验证不抛
    paths_mod.migrate_legacy_files()


def test_migrate_copies_from_exe_dir(monkeypatch, tmp_path):
    appdata = tmp_path / "Roaming"
    local = tmp_path / "Local"
    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    fake_root = tmp_path / "fake_root"
    fake_root.mkdir()
    (exe_dir / "config.json").write_text('{"max_terminals": 2}', encoding="utf-8")
    (exe_dir / "path_history.json").write_text('["c:/foo"]', encoding="utf-8")

    _freeze(monkeypatch, appdata, local)
    monkeypatch.setattr(paths_mod, "_exe_dir", lambda: exe_dir)
    monkeypatch.setattr(paths_mod, "project_root", lambda: fake_root)

    paths_mod.migrate_legacy_files()

    assert (appdata / "MyTerm" / "config.json").read_text(encoding="utf-8") == '{"max_terminals": 2}'
    assert (local / "MyTerm" / "path_history.json").read_text(encoding="utf-8") == '["c:/foo"]'
    # 哨兵已写入
    assert (appdata / "MyTerm" / ".migrated").is_file()


def test_migrate_skipped_when_target_exists(monkeypatch, tmp_path):
    appdata = tmp_path / "Roaming"
    local = tmp_path / "Local"
    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    fake_root = tmp_path / "fake_root"
    fake_root.mkdir()
    (exe_dir / "config.json").write_text("FROM_EXE", encoding="utf-8")

    # 目标已经有了，不应被覆盖
    (appdata / "MyTerm").mkdir(parents=True)
    (appdata / "MyTerm" / "config.json").write_text("EXISTING", encoding="utf-8")

    _freeze(monkeypatch, appdata, local)
    monkeypatch.setattr(paths_mod, "_exe_dir", lambda: exe_dir)
    monkeypatch.setattr(paths_mod, "project_root", lambda: fake_root)

    paths_mod.migrate_legacy_files()

    assert (appdata / "MyTerm" / "config.json").read_text(encoding="utf-8") == "EXISTING"


def test_migrate_runs_only_once(monkeypatch, tmp_path):
    appdata = tmp_path / "Roaming"
    local = tmp_path / "Local"
    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    fake_root = tmp_path / "fake_root"
    fake_root.mkdir()

    _freeze(monkeypatch, appdata, local)
    monkeypatch.setattr(paths_mod, "_exe_dir", lambda: exe_dir)
    monkeypatch.setattr(paths_mod, "project_root", lambda: fake_root)

    paths_mod.migrate_legacy_files()
    assert (appdata / "MyTerm" / ".migrated").is_file()
    assert not (appdata / "MyTerm" / "config.json").exists()

    # 第二次运行：即便 exe_dir 突然出现新的 config.json 也不该被搬
    (exe_dir / "config.json").write_text("NEW", encoding="utf-8")
    paths_mod.migrate_legacy_files()
    assert not (appdata / "MyTerm" / "config.json").exists()


def test_migrate_no_source_files_still_writes_sentinel(monkeypatch, tmp_path):
    appdata = tmp_path / "Roaming"
    local = tmp_path / "Local"
    exe_dir = tmp_path / "exe_empty"
    exe_dir.mkdir()
    _freeze(monkeypatch, appdata, local)
    monkeypatch.setattr(paths_mod, "_exe_dir", lambda: exe_dir)

    # 同时屏蔽工程根作为后备源：让 project_root 指向空目录
    empty_root = tmp_path / "fake_root"
    empty_root.mkdir()
    monkeypatch.setattr(paths_mod, "project_root", lambda: empty_root)

    paths_mod.migrate_legacy_files()
    assert not (appdata / "MyTerm" / "config.json").exists()
    assert (appdata / "MyTerm" / ".migrated").is_file()


def test_is_frozen_default_false(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths_mod.is_frozen() is False


def test_is_frozen_when_set(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert paths_mod.is_frozen() is True
