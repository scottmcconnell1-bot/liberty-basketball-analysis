"""Tests for scripts/launch_liberty.py helpers."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import launch_liberty as launcher


def test_python_ok_accepts_312_and_313():
    assert launcher._python_ok((3, 12, 0)) is True
    assert launcher._python_ok((3, 13, 1)) is True
    assert launcher._python_ok((3, 11, 9)) is False
    assert launcher._python_ok((3, 14, 0)) is False


def test_find_system_python_returns_current_interpreter():
    cmd = launcher._find_system_python()
    assert cmd
    assert cmd[0]


def test_venv_python_path_under_repo():
    path = launcher._venv_python()
    assert path.name.startswith("python")
    assert ".venv" in str(path)


def test_film_tool_build_info_detects_controls_v2():
    info = launcher.film_tool_build_info()
    assert info["has_tagging_controls_v2"] is True
    assert info["has_focus_mode"] is True


def test_film_tool_template_has_fullscreen_focus_drawer():
    text = launcher.FILM_TOOL_TEMPLATE.read_text(encoding="utf-8")
    assert "focus-roster-starters-20260717a" in text
    assert "ft-tag-drawer-open" in text
