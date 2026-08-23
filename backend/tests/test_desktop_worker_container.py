from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "containers/sovereign-desktop-worker/desktop_worker.py"


def _worker_module(tmp_path: Path, monkeypatch):
    view = tmp_path / "view.scope"
    input_scope = tmp_path / "input.scope"
    view.write_text("view-scope-value-that-is-long-enough-0001", "utf-8")
    input_scope.write_text("input-scope-value-that-is-long-enough-0002", "utf-8")
    monkeypatch.setenv("DESKTOP_VIEW_SCOPE_FILE", str(view))
    monkeypatch.setenv("DESKTOP_INPUT_SCOPE_FILE", str(input_scope))
    monkeypatch.setenv("DESKTOP_RUNTIME_IDENTITY_HASH", "a" * 64)
    module_name = f"desktop_worker_test_{tmp_path.name}"
    spec = importlib.util.spec_from_file_location(module_name, SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_desktop_worker_source_compiles_without_provider_or_shell_layers() -> None:
    result = subprocess.run([sys.executable, "-m", "py_compile", str(SOURCE)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    source = SOURCE.read_text("utf-8")
    assert "shell=True" not in source
    assert "LiteLLM" not in source
    assert "docker.sock" not in source


def test_computer_use_command_builder_allows_only_bounded_argv(tmp_path: Path, monkeypatch) -> None:
    worker = _worker_module(tmp_path, monkeypatch)
    action, argv, normalized = worker._safe_command({"action": "click", "x": 11, "y": 22, "button": "left"})
    assert action == "click"
    assert argv == ["xdotool", "mousemove", "--sync", "11", "22", "click", "1"]
    assert normalized == {"x": 11, "y": 22, "button": "left"}
    typed_action, typed_argv, typed_normalized = worker._safe_command({"action": "type", "text": "safe text"})
    assert typed_action == "type"
    assert typed_argv[:4] == ["xdotool", "type", "--clearmodifiers", "--delay"]
    assert "text" not in typed_normalized
    with pytest.raises(ValueError, match="forbidden"):
        worker._safe_command({"action": "shell_root", "command": "id"})
    with pytest.raises(ValueError, match="forbidden"):
        worker._safe_command({"action": "keypress", "key": "ctrl+alt+Delete;rm"})
