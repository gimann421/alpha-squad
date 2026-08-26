"""Regression test for the D35/D41 guardrail: `scripts/check_no_secrets.py` must actually catch
a real-looking secret value in a tracked *.env.example file, and must not false-positive on a
normal empty placeholder or a non-secret-shaped variable."""

from __future__ import annotations

from scripts.check_no_secrets import find_violations


def test_flags_a_nonempty_secret_shaped_value():
    lines = [
        "# a comment\n",
        "FANTASYPROS_API_KEY=sk-live-abcdef1234567890\n",
    ]
    violations = find_violations(".env.example", lines)
    assert len(violations) == 1
    assert "FANTASYPROS_API_KEY" in violations[0]
    assert ".env.example:2" in violations[0]


def test_does_not_flag_an_empty_placeholder():
    lines = ["CFBD_API_KEY=\n"]
    assert find_violations(".env.example", lines) == []


def test_does_not_flag_a_nonsecret_variable_with_a_real_value():
    lines = ["ALPHA_SQUAD_DATA_DIR=./data\n", "SLEEPER_BASE_URL=https://api.sleeper.app/v1\n"]
    assert find_violations(".env.example", lines) == []


def test_flags_secret_regardless_of_case_or_spacing():
    lines = ["  cfbd_api_key = abc123  \n"]
    violations = find_violations(".env.example", lines)
    assert len(violations) == 1


def test_ignores_comments_and_blank_lines():
    lines = ["\n", "# FANTASYPROS_API_KEY=abc123\n", "   \n"]
    assert find_violations(".env.example", lines) == []
