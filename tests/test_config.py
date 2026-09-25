"""Tests for application settings."""

import pytest

from logistics_tower.config import Settings


def test_settings_accepts_llm_provider_aliases(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llama")
    assert Settings().llm_provider == "ollama"
    monkeypatch.setenv("LLM_PROVIDER", "google")
    assert Settings().llm_provider == "gemini"
    monkeypatch.setenv("LLM_PROVIDER", "banana")
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        Settings()
