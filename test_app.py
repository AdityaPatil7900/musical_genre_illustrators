"""
Unit tests for the local pipeline pieces (classifier + local image gen).
Run with: pytest test_app.py
No remote API calls required for these to pass.
"""

import os
import pytest
from app import (
    classify_audio,
    generate_image_local,
    create_visual_prompt,
    FALLBACK_PROMPTS,
    _remote_breaker,
)

SAMPLE_AUDIO = os.path.join(os.path.dirname(__file__), "sample.wav")


@pytest.mark.skipif(
    not os.path.exists(SAMPLE_AUDIO),
    reason="sample.wav not present - add a short test clip to run this test",
)
def test_classify_audio_returns_genre_and_confidence():
    genre, confidence = classify_audio(SAMPLE_AUDIO)
    assert isinstance(genre, str)
    assert 0.0 <= confidence <= 1.0


def test_classify_audio_handles_none():
    genre, confidence = classify_audio(None)
    assert genre == "unknown"
    assert confidence == 0.0


def test_generate_image_local_returns_image():
    prompt = FALLBACK_PROMPTS["jazz"]
    image = generate_image_local(prompt)
    assert image is not None


# ---------------------------------------------------------------------------
# Adaptive LLM failover (Phase 6)
# These tests stub out the local LLM call so they don't need to download
# LOCAL_TEXT_MODEL_ID; they only exercise the routing/failover logic.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    """Each test starts with the remote LLM considered healthy."""
    _remote_breaker.unavailable_until = 0.0
    _remote_breaker.last_reason = None
    yield
    _remote_breaker.unavailable_until = 0.0
    _remote_breaker.last_reason = None


def test_simulated_remote_failure_routes_to_local_llm(monkeypatch):
    monkeypatch.setattr(
        "app.generate_prompt_local", lambda instruction: "a local-llm-generated prompt"
    )

    prompt, source = create_visual_prompt("jazz", hf_token=None, simulate_remote_failure=True)

    assert prompt == "a local-llm-generated prompt"
    assert "Local LLM" in source
    assert "failover" in source.lower()
    assert _remote_breaker.is_down()


def test_remote_stays_in_cooldown_after_a_failure_and_skips_straight_to_local(monkeypatch):
    monkeypatch.setattr(
        "app.generate_prompt_local", lambda instruction: "a local-llm-generated prompt"
    )

    # First call fails over and puts the remote LLM into cooldown.
    create_visual_prompt("jazz", hf_token=None, simulate_remote_failure=True)
    assert _remote_breaker.is_down()

    # A second call, even without forcing failure, should not attempt the
    # remote API again while it's in cooldown -- it goes straight to local.
    prompt, source = create_visual_prompt("jazz", hf_token=None, simulate_remote_failure=False)
    assert "Local LLM" in source


def test_both_llms_unavailable_falls_back_to_static_template(monkeypatch):
    def _boom(instruction):
        raise RuntimeError("local model also unavailable")

    monkeypatch.setattr("app.generate_prompt_local", _boom)

    prompt, source = create_visual_prompt("jazz", hf_token=None, simulate_remote_failure=True)

    assert prompt == FALLBACK_PROMPTS["jazz"]
    assert "fallback" in source.lower()
