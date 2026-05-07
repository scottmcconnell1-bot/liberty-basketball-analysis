"""
Tests for LLM integration — Ollama practice AI notes.

Tests cover:
  - call_ollama() with mocked subprocess
  - generate_practice_ai_notes_llm() with various settings
  - build_practice_ai_notes() LLM vs heuristic fallback
"""

import json
import subprocess
import pytest


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def sample_practice():
    return {
        "id": 1,
        "season_id": 1,
        "practice_date": "2025-12-22",
        "level": "varsity",
        "status": "completed",
        "plan_text": "Shell defense and transition offense. Work on closeouts.",
        "coach_notes": "Good energy. Need to improve communication on switches.",
        "ai_notes": "",
        "combined_summary": "",
        "plan_source": "manual",
    }


@pytest.fixture
def settings_llm_enabled():
    return {
        "features": {"ENABLE_PRACTICES": True},
        "analysis": {},
        "ai": {
            "llm_provider": "ollama",
            "llm_model": "llama3",
        },
    }


@pytest.fixture
def settings_llm_disabled():
    return {
        "features": {"ENABLE_PRACTICES": True},
        "analysis": {},
        "ai": {
            "llm_provider": "none",
            "llm_model": "",
        },
    }


# ── Tests: call_ollama ─────────────────────────────────────────

class TestCallOllama:
    def test_returns_success_on_ok(self, monkeypatch):
        """call_ollama returns (True, text) when Ollama succeeds."""
        def fake_run(*args, **kwargs):
            class Result:
                returncode = 0
                stdout = "This is the LLM response."
                stderr = ""
            return Result()

        monkeypatch.setattr(subprocess, "run", fake_run)
        from helpers import call_ollama
        ok, text = call_ollama("test prompt", model="llama3")
        assert ok is True
        assert text == "This is the LLM response."

    def test_returns_error_on_missing_ollama(self, monkeypatch):
        """call_ollama returns (False, msg) when Ollama binary is missing."""
        def fake_run(*args, **kwargs):
            raise FileNotFoundError("ollama not found")

        monkeypatch.setattr(subprocess, "run", fake_run)
        from helpers import call_ollama
        ok, text = call_ollama("test prompt", model="llama3")
        assert ok is False
        assert "not installed" in text

    def test_returns_error_on_timeout(self, monkeypatch):
        """call_ollama returns (False, msg) on timeout."""
        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="ollama", timeout=60)

        monkeypatch.setattr(subprocess, "run", fake_run)
        from helpers import call_ollama
        ok, text = call_ollama("test prompt", model="llama3")
        assert ok is False
        assert "timed out" in text

    def test_returns_error_on_nonzero_exit(self, monkeypatch):
        """call_ollama returns (False, msg) when Ollama exits non-zero."""
        def fake_run(*args, **kwargs):
            class Result:
                returncode = 1
                stdout = ""
                stderr = "model not found"
            return Result()

        monkeypatch.setattr(subprocess, "run", fake_run)
        from helpers import call_ollama
        ok, text = call_ollama("test prompt", model="nonexistent")
        assert ok is False

    def test_uses_default_model(self, monkeypatch):
        """call_ollama defaults to 'llama3' when model is None."""
        captured_args = {}

        def fake_run(args, **kwargs):
            captured_args["cmd"] = args
            class Result:
                returncode = 0
                stdout = "ok"
                stderr = ""
            return Result()

        monkeypatch.setattr(subprocess, "run", fake_run)
        from helpers import call_ollama
        call_ollama("test", model=None)
        assert captured_args["cmd"] == ["ollama", "run", "llama3"]


# ── Tests: generate_practice_ai_notes_llm ───────────────────────

class TestGeneratePracticeAiNotesLlm:
    def test_returns_none_when_provider_disabled(self, sample_practice, settings_llm_disabled):
        """Returns (None, 'none') when LLM provider is not 'ollama'."""
        from helpers import generate_practice_ai_notes_llm
        notes, source = generate_practice_ai_notes_llm(sample_practice, settings_llm_disabled)
        assert notes is None
        assert source == "none"

    def test_returns_none_when_model_empty(self, sample_practice):
        """Returns (None, 'none') when no model is configured."""
        settings = {
            "features": {},
            "analysis": {},
            "ai": {"llm_provider": "ollama", "llm_model": ""},
        }
        from helpers import generate_practice_ai_notes_llm
        notes, source = generate_practice_ai_notes_llm(sample_practice, settings)
        assert notes is None
        assert source == "none"

    def test_returns_none_when_model_not_installed(self, sample_practice, settings_llm_enabled, monkeypatch):
        """Returns (None, 'none') when configured model is not in Ollama."""
        monkeypatch.setattr("helpers.list_ollama_models", lambda: ["mistral", "phi3"])
        from helpers import generate_practice_ai_notes_llm
        notes, source = generate_practice_ai_notes_llm(sample_practice, settings_llm_enabled)
        assert notes is None
        assert source == "none"

    def test_returns_llm_notes_when_available(self, sample_practice, settings_llm_enabled, monkeypatch):
        """Returns (notes, 'llm') when Ollama call succeeds."""
        monkeypatch.setattr("helpers.list_ollama_models", lambda: ["llama3"])
        monkeypatch.setattr(
            "helpers.call_ollama",
            lambda prompt, model=None, timeout=60: (True, "Defense was the focus. Communication needs work."),
        )
        from helpers import generate_practice_ai_notes_llm
        notes, source = generate_practice_ai_notes_llm(sample_practice, settings_llm_enabled)
        assert notes == "Defense was the focus. Communication needs work."
        assert source == "llm"

    def test_falls_back_when_ollama_fails(self, sample_practice, settings_llm_enabled, monkeypatch):
        """Returns (None, 'none') when Ollama returns an error."""
        monkeypatch.setattr("helpers.list_ollama_models", lambda: ["llama3"])
        monkeypatch.setattr(
            "helpers.call_ollama",
            lambda prompt, model=None, timeout=60: (False, "connection refused"),
        )
        from helpers import generate_practice_ai_notes_llm
        notes, source = generate_practice_ai_notes_llm(sample_practice, settings_llm_enabled)
        assert notes is None
        assert source == "none"

    def test_prompt_includes_practice_details(self, sample_practice, settings_llm_enabled, monkeypatch):
        """The prompt sent to Ollama includes plan text and coach notes."""
        captured_prompts = {}

        monkeypatch.setattr("helpers.list_ollama_models", lambda: ["llama3"])
        monkeypatch.setattr(
            "helpers.call_ollama",
            lambda prompt, model=None, timeout=60: (captured_prompts.update({"prompt": prompt}) or (True, "ok")),
        )
        from helpers import generate_practice_ai_notes_llm
        generate_practice_ai_notes_llm(sample_practice, settings_llm_enabled)
        prompt = captured_prompts["prompt"]
        assert "Shell defense" in prompt
        assert "Good energy" in prompt
        assert "2025-12-22" in prompt
        assert "completed" in prompt


# ── Tests: build_practice_ai_notes (integration) ────────────────

class TestBuildPracticeAiNotes:
    def test_heuristic_fallback_when_llm_disabled(self, sample_practice, settings_llm_disabled):
        """When LLM is disabled, falls back to heuristic output."""
        from helpers import build_practice_ai_notes
        notes = build_practice_ai_notes(sample_practice, settings_llm_disabled)
        assert "Plan focus:" in notes
        assert "Coach notes:" in notes
        assert "Shell defense" in notes
        assert "Good energy" in notes

    def test_heuristic_identifies_theme(self, sample_practice, settings_llm_disabled):
        """Heuristic fallback identifies defense theme from plan text."""
        from helpers import build_practice_ai_notes
        notes = build_practice_ai_notes(sample_practice, settings_llm_disabled)
        assert "defense" in notes.lower() or "defensive" in notes.lower()

    def test_heuristic_handles_empty_notes(self, settings_llm_disabled):
        """Heuristic handles practice with no plan or coach notes."""
        practice = {
            "id": 2,
            "plan_text": "",
            "coach_notes": "",
            "practice_date": "2025-01-01",
            "status": "planned",
        }
        from helpers import build_practice_ai_notes
        notes = build_practice_ai_notes(practice, settings_llm_disabled)
        assert "Plan focus:" in notes
        assert "Coach notes:" in notes

    def test_llm_takes_priority_when_available(self, sample_practice, settings_llm_enabled, monkeypatch):
        """When LLM is available and returns notes, uses those instead of heuristic."""
        monkeypatch.setattr("helpers.list_ollama_models", lambda: ["llama3"])
        monkeypatch.setattr(
            "helpers.call_ollama",
            lambda prompt, model=None, timeout=60: (True, "LLM-generated summary here."),
        )
        from helpers import build_practice_ai_notes
        notes = build_practice_ai_notes(sample_practice, settings_llm_enabled)
        assert notes == "LLM-generated summary here."

    def test_no_llm_returns_heuristic(self, sample_practice, settings_llm_enabled, monkeypatch):
        """When Ollama fails, falls back to heuristic."""
        monkeypatch.setattr("helpers.list_ollama_models", lambda: ["llama3"])
        monkeypatch.setattr(
            "helpers.call_ollama",
            lambda prompt, model=None, timeout=60: (False, "error"),
        )
        from helpers import build_practice_ai_notes
        notes = build_practice_ai_notes(sample_practice, settings_llm_enabled)
        # Should have heuristic output
        assert "Plan focus:" in notes
        assert "Coach notes:" in notes
