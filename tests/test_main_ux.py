"""Tests for app/main.py — error handling, hint bar, completer, extract_command."""
import pathlib
import sys

import pytest

# Ensure project root is importable
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.main import (
    _friendly_error,
    _extract_command,
    _make_completer,
    _SLASH_COMMANDS,
    _resolve_codegen_model,
    _resolve_cloud_api_key,
)


# ── _friendly_error ───────────────────────────────────────────────────────────

class TestFriendlyError:
    def test_ollama_connection(self):
        msg = _friendly_error(Exception("connection refused by server"))
        assert "Ollama" in msg

    def test_validation_error(self):
        msg = _friendly_error(Exception("1 validation error for install_packages"))
        assert "tool" in msg.lower() or "model" in msg.lower()

    def test_list_type(self):
        msg = _friendly_error(Exception("list_type: Input should be a valid list"))
        assert "Package" in msg or "package" in msg

    def test_context_length(self):
        msg = _friendly_error(Exception("context length exceeded 32768 tokens"))
        assert "/reset" in msg

    def test_unknown_error_includes_original(self):
        msg = _friendly_error(Exception("something totally unknown happened"))
        assert "something totally unknown" in msg


# ── _extract_command ──────────────────────────────────────────────────────────

class TestExtractCommand:
    def test_backtick_extracts_command(self):
        assert _extract_command("please run `python main.py` for me") == "python main.py"

    def test_no_backtick_returns_full_string(self):
        raw = "run the snake game"
        assert _extract_command(raw) == raw

    def test_first_backtick_wins(self):
        assert _extract_command("`pytest` then `ruff`") == "pytest"

    def test_empty_string(self):
        assert _extract_command("") == ""


# ── _SLASH_COMMANDS ───────────────────────────────────────────────────────────

class TestSlashCommands:
    def test_all_expected_commands_present(self):
        expected = {"/init", "/run", "/plan", "/memory", "/context", "/reset", "/help"}
        assert expected.issubset(set(_SLASH_COMMANDS))


# ── _make_completer ───────────────────────────────────────────────────────────

class TestMakeCompleter:
    def test_completer_includes_slash_commands(self, tmp_path):
        completer = _make_completer(str(tmp_path))
        words = set(completer.words)
        assert "/help" in words
        assert "/run" in words

    def test_completer_includes_workspace_files(self, tmp_path):
        (tmp_path / "main.py").write_text("pass")
        (tmp_path / "utils.py").write_text("pass")
        completer = _make_completer(str(tmp_path))
        words = set(completer.words)
        assert "main.py" in words
        assert "utils.py" in words

    def test_completer_excludes_hidden_files(self, tmp_path):
        (tmp_path / ".env").write_text("SECRET=1")
        completer = _make_completer(str(tmp_path))
        words = set(completer.words)
        assert ".env" not in words

    def test_bad_workspace_does_not_raise(self):
        # Should not raise even if workspace doesn't exist
        completer = _make_completer("/nonexistent/path/xyz")
        assert completer is not None


class TestCloudRoutingConfig:
    def test_codegen_model_defaults_to_cloud_model(self):
        assert _resolve_codegen_model({}) == "kimi-k2.5:cloud"

    def test_codegen_model_prefers_configured_value(self):
        assert _resolve_codegen_model({"codegen_model": "gpt-oss:120b"}) == "gpt-oss:120b"

    def test_api_key_prefers_config(self):
        value = _resolve_cloud_api_key(
            {"ollama_api_key": "cfg-secret"},
            prompt_fn=lambda _: "should-not-be-used",
        )
        assert value == "cfg-secret"

    def test_api_key_can_be_entered_interactively(self):
        value = _resolve_cloud_api_key({}, prompt_fn=lambda _: "typed-secret")
        assert value == "typed-secret"

    def test_empty_api_key_keeps_local_mode(self):
        value = _resolve_cloud_api_key({}, prompt_fn=lambda _: "")
        assert value == ""
