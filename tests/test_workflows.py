"""Workflow-style regression tests for CodeMitra."""

from contextlib import nullcontext
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app import memory
from app.agents import filesystem
from app.agents import planner as planner_agent
from app.agents import shell as shell_agent
from app.agents import session as session_agent
from app.agents.response import AgentResponse, ToolResult
from app.agents.shell import ShellResult
from app.main import (
    _auto_plan_request,
    _build_plan_unapproved_reply,
    _execute_approved_plan,
    _build_plan_execution_blocked_reply,
    _build_project_summary,
    _build_startup_project_brief,
    _cmd_open_url,
    _cmd_search,
    _cmd_fix,
    _confirm_shell,
    _confirm_tool,
    _classify_intent,
    _compact,
    _extract_navigation_target,
    _extract_url_from_input,
    _extract_web_search_query,
    _extract_workspace_selection_target,
    _hibernate_session,
    _is_project_summary_request,
    _is_understand_alias_request,
)


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        if not self.responses:
            raise AssertionError("No fake LLM responses left")
        return self.responses.pop(0)


class CapturingSummaryLLM:
    def __init__(self, summary: str):
        self.summary = summary
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=self.summary)


class TestBootstrapWorkflow:
    def test_actionable_project_bootstrap_request_routes_to_change(self):
        prompt = (
            "create a folder named Med_RAG and make .venv in that folder and setup obsidian "
            "and other docs that will help us start planning and brainstorming our ideas and build the project"
        )

        assert _classify_intent(prompt) == "change"

    def test_bootstrap_filesystem_flow_creates_project_scaffold(self, monkeypatch, tmp_path):
        target = tmp_path / "Med_RAG"
        filesystem.configure(workspace=str(tmp_path), confirm_fn=lambda tool, args: True)

        def fake_subprocess_run(command, cwd=None, capture_output=True, text=True):
            (target / ".venv").mkdir(parents=True, exist_ok=True)
            return SimpleNamespace(returncode=0, stderr="")

        monkeypatch.setattr(filesystem.subprocess, "run", fake_subprocess_run)

        llm = FakeLLM([
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_folder",
                        "args": {"path": str(target)},
                        "id": "call-1",
                        "type": "tool_call",
                    },
                    {
                        "name": "create_venv",
                        "args": {"project_path": str(target)},
                        "id": "call-2",
                        "type": "tool_call",
                    },
                    {
                        "name": "create_file",
                        "args": {"path": str(target / "README.md"), "content": "# Med_RAG\n"},
                        "id": "call-3",
                        "type": "tool_call",
                    },
                    {
                        "name": "create_file",
                        "args": {"path": str(target / "NOTES.md"), "content": "# Session Notes\n"},
                        "id": "call-4",
                        "type": "tool_call",
                    },
                ],
            ),
            AIMessage(content="Created the project scaffold and starter docs."),
        ])

        result = filesystem.run(llm, "bootstrap Med_RAG", console=None)

        assert target.exists()
        assert (target / ".venv").exists()
        assert (target / "README.md").read_text(encoding="utf-8") == "# Med_RAG\n"
        assert (target / "NOTES.md").read_text(encoding="utf-8") == "# Session Notes\n"
        assert result.ok_count == 4
        assert "Created the project scaffold" in result.summary


class TestStartupUnderstandingWorkflow:
    def test_startup_brief_captures_project_shape(self, tmp_path):
        (tmp_path / "README.md").write_text("# Demo\nAn offline coding assistant.\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
        (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
        (tmp_path / "tests").mkdir()

        brief = _build_startup_project_brief(str(tmp_path))

        assert brief is not None
        assert "offline coding assistant" in brief.lower()
        assert ".\\main.py" in brief
        assert "pyproject.toml" in brief
        assert "**Tests:** present" in brief

    def test_navigation_then_understand_summarizes_new_active_folder(self, tmp_path):
        target = tmp_path / "snake-game"
        target.mkdir()
        (target / "README.md").write_text("# Snake Game\nA pygame snake clone.\n", encoding="utf-8")
        (target / "requirements.txt").write_text("pygame\n", encoding="utf-8")
        (target / "main.py").write_text("print('snake')\n", encoding="utf-8")
        (target / "tests").mkdir()

        shell_agent.configure(workspace=str(tmp_path), stream_to_console=False)
        prompt = "move to snake-game and understand it"

        target_name = _extract_navigation_target(prompt) or _extract_workspace_selection_target(prompt, shell_agent.get_cwd())
        result = shell_agent.execute(f"cd {target_name}", console=None)
        summary = _build_project_summary(shell_agent.get_cwd())

        assert _is_project_summary_request(prompt)
        assert target_name == "snake-game"
        assert result.ok
        assert shell_agent.get_cwd() == str(target)
        assert "**Workspace:** `snake-game`" in summary
        assert "**Purpose:** A pygame snake clone." in summary
        assert "**Entrypoint:** `.\\main.py`" in summary
        assert "Install dependencies from `requirements.txt`." in summary
        assert "Run `.\\main.py` from PowerShell" in summary

    def test_workspace_selection_then_project_summary_uses_matching_directory(self, tmp_path):
        target = tmp_path / "snake-game"
        target.mkdir()
        (target / "README.md").write_text("# Snake Game\nSimple arcade prototype.\n", encoding="utf-8")
        (target / "app.py").write_text("print('hi')\n", encoding="utf-8")

        shell_agent.configure(workspace=str(tmp_path), stream_to_console=False)
        prompt = "work on snake game and go through the folder and tell me what you understand"

        target_name = _extract_navigation_target(prompt) or _extract_workspace_selection_target(prompt, shell_agent.get_cwd())
        result = shell_agent.execute(f"cd {target_name}", console=None)
        summary = _build_project_summary(shell_agent.get_cwd())

        assert _is_project_summary_request(prompt)
        assert target_name == "snake-game"
        assert result.ok
        assert shell_agent.get_cwd() == str(target)
        assert "**Workspace:** `snake-game`" in summary
        assert "**Purpose:** Simple arcade prototype." in summary
        assert "**Key files:**" in summary
        assert "`README.md`" in summary
        assert "`app.py`" in summary


class TestSessionRecoveryWorkflow:
    def test_compact_replaces_history_with_summary_context(self):
        llm = CapturingSummaryLLM("Summary with app.py, pytest failure, and next step.")
        messages = [
            SystemMessage(content="SYSTEM"),
            HumanMessage(content="Open app.py and inspect the failing test output."),
            AIMessage(content="I found a pytest failure in tests/test_api.py."),
            HumanMessage(content="Patch app.py and keep the undo path."),
        ]

        compacted = _compact(llm, messages, "SYSTEM")

        assert len(llm.calls) == 1
        compact_prompt = llm.calls[0][0].content
        assert "Open app.py and inspect the failing test output." in compact_prompt
        assert "I found a pytest failure in tests/test_api.py." in compact_prompt
        assert "Patch app.py and keep the undo path." in compact_prompt
        assert len(compacted) == 2
        assert isinstance(compacted[0], SystemMessage)
        assert compacted[0].content == "SYSTEM"
        assert isinstance(compacted[1], HumanMessage)
        assert "[Compacted context from previous turns]" in compacted[1].content
        assert "Summary with app.py, pytest failure, and next step." in compacted[1].content

    def test_compact_records_session_checkpoint_when_workspace_is_available(self, tmp_path):
        llm = CapturingSummaryLLM("Summary with next action preserved.")
        messages = [
            SystemMessage(content="SYSTEM"),
            HumanMessage(content="Inspect app.py."),
            AIMessage(content="Found the relevant function."),
        ]

        _compact(
            llm,
            messages,
            "SYSTEM",
            workspace=str(tmp_path),
            reason="manual",
            total_tokens=42000,
        )

        metadata = memory.load_session_metadata(str(tmp_path))
        assert metadata is not None
        assert metadata["last_compaction"]["reason"] == "manual"
        assert metadata["last_compaction"]["summary"] == "Summary with next action preserved."
        assert metadata["last_compaction"]["turns_compacted"] == 2
        assert metadata["last_compaction"]["usage_tokens_before"] == 42000

    def test_hibernate_then_resume_preserves_session_context(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.main.config.get_available_system_memory_gib", lambda: 4.0)
        monkeypatch.setattr("app.main.config.stop_local_model", lambda model: (True, f"Stopped `{model}`."))
        monkeypatch.setattr("app.main.shell_agent.get_cwd", lambda: str(tmp_path))

        session_agent.ensure_session(str(tmp_path))
        memory.write_plan(str(tmp_path), goal="Ship Med_RAG", steps=["Create project", "Verify setup"])
        memory.append_activity(str(tmp_path), "start work", "Created initial scaffold")

        messages, sess_in, sess_out, reply = _hibernate_session(
            workspace=str(tmp_path),
            model="qwen3.5:latest",
            system_prompt="SYSTEM",
            total_tokens=24000,
            auto_compact_threshold=120000,
        )

        resume = session_agent.build_resume_reply(str(tmp_path))

        assert len(messages) == 1
        assert messages[0].content == "SYSTEM"
        assert sess_in == 0
        assert sess_out == 0
        assert "Session hibernated" in reply
        assert "Ship Med_RAG" in memory.load_plan(str(tmp_path))
        assert "Session resume" in resume
        assert "Loaded" in resume

    def test_resume_after_recovery_includes_brainstorm_and_undo_state(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.main.config.get_available_system_memory_gib", lambda: 6.0)
        monkeypatch.setattr("app.main.config.stop_local_model", lambda model: (True, f"Stopped `{model}`."))
        monkeypatch.setattr("app.main.shell_agent.get_cwd", lambda: str(tmp_path))

        session_agent.ensure_session(str(tmp_path))
        memory.write_plan(str(tmp_path), goal="Ship Med_RAG", steps=["Create project"])
        memory.append_activity(str(tmp_path), "draft the ingestion flow", "Captured the first bootstrap notes.")
        memory.append_brainstorm_entry(str(tmp_path), "brainstorm ingestion options", "Use a staged document pipeline.")
        memory.record_last_change_set(
            str(tmp_path),
            {"entries": [{"kind": "create_file", "path": str(tmp_path / "README.md"), "before": None}]},
        )

        _hibernate_session(
            workspace=str(tmp_path),
            model="qwen3.5:latest",
            system_prompt="SYSTEM",
            total_tokens=18000,
            auto_compact_threshold=120000,
        )

        resume = session_agent.build_resume_reply(str(tmp_path))
        metadata = memory.load_session_metadata(str(tmp_path))

        assert metadata is not None
        assert metadata["last_hibernated_model"] == "qwen3.5:latest"
        assert "Brainstorm notes:** Saved" in resume
        assert "Undo state:** 1 step available for undo" in resume
        assert "draft the ingestion flow" in resume
        assert "/hibernate" in resume


class TestPlanLifecycleWorkflow:
    def test_auto_plan_request_writes_plan_and_pauses_in_plan_mode(self, monkeypatch, tmp_path):
        from app import main as main_mod

        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)
        monkeypatch.setattr(main_mod.console, "status", lambda *args, **kwargs: nullcontext())
        monkeypatch.setattr("app.agents.brainstorm.run", lambda llm, goal, console: "Focus on a tiny safe bootstrap.")

        llm = FakeLLM([AIMessage(content="1. Inspect the current workspace\n2. Create the bootstrap files\n3. Run pytest")])

        reply = _auto_plan_request(
            "bootstrap the project",
            str(tmp_path),
            llm,
            session_mode="plan",
        )

        saved = memory.load_plan(str(tmp_path))

        assert reply == "Created a plan for: bootstrap the project"
        assert saved is not None
        assert "Inspect the current workspace" in saved
        assert "Create the bootstrap files" in saved
        assert "- [ ] Run pytest" in saved

    def test_auto_plan_request_pauses_after_creation_when_operator_declines_start(self, monkeypatch, tmp_path):
        from app import main as main_mod

        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)
        monkeypatch.setattr(main_mod.console, "status", lambda *args, **kwargs: nullcontext())
        monkeypatch.setattr("app.agents.brainstorm.run", lambda llm, goal, console: "Use the smallest safe plan.")
        monkeypatch.setattr(main_mod, "_confirm_plan_start", lambda: False)

        llm = FakeLLM([AIMessage(content="1. Read the repo\n2. Patch the bug\n3. Run pytest")])

        reply = _auto_plan_request(
            "fix the failing tests",
            str(tmp_path),
            llm,
            session_mode="approve",
        )
        plan = planner_agent._parse_plan(str(tmp_path))

        assert reply == "Created a plan for: fix the failing tests"
        assert plan is not None
        assert len(plan.completed) == 0
        assert [step.text for step in plan.pending] == ["Read the repo", "Patch the bug", "Run pytest"]

    def test_run_plan_executes_one_next_step_and_advances_saved_plan(self, tmp_path):
        memory.write_plan(str(tmp_path), goal="Ship feature", steps=["Inspect app.py", "Run pytest"])

        llm = FakeLLM([
            AIMessage(content="direct"),
            AIMessage(content="Inspected app.py and identified the next change."),
        ])

        summary = planner_agent.run_plan(llm=llm, workspace=str(tmp_path), max_steps=1)
        plan = planner_agent._parse_plan(str(tmp_path))

        assert "Executed 1 step(s). 1 step(s) remaining." in summary
        assert "Step 1 (Inspect app.py): Inspected app.py and identified the next change." in summary
        assert plan is not None
        assert plan.steps[0].done is True
        assert plan.steps[1].done is False

    def test_plan_execution_block_reply_matches_continue_gate(self):
        assert _build_plan_execution_blocked_reply("plan") == (
            "CodeMitra is in `plan` mode, so it will not execute plan steps yet. "
            "Use `/mode approve` or `/mode auto` to act."
        )
        assert _build_plan_execution_blocked_reply("read-only", active_plan=True) == (
            "CodeMitra is in `read-only` mode, so it will not execute the active plan yet. "
            "Use `/mode approve` or `/mode auto` to continue."
        )

    def test_unapproved_plan_execution_is_blocked(self, monkeypatch, tmp_path):
        from app import main as main_mod

        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)
        memory.write_plan(str(tmp_path), goal="Ship feature", steps=["Inspect app.py"])

        reply = _execute_approved_plan(
            workspace=str(tmp_path),
            llm=FakeLLM([]),
            max_steps=1,
            session_mode="approve",
        )

        assert reply == _build_plan_unapproved_reply()

    def test_approved_plan_next_executes_one_step(self, monkeypatch, tmp_path):
        from app import main as main_mod

        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)
        memory.write_plan(str(tmp_path), goal="Ship feature", steps=["Inspect app.py", "Run pytest"])
        planner_agent.approve_plan(str(tmp_path))

        llm = FakeLLM([
            AIMessage(content="direct"),
            AIMessage(content="Inspected app.py."),
        ])

        reply = _execute_approved_plan(
            workspace=str(tmp_path),
            llm=llm,
            max_steps=1,
            session_mode="approve",
        )
        plan = planner_agent._parse_plan(str(tmp_path))

        assert "Executed 1 step(s). 1 step(s) remaining." in reply
        assert plan is not None
        assert [step.done for step in plan.steps] == [True, False]

    def test_approved_plan_run_executes_remaining_steps(self, monkeypatch, tmp_path):
        from app import main as main_mod

        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)
        memory.write_plan(str(tmp_path), goal="Ship feature", steps=["Inspect app.py", "Run pytest"])
        planner_agent.approve_plan(str(tmp_path))

        llm = FakeLLM([
            AIMessage(content="direct"),
            AIMessage(content="Inspected app.py."),
            AIMessage(content="direct"),
            AIMessage(content="Ran pytest."),
        ])

        reply = _execute_approved_plan(
            workspace=str(tmp_path),
            llm=llm,
            max_steps=None,
            session_mode="approve",
        )
        plan = planner_agent._parse_plan(str(tmp_path))
        metadata = memory.load_session_metadata(str(tmp_path))

        assert "Executed 2 step(s). 0 step(s) remaining." in reply
        assert plan is not None
        assert plan.is_done is True
        assert metadata is not None
        assert metadata["plan_execution"]["status"] == "completed"


class TestSafeEditWorkflow:
    def test_safe_edit_denied_overwrite_keeps_file_and_shows_diff_preview(self, monkeypatch, tmp_path):
        from app import main as main_mod

        target = tmp_path / "app.py"
        target.write_text("print('old')\n", encoding="utf-8")

        captured = {}

        def fake_choose(title, prompt, options, fallback_default=None):
            captured["title"] = title
            captured["prompt"] = prompt
            return "deny"

        monkeypatch.setattr(main_mod, "_choose_approval_option", fake_choose)
        monkeypatch.setattr(main_mod, "_print_approval_result", lambda *args, **kwargs: None)

        filesystem.configure(
            workspace=str(tmp_path),
            confirm_fn=_confirm_tool,
            require_diff_approval=True,
        )

        llm = FakeLLM([
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "create_file",
                    "args": {"path": str(target), "content": "print('new')\n"},
                    "id": "call-1",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="Skipped the overwrite because approval was denied."),
        ])

        result = filesystem.run(llm, "update app.py safely")

        assert captured["title"] == "File diff preview"
        assert "--- current\\app.py" in captured["prompt"]
        assert "+++ new\\app.py" in captured["prompt"]
        assert "-print('old')" in captured["prompt"]
        assert "+print('new')" in captured["prompt"]
        assert result.steps[0].output == "✗ Skipped: user declined create_file"
        assert target.read_text(encoding="utf-8") == "print('old')\n"
        assert memory.load_last_change_set(str(tmp_path)) is None

    def test_safe_edit_approved_overwrite_can_be_undone(self, monkeypatch, tmp_path):
        from app import main as main_mod

        target = tmp_path / "app.py"
        target.write_text("print('old')\n", encoding="utf-8")

        monkeypatch.setattr(main_mod, "_choose_approval_option", lambda *args, **kwargs: "approve")
        monkeypatch.setattr(main_mod, "_print_approval_result", lambda *args, **kwargs: None)

        filesystem.configure(
            workspace=str(tmp_path),
            confirm_fn=_confirm_tool,
            require_diff_approval=True,
        )

        llm = FakeLLM([
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "create_file",
                    "args": {"path": str(target), "content": "print('new')\n"},
                    "id": "call-1",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="Updated app.py and kept the change reversible."),
        ])

        result = filesystem.run(llm, "update app.py safely")
        change_set = memory.load_last_change_set(str(tmp_path))

        assert result.ok_count == 1
        assert target.read_text(encoding="utf-8") == "print('new')\n"
        assert change_set is not None
        assert change_set["entries"][0]["kind"] == "create_file"
        assert change_set["entries"][0]["before"] == "print('old')\n"

        undo_reply = filesystem.undo_last_change_set(str(tmp_path))

        assert target.read_text(encoding="utf-8") == "print('old')\n"
        assert undo_reply == "Undid 1 change step from the last change set."
        assert memory.load_last_change_set(str(tmp_path)) is None


class TestFixFailureWorkflow:
    def test_fix_failure_stops_when_command_is_not_approved(self, monkeypatch, tmp_path):
        from app import main as main_mod

        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)
        monkeypatch.setattr(main_mod.shell_agent, "render", lambda result: result.output)
        monkeypatch.setattr(
            main_mod.shell_agent,
            "execute",
            lambda command, cwd, console=None: ShellResult(
                command=command,
                cwd=str(tmp_path),
                exit_code=1,
                output_lines=["Skipped: user declined"],
                denied=True,
            ),
        )
        monkeypatch.setattr(
            main_mod.filesystem,
            "run",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("filesystem.run should not be called")),
        )

        reply = _cmd_fix("pytest", str(tmp_path), codegen_llm=SimpleNamespace())

        assert reply == "Repair stopped because the failing command was not approved."

    def test_fix_failure_succeeds_after_targeted_patch_and_rerun(self, monkeypatch, tmp_path):
        from app import main as main_mod

        shell_results = [
            ShellResult(command="pytest", cwd=str(tmp_path), exit_code=1, output_lines=["FAILED test_login"]),
            ShellResult(command="pytest", cwd=str(tmp_path), exit_code=0, output_lines=["12 passed"]),
        ]
        filesystem_calls = {"count": 0, "request": ""}

        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)
        monkeypatch.setattr(main_mod.shell_agent, "render", lambda result: result.output)
        monkeypatch.setattr(
            main_mod.shell_agent,
            "execute",
            lambda command, cwd, console=None: shell_results.pop(0),
        )

        def fake_run(llm, request, console=None):
            filesystem_calls["count"] += 1
            filesystem_calls["request"] = request
            return AgentResponse(
                request=request,
                steps=[ToolResult(tool="create_file", args={"path": "app.py"}, output="✓ Created file: app.py")],
                summary="Patched the failing branch in app.py.",
            )

        monkeypatch.setattr(main_mod.filesystem, "run", fake_run)
        monkeypatch.setattr(main_mod, "render", lambda response: response.summary)

        reply = _cmd_fix("pytest", str(tmp_path), codegen_llm=SimpleNamespace())

        assert filesystem_calls["count"] == 1
        assert "This is repair attempt 1 of 3." in filesystem_calls["request"]
        assert "FAILED test_login" in filesystem_calls["request"]
        assert reply == "Fixed after 1 repair attempt. `pytest` now passes."

    def test_fix_failure_stops_after_max_attempts_with_latest_output(self, monkeypatch, tmp_path):
        from app import main as main_mod

        shell_results = [
            ShellResult(command="pytest", cwd=str(tmp_path), exit_code=1, output_lines=["FAILED first run"]),
            ShellResult(command="pytest", cwd=str(tmp_path), exit_code=1, output_lines=["FAILED second run"]),
            ShellResult(command="pytest", cwd=str(tmp_path), exit_code=1, output_lines=["FAILED final run"]),
        ]
        filesystem_calls = {"count": 0}

        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)
        monkeypatch.setattr(main_mod.shell_agent, "render", lambda result: result.output)
        monkeypatch.setattr(
            main_mod.shell_agent,
            "execute",
            lambda command, cwd, console=None: shell_results.pop(0),
        )

        def fake_run(llm, request, console=None):
            filesystem_calls["count"] += 1
            return AgentResponse(
                request=request,
                steps=[ToolResult(tool="create_file", args={"path": "app.py"}, output="✓ Created file: app.py")],
                summary="Applied another narrow patch.",
            )

        monkeypatch.setattr(main_mod.filesystem, "run", fake_run)
        monkeypatch.setattr(main_mod, "render", lambda response: response.summary)

        reply = _cmd_fix("pytest", str(tmp_path), codegen_llm=SimpleNamespace())

        assert filesystem_calls["count"] == 2
        assert "Repair stopped after 3 attempts. `pytest` is still failing." in reply
        assert "FAILED final run" in reply


class TestResearchWorkflow:
    def test_research_search_workflow_runs_web_search_and_returns_summary(self, monkeypatch):
        from app import main as main_mod
        from app.agents import web as web_agent

        html = """
        <html><body>
        <a class="result__a" href="https://example.com/python-packaging">Python Packaging Guide</a>
        </body></html>
        """
        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)
        monkeypatch.setattr(web_agent, "_http_get", lambda url, timeout=15: html)

        llm = FakeLLM([
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "search_web",
                    "args": {"query": "python packaging"},
                    "id": "call-1",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="Top result: Python Packaging Guide — https://example.com/python-packaging"),
        ])

        query = _extract_web_search_query("search the web for python packaging")
        reply = _cmd_search(f"/search {query}", llm)

        assert query == "python packaging"
        assert "Python Packaging Guide" in reply
        assert "https://example.com/python-packaging" in reply

    def test_research_open_url_workflow_extracts_url_and_reads_page(self, monkeypatch):
        from app import main as main_mod
        from app.agents import web as web_agent

        html = """
        <html>
            <head><title>Example Docs</title></head>
            <body><p>Read the docs carefully.</p></body>
        </html>
        """
        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)
        monkeypatch.setattr(web_agent, "_http_get", lambda url, timeout=15: html)

        llm = FakeLLM([
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "fetch_url",
                    "args": {"url": "https://example.com/docs"},
                    "id": "call-1",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="Example Docs says: Read the docs carefully."),
        ])

        url = _extract_url_from_input("please read this page https://example.com/docs and summarize it")
        reply = _cmd_open_url(f"/open-url {url}", llm)

        assert url == "https://example.com/docs"
        assert "Example Docs" in reply
        assert "Read the docs carefully." in reply

    def test_research_failure_summary_cannot_claim_success_after_fetch_error(self, monkeypatch):
        from app import main as main_mod
        from app.agents import web as web_agent

        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            web_agent,
            "_http_get",
            lambda url, timeout=15: (_ for _ in ()).throw(RuntimeError("network down")),
        )

        llm = FakeLLM([
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "fetch_url",
                    "args": {"url": "https://example.com/down"},
                    "id": "call-1",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="I reviewed the page successfully and extracted the key points."),
        ])

        reply = _cmd_open_url("/open-url https://example.com/down", llm)

        assert reply == "Could not complete the web request. URL fetch failed: network down."


class TestSafetyApprovalWorkflow:
    def test_trusted_shell_command_runs_once_with_prompt_then_bypasses_menu(self, monkeypatch, tmp_path):
        from app import main as main_mod

        chooser_calls = {"count": 0}

        def fake_choose(*args, **kwargs):
            chooser_calls["count"] += 1
            return "trust"

        monkeypatch.setattr(main_mod, "_choose_approval_option", fake_choose)
        monkeypatch.setattr(main_mod, "_print_approval_result", lambda *args, **kwargs: None)

        shell_agent.configure(
            workspace=str(tmp_path),
            stream_to_console=False,
            confirm_fn=_confirm_shell,
        )

        first = shell_agent.execute("python --version", cwd=str(tmp_path))
        second = shell_agent.execute("python --version", cwd=str(tmp_path))

        assert first.ok
        assert second.ok
        assert chooser_calls["count"] == 1
        assert memory.is_shell_command_trusted(str(tmp_path), str(tmp_path), "python") is True

    def test_denied_destructive_action_keeps_file_and_reports_failure(self, monkeypatch, tmp_path):
        from app import main as main_mod

        target = tmp_path / "app.py"
        target.write_text("print('safe')\n", encoding="utf-8")

        monkeypatch.setattr(main_mod, "_choose_approval_option", lambda *args, **kwargs: "deny")
        monkeypatch.setattr(main_mod, "_print_approval_result", lambda *args, **kwargs: None)

        filesystem.configure(
            workspace=str(tmp_path),
            confirm_fn=_confirm_tool,
            require_diff_approval=True,
        )

        llm = FakeLLM([
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "delete_file",
                    "args": {"path": str(target)},
                    "id": "call-1",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="Deleted app.py."),
        ])

        result = filesystem.run(llm, "delete app.py")

        assert result.steps[0].output == "✗ Skipped: user declined delete_file"
        assert result.summary == "Could not complete the request. Skipped: user declined delete_file."
        assert target.exists()

    def test_read_only_mode_blocks_shell_but_keeps_safe_builtins_available(self, tmp_path):
        nested = tmp_path / "pkg"
        nested.mkdir()
        (nested / "module.py").write_text("print('hi')\n", encoding="utf-8")

        shell_agent.configure(
            workspace=str(tmp_path),
            session_mode="read-only",
            stream_to_console=False,
            confirm_fn=None,
        )

        blocked = shell_agent.execute("python --version", cwd=str(tmp_path))
        allowed = shell_agent.execute("ls", cwd=str(tmp_path))

        assert not blocked.ok
        assert "disabled in `read-only` mode" in blocked.output
        assert allowed.ok
        assert "pkg" in allowed.output
