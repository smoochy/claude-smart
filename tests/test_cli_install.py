"""Tests for Claude Code install bootstrap recovery paths."""

from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path

from claude_smart import cli


def _installed_plugin(tmp_path: Path, version: str = "9.8.7") -> Path:
    root = (
        tmp_path
        / ".claude"
        / "plugins"
        / "cache"
        / "reflexioai"
        / "claude-smart"
        / version
    )
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='claude-smart'\n")
    install = scripts / "smart-install.sh"
    install.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$PWD\" > \"$HOME/bootstrap-ran\"\n")
    install.chmod(install.stat().st_mode | stat.S_IXUSR)
    return root


def _isolate_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(cli, "_REFLEXIO_DIR", tmp_path / ".reflexio")
    monkeypatch.setattr(cli, "_INSTALL_FAILURE_MARKER", tmp_path / ".claude-smart" / "install-failed")
    monkeypatch.setenv("HOME", str(tmp_path))


def test_bootstrap_claude_code_install_runs_installed_smart_install(
    monkeypatch,
    tmp_path: Path,
) -> None:
    plugin_root = _installed_plugin(tmp_path)
    _isolate_home(monkeypatch, tmp_path)

    ok, message = cli._bootstrap_claude_code_install()

    assert ok, message
    assert message == str(plugin_root)
    assert (tmp_path / "bootstrap-ran").read_text().strip() == str(plugin_root)
    assert (tmp_path / ".reflexio" / "plugin-root").resolve() == plugin_root


def test_bootstrap_claude_code_install_reports_failure_marker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    plugin_root = _installed_plugin(tmp_path)
    install = plugin_root / "scripts" / "smart-install.sh"
    install.write_text(
        "#!/usr/bin/env bash\n"
        "mkdir -p \"$HOME/.claude-smart\"\n"
        "printf 'network unavailable\\n' > \"$HOME/.claude-smart/install-failed\"\n"
    )
    install.chmod(install.stat().st_mode | stat.S_IXUSR)
    _isolate_home(monkeypatch, tmp_path)

    ok, message = cli._bootstrap_claude_code_install()

    assert not ok
    assert message == "network unavailable"


def test_bootstrap_claude_code_install_refuses_real_plugin_root_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _installed_plugin(tmp_path)
    _isolate_home(monkeypatch, tmp_path)
    real_dir = tmp_path / ".reflexio" / "plugin-root"
    real_dir.mkdir(parents=True)
    sentinel = real_dir / "keep.txt"
    sentinel.write_text("do not delete")

    ok, message = cli._bootstrap_claude_code_install()

    assert not ok
    assert "refusing to replace non-symlink plugin-root" in message
    assert sentinel.read_text() == "do not delete"


def test_cmd_install_fails_when_dependency_bootstrap_fails(monkeypatch, tmp_path: Path) -> None:
    _installed_plugin(tmp_path)
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: argparse.Namespace(returncode=0))
    monkeypatch.setattr(cli, "_bootstrap_claude_code_install", lambda: (False, "uv failed"))

    rc = cli.cmd_install(argparse.Namespace(host="claude-code", source="unused"))

    assert rc == 1
