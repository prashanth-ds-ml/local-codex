"""Tests for app/agents/shell.py — execute, whitelist, confirm, ShellResult."""
import pathlib
import pytest
from app.agents import shell as shell_agent


@pytest.fixture(autouse=True)
def reset_config(tmp_path):
    """Reset shell config to a clean state before each test."""
    shell_agent.configure(
        workspace=str(tmp_path),
        stream_to_console=False,
        confirm_fn=None,
    )
    yield


# ── Whitelist ─────────────────────────────────────────────────────────────────

class TestWhitelist:
    def test_python_allowed(self, tmp_path):
        result = shell_agent.execute("python --version", cwd=str(tmp_path))
        assert result.ok
        assert result.exit_code == 0

    def test_rm_blocked(self, tmp_path):
        result = shell_agent.execute("rm -rf .", cwd=str(tmp_path))
        assert not result.ok
        assert "Permission denied" in result.output

    def test_curl_blocked(self, tmp_path):
        result = shell_agent.execute("curl https://example.com", cwd=str(tmp_path))
        assert not result.ok
        assert "Permission denied" in result.output

    def test_empty_command_blocked(self, tmp_path):
        result = shell_agent.execute("", cwd=str(tmp_path))
        assert not result.ok


# ── confirm_fn ────────────────────────────────────────────────────────────────

class TestConfirmFn:
    def test_deny_skips_execution(self, tmp_path):
        shell_agent.configure(workspace=str(tmp_path), confirm_fn=lambda cmd: False, stream_to_console=False)
        result = shell_agent.execute("python --version", cwd=str(tmp_path))
        assert result.denied is True
        assert result.exit_code == 1

    def test_approve_runs_command(self, tmp_path):
        shell_agent.configure(workspace=str(tmp_path), confirm_fn=lambda cmd: True, stream_to_console=False)
        result = shell_agent.execute("python --version", cwd=str(tmp_path))
        assert result.ok

    def test_no_confirm_fn_auto_runs(self, tmp_path):
        shell_agent.configure(workspace=str(tmp_path), confirm_fn=None, stream_to_console=False)
        result = shell_agent.execute("python --version", cwd=str(tmp_path))
        assert result.ok


# ── ShellResult ───────────────────────────────────────────────────────────────

class TestShellResult:
    def test_ok_true_on_exit_0(self, tmp_path):
        result = shell_agent.execute("python --version", cwd=str(tmp_path))
        assert result.ok is True

    def test_tail_returns_last_30_lines(self):
        from app.agents.shell import ShellResult
        lines = [str(i) for i in range(100)]
        r = ShellResult(command="x", cwd=".", exit_code=0, output_lines=lines)
        tail_lines = r.tail.splitlines()
        assert len(tail_lines) == 30
        assert tail_lines[-1] == "99"

    def test_to_llm_summary_contains_exit_code(self):
        from app.agents.shell import ShellResult
        r = ShellResult(command="pytest", cwd=".", exit_code=1, output_lines=["FAILED"])
        summary = r.to_llm_summary()
        assert "Exit code: 1" in summary
        assert "FAILED" in summary

    def test_to_llm_summary_ok_status(self):
        from app.agents.shell import ShellResult
        r = ShellResult(command="pytest", cwd=".", exit_code=0, output_lines=["passed"])
        assert "[OK]" in r.to_llm_summary()

    def test_to_llm_summary_failed_status(self):
        from app.agents.shell import ShellResult
        r = ShellResult(command="pytest", cwd=".", exit_code=1, output_lines=["error"])
        assert "[FAILED]" in r.to_llm_summary()

    def test_denied_result(self):
        from app.agents.shell import ShellResult
        r = ShellResult(command="x", cwd=".", exit_code=1, output_lines=["Skipped"], denied=True)
        assert not r.ok
        assert "[DENIED]" in r.to_llm_summary()


# ── render() ─────────────────────────────────────────────────────────────────

class TestRender:
    def test_render_ok_panel(self):
        from app.agents.shell import ShellResult
        r = ShellResult(command="python --version", cwd=".", exit_code=0, output_lines=["Python 3.13.0"])
        panel = shell_agent.render(r)
        assert panel is not None

    def test_render_failed_panel(self):
        from app.agents.shell import ShellResult
        r = ShellResult(command="pytest", cwd=".", exit_code=1, output_lines=["FAILED"])
        panel = shell_agent.render(r)
        assert panel is not None

    def test_render_timeout_panel(self):
        from app.agents.shell import ShellResult
        r = ShellResult(command="sleep 999", cwd=".", exit_code=1, output_lines=[], timed_out=True)
        panel = shell_agent.render(r)
        assert panel is not None
