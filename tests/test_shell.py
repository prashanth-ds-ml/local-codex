"""Tests for app/agents/shell.py — execute, whitelist, confirm, ShellResult."""
import pathlib
import time
import pytest
from app.agents import shell as shell_agent


@pytest.fixture(autouse=True)
def reset_config(tmp_path):
    """Reset shell config to a clean state before each test."""
    shell_agent.reset_background_tasks()
    shell_agent.configure(
        workspace=str(tmp_path),
        stream_to_console=False,
        confirm_fn=None,
    )
    yield
    shell_agent.reset_background_tasks()


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

    def test_pwd_builtin_works(self, tmp_path):
        result = shell_agent.execute("pwd", cwd=str(tmp_path))
        assert result.ok
        assert str(tmp_path) in result.output

    def test_tree_builtin_works(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hi')", encoding="utf-8")
        result = shell_agent.execute("tree", cwd=str(tmp_path))
        assert result.ok
        assert "src" in result.output

    def test_dir_builtin_works(self, tmp_path):
        (tmp_path / "app.py").write_text("print('hi')", encoding="utf-8")
        result = shell_agent.execute("dir", cwd=str(tmp_path))
        assert result.ok
        assert "app.py" in result.output

    def test_cd_builtin_updates_session_cwd(self, tmp_path):
        target = tmp_path / "src"
        target.mkdir()
        result = shell_agent.execute("cd src")
        assert result.ok
        assert result.cwd == str(target)
        assert shell_agent.get_cwd() == str(target)

    def test_cd_outside_workspace_blocked(self, tmp_path):
        result = shell_agent.execute("cd ..")
        assert not result.ok
        assert "outside the workspace" in result.output

    def test_ll_builtin_works(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")
        result = shell_agent.execute("ll")
        assert result.ok
        assert "main.py" in result.output

    def test_cat_builtin_works(self, tmp_path):
        target = tmp_path / "notes.txt"
        target.write_text("hello\nworld\n", encoding="utf-8")
        result = shell_agent.execute("cat notes.txt")
        assert result.ok
        assert "hello" in result.output
        assert "world" in result.output

    def test_session_cwd_used_for_subsequent_commands(self, tmp_path):
        nested = tmp_path / "pkg"
        nested.mkdir()
        (nested / "module.py").write_text("print('hi')", encoding="utf-8")
        shell_agent.execute("cd pkg")
        result = shell_agent.execute("ls")
        assert result.ok
        assert "module.py" in result.output

    def test_read_only_mode_blocks_subprocess_commands(self, tmp_path):
        shell_agent.configure(workspace=str(tmp_path), session_mode="read-only", stream_to_console=False, confirm_fn=None)
        result = shell_agent.execute("python --version")
        assert not result.ok
        assert "disabled in `read-only` mode" in result.output

    def test_cd_into_allowed_root_succeeds(self, tmp_path):
        extra = tmp_path.parent / "shared-shell"
        extra.mkdir(exist_ok=True)
        shell_agent.configure(
            workspace=str(tmp_path),
            allowed_roots=[str(extra)],
            stream_to_console=False,
            confirm_fn=None,
        )
        result = shell_agent.execute(f"cd {extra}")
        assert result.ok
        assert result.cwd == str(extra.resolve())


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

    def test_confirm_fn_can_receive_command_and_cwd(self, tmp_path):
        calls = []
        shell_agent.configure(
            workspace=str(tmp_path),
            confirm_fn=lambda cmd, cwd: calls.append((cmd, cwd)) or True,
            stream_to_console=False,
        )
        result = shell_agent.execute("python --version", cwd=str(tmp_path))
        assert result.ok
        assert calls == [("python --version", str(tmp_path))]

    def test_no_confirm_fn_auto_runs(self, tmp_path):
        shell_agent.configure(workspace=str(tmp_path), confirm_fn=None, stream_to_console=False)
        result = shell_agent.execute("python --version", cwd=str(tmp_path))
        assert result.ok


class TestBackgroundTasks:
    def _wait_for(self, task_id: str, *, timeout: float = 3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            task = shell_agent.get_background_task(task_id)
            if task is not None and task.status != "running":
                return task
            time.sleep(0.05)
        return shell_agent.get_background_task(task_id)

    def test_start_background_tracks_completion(self, tmp_path):
        script = tmp_path / "emit.py"
        script.write_text("print('boot')\nprint('done')\n", encoding="utf-8")
        task, error = shell_agent.start_background(
            f"python {script.name}",
            cwd=str(tmp_path),
        )

        assert error is None
        assert task is not None
        finished = self._wait_for(task.id)

        assert finished is not None
        assert finished.status == "completed"
        assert finished.exit_code == 0
        assert "boot" in finished.tail
        assert "done" in finished.tail

    def test_stop_background_task_marks_task_stopped(self, tmp_path):
        script = tmp_path / "sleepy.py"
        script.write_text("import time\nprint('start')\ntime.sleep(5)\n", encoding="utf-8")
        task, error = shell_agent.start_background(
            f"python {script.name}",
            cwd=str(tmp_path),
        )

        assert error is None
        assert task is not None
        stopped, stop_error = shell_agent.stop_background_task(task.id)

        assert stop_error is None
        assert stopped is not None
        assert stopped.status == "stopped"
        assert shell_agent.count_background_tasks(only_running=True) == 0

    def test_background_builtin_command_is_rejected(self, tmp_path):
        task, error = shell_agent.start_background("ls", cwd=str(tmp_path))

        assert task is None
        assert "Background tasks only support subprocess commands" in error


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
        assert "Run" in str(panel.title)

    def test_render_failed_panel(self):
        from app.agents.shell import ShellResult
        r = ShellResult(command="pytest", cwd=".", exit_code=1, output_lines=["FAILED"])
        panel = shell_agent.render(r)
        assert panel is not None
        assert "Run" in str(panel.title)

    def test_render_timeout_panel(self):
        from app.agents.shell import ShellResult
        r = ShellResult(command="sleep 999", cwd=".", exit_code=1, output_lines=[], timed_out=True)
        panel = shell_agent.render(r)
        assert panel is not None
