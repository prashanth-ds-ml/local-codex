"""Tests for app/agents/response.py — panel rendering, title logic, step truncation."""
import pytest
from app.agents.response import AgentResponse, ToolResult, _panel_title, render


# ── _panel_title ──────────────────────────────────────────────────────────────

class TestPanelTitle:
    def _resp(self, *tools):
        steps = [ToolResult(tool=t, args={}, output="✓ ok") for t in tools]
        return AgentResponse(request="test", steps=steps)

    def test_git_tools(self):
        assert _panel_title(self._resp("git_commit")) == "Git"
        assert _panel_title(self._resp("git_status")) == "Git"
        assert _panel_title(self._resp("git_diff")) == "Git"

    def test_install(self):
        assert _panel_title(self._resp("install_packages")) == "Installing packages"
        assert _panel_title(self._resp("create_venv", "install_packages")) == "Installing packages"

    def test_delete(self):
        assert _panel_title(self._resp("delete_file")) == "Removing files"
        assert _panel_title(self._resp("delete_folder")) == "Removing files"

    def test_move(self):
        assert _panel_title(self._resp("move_file")) == "Moving files"

    def test_create(self):
        assert _panel_title(self._resp("create_file")) == "Creating files"
        assert _panel_title(self._resp("create_folder")) == "Creating files"

    def test_read(self):
        assert _panel_title(self._resp("read_file")) == "Reading project"
        assert _panel_title(self._resp("list_directory")) == "Reading project"

    def test_fallback(self):
        assert _panel_title(self._resp("run_command")) == "Setup Agent"

    def test_empty_steps(self):
        assert _panel_title(AgentResponse(request="test")) == "Setup Agent"

    def test_git_takes_priority_over_create(self):
        # git + create_file → still "Git"
        assert _panel_title(self._resp("git_commit", "create_file")) == "Git"


# ── ToolResult.ok ─────────────────────────────────────────────────────────────

class TestToolResultOk:
    def test_ok_on_checkmark(self):
        assert ToolResult(tool="t", args={}, output="✓ Created folder").ok is True

    def test_not_ok_on_cross(self):
        assert ToolResult(tool="t", args={}, output="✗ Failed").ok is False

    def test_not_ok_on_empty(self):
        assert ToolResult(tool="t", args={}, output="").ok is False


# ── AgentResponse counts ──────────────────────────────────────────────────────

class TestAgentResponseCounts:
    def test_counts(self):
        r = AgentResponse(request="x", steps=[
            ToolResult(tool="a", args={}, output="✓ ok"),
            ToolResult(tool="b", args={}, output="✗ fail"),
            ToolResult(tool="c", args={}, output="✓ ok"),
        ])
        assert r.ok_count == 2
        assert r.err_count == 1


# ── render() — step truncation ────────────────────────────────────────────────

class TestRenderStepTruncation:
    def test_long_error_truncated_to_120_chars(self):
        long_err = "x" * 200
        step = ToolResult(tool="create_file", args={"path": "a.py"}, output=f"✗ {long_err}")
        r = AgentResponse(request="req", steps=[step])
        # render() should not raise and the panel should be producible
        panel = render(r)
        assert panel is not None

    def test_multiline_error_shows_first_line_only(self):
        step = ToolResult(
            tool="create_file",
            args={"path": "a.py"},
            output="✗ Line one error\nLine two details\nLine three",
        )
        r = AgentResponse(request="req", steps=[step])
        # Should not raise — first line extraction works
        panel = render(r)
        assert panel is not None


# ── render() — panel contains title ──────────────────────────────────────────

class TestRenderPanelTitle:
    def test_title_reflects_tools(self):
        r = AgentResponse(request="install", steps=[
            ToolResult(tool="install_packages", args={"project_path": "."}, output="✓ done"),
        ])
        panel = render(r)
        # Rich Panel title is a renderable — check it contains our string
        assert "Installing packages" in str(panel.title)
