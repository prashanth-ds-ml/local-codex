"""Tests for app/main.py — error handling, hint bar, completer, extract_command."""
import pathlib
import sys

import pytest
from types import SimpleNamespace
from rich.console import Console

# Ensure project root is importable
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.agents.response import AgentResponse, ToolResult
from app.agents.shell import ShellResult
from app.main import (
    _build_bottom_toolbar,
    _build_context_reply,
    _build_commit_readiness,
    _build_hibernation_reply,
    _build_tasks_reply,
    _cmd_fix,
    _cmd_brainstorm,
    _cmd_explain,
    _cmd_rename,
    _cmd_resume,
    _cmd_review,
    _cmd_symbols,
    _clear_terminal,
    _confirm_shell,
    _confirm_tool,
    _build_intent_progress_message,
    _build_model_inventory_reply,
    _build_progress_message,
    _build_permissions_reply,
    _build_project_instructions_prompt,
    _build_skills_prompt,
    _build_skills_reply,
    _build_small_talk_reply,
    _build_change_set_review_input,
    _build_change_set_diff_reply,
    _build_move_preview,
    _build_cleanup_preview,
    _build_diff_preview,
    _build_diff_reply,
    _build_fix_usage,
    _build_greeting_reply,
    _build_git_summary,
    _build_history_reply,
    _build_current_folder_reply,
    _handle_cleanup_request,
    _build_model_reply,
    _build_mode_reply,
    _build_prompt_label,
    _build_reasoning_reply,
    _build_project_summary,
    _build_startup_project_brief,
    _build_root_delete_reply,
    _build_root_rename_reply,
    _build_run_command_reply,
    _build_status_reply,
    _build_startup_status,
    _build_startup_walkthrough,
    _classify_intent,
    _confirm_plan_start,
    _detect_project_state,
    _friendly_error,
    _handle_model_command,
    _hibernate_session,
    _extract_navigation_target,
    _extract_url_from_input,
    _extract_web_search_query,
    _extract_workspace_selection_target,
    _extract_command,
    _extract_bang_command,
    _find_cleanup_candidates,
    _resolve_cleanup_root,
    _extract_fix_command,
    _parse_review_target,
    _parse_run_command,
    _is_simple_change_request,
    _is_brainstorm_request,
    _is_bang_command,
    _is_command_help_request,
    _is_cleanup_request,
    _is_current_folder_request,
    _is_delete_project_request,
    _is_project_summary_request,
    _is_small_talk,
    _is_simple_greeting,
    _is_understand_alias_request,
    _looks_like_explicit_command,
    _make_completer,
    _normalize_session_mode,
    _pick_model,
    _SLASH_COMMANDS,
    _strip_soft_prefixes,
    _should_plan_first,
    _resolve_codegen_model,
    _resolve_cloud_api_key,
)
from app import memory, skills as skills_registry


def _render_rich(renderable) -> str:
    console = Console(record=True, width=120)
    console.print(renderable)
    return console.export_text()


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

    def test_memory_pressure_hint(self):
        msg = _friendly_error(Exception("model requires more system memory (10.2 GiB) than is available (6.3 GiB)"))
        assert "/hibernate" in msg

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

    def test_detects_bang_command(self):
        assert _is_bang_command("! pwd")
        assert _extract_bang_command("! pwd") == "pwd"

    def test_extract_fix_command_uses_explicit_value(self):
        assert _extract_fix_command("/fix pytest -q") == "pytest -q"

    def test_extract_fix_command_falls_back_to_last_command(self):
        assert _extract_fix_command("/fix", last_command="python -m pytest") == "python -m pytest"


# ── _SLASH_COMMANDS ───────────────────────────────────────────────────────────

class TestSlashCommands:
    def test_all_expected_commands_present(self):
        expected = {"/init", "/run", "/plan", "/brainstorm", "/memory", "/context", "/status", "/resume", "/rename", "/mode", "/thinking", "/model", "/history", "/diff", "/review", "/explain", "/symbols", "/search", "/open-url", "/undo", "/fix", "/tasks", "/skills", "/permissions", "/hibernate", "/reset", "/help"}
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

    def test_load_config_resolves_allowed_roots(self, tmp_path):
        (tmp_path / "extra").mkdir()
        (tmp_path / "codemitra.toml").write_text('allowed_roots = ["extra"]\ndisabled_tools = ["delete_file"]\ndisabled_commands = ["python"]\n', encoding="utf-8")
        from app.config import load
        cfg = load(cwd=str(tmp_path))
        assert str((tmp_path / "extra").resolve()) in cfg["allowed_roots"]
        assert "delete_file" in cfg["disabled_tools"]
        assert "python" in cfg["disabled_commands"]

    def test_project_instruction_files_loaded_from_workspace(self, tmp_path):
        from app.config import load

        (tmp_path / "AGENTS.md").write_text("Prefer small focused patches.", encoding="utf-8")
        (tmp_path / ".codemitra").mkdir()
        (tmp_path / ".codemitra" / "instructions.md").write_text("Keep plans explicit.", encoding="utf-8")

        cfg = load(cwd=str(tmp_path))
        loaded = {item["path"]: item["content"] for item in cfg["project_instructions"]}

        assert loaded["AGENTS.md"] == "Prefer small focused patches."
        assert loaded[str(pathlib.Path(".codemitra") / "instructions.md")] == "Keep plans explicit."

    def test_project_instruction_files_ignore_paths_outside_workspace(self, tmp_path):
        from app.config import load

        outside = tmp_path.parent / "outside-instructions.md"
        outside.write_text("Do not load me.", encoding="utf-8")
        (tmp_path / "codemitra.toml").write_text(
            f'instruction_files = ["{outside.as_posix()}"]\n',
            encoding="utf-8",
        )

        cfg = load(cwd=str(tmp_path))

        assert cfg["project_instructions"] == []

    def test_build_project_instructions_prompt_formats_loaded_files(self):
        prompt = _build_project_instructions_prompt([
            {"path": "AGENTS.md", "content": "Prefer tests first."},
            {"path": ".codemitra/instructions.md", "content": "Keep output concise."},
        ])

        assert "Project Instructions" in prompt
        assert "### AGENTS.md" in prompt
        assert "Prefer tests first." in prompt
        assert "### .codemitra/instructions.md" in prompt
        assert "Keep output concise." in prompt

    def test_skill_dirs_config_defaults_to_workspace_skill_locations(self, tmp_path):
        from app.config import load

        cfg = load(cwd=str(tmp_path))

        assert cfg["skill_dirs"] == ["skills", ".codemitra/skills"]

    def test_build_skills_prompt_uses_compact_index(self):
        prompt = _build_skills_prompt([
            skills_registry.Skill(
                name="repo-analyzer",
                description="Analyze repositories before editing.",
                path="skills\\01-repo-analyzer\\SKILL.md",
            )
        ])

        assert "Available CodeMitra Skills" in prompt
        assert "repo-analyzer" in prompt
        assert "read that skill's `SKILL.md`" in prompt

    def test_build_skills_reply_lists_discovered_skills(self):
        reply = _build_skills_reply([
            skills_registry.Skill(
                name="rag-pipeline",
                description="Build or review RAG pipelines.",
                path="skills\\05-rag-pipeline\\SKILL.md",
            )
        ])

        assert "CodeMitra skills" in reply
        assert "**rag-pipeline**" in reply
        assert "05-rag-pipeline" in reply
        assert "/skills show <name>" in reply

    def test_build_skills_reply_handles_empty_registry(self):
        reply = _build_skills_reply([])
        assert "No CodeMitra skills found" in reply

    def test_build_skills_reply_shows_specific_skill_body(self, tmp_path):
        skill_dir = tmp_path / "skills" / "05-rag-pipeline"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: rag-pipeline\ndescription: Build RAG.\n---\n# RAG Pipeline\n",
            encoding="utf-8",
        )
        reply = _build_skills_reply(
            [
                skills_registry.Skill(
                    name="rag-pipeline",
                    description="Build RAG.",
                    path="skills\\05-rag-pipeline\\SKILL.md",
                )
            ],
            "/skills show rag",
            workspace=str(tmp_path),
        )

        assert "## rag-pipeline" in reply
        assert "```md" in reply
        assert "# RAG Pipeline" in reply

    def test_build_skills_reply_reports_unknown_skill(self):
        reply = _build_skills_reply([], "/skills show missing")
        assert "No matching skill found" in reply

    def test_build_skills_reply_reports_usage_for_unknown_subcommand(self):
        reply = _build_skills_reply([], "/skills delete rag")
        assert "Usage: `/skills` or `/skills show <name>`" in reply


class TestPromptLabel:
    def test_prompt_label_uses_codemitra_name(self):
        assert _build_prompt_label("qwen3.5:latest") == "\n[CodeMitra · approve] (qwen3.5)> "

    def test_prompt_label_can_show_mode(self):
        assert _build_prompt_label("qwen3.5:latest", "read-only") == "\n[CodeMitra · read-only] (qwen3.5)> "


class TestTerminalSurfaceHelpers:
    def test_context_reply_reports_usage(self):
        reply = _build_context_reply(total_tokens=60000, auto_compact_threshold=120000, num_ctx=131072)
        assert "131,072" in reply
        assert "60,000" in reply
        assert "50%" in reply
        assert "/compact" in reply

    def test_permissions_reply_includes_mode_and_roots(self, monkeypatch):
        from app import main as main_module

        monkeypatch.setattr(main_module.shell_agent, "get_cwd", lambda: r"C:\Users\prash\projects\snake-game")
        reply = _build_permissions_reply(
            {
                "workspace": r"C:\Users\prash\projects",
                "allowed_roots": [r"C:\Users\prash\projects\extra"],
                "disabled_tools": ["delete_file"],
                "disabled_commands": ["python"],
            },
            "approve",
        )
        assert "`approve`" in reply
        assert "projects\\extra" in reply
        assert "`delete_file`" in reply
        assert "`python`" in reply

    def test_bottom_toolbar_shows_core_session_state(self):
        toolbar = _build_bottom_toolbar(
            session_mode="approve",
            model="qwen3.5:latest",
            cwd=r"C:\Users\prash\projects\snake-game",
            total_tokens=24000,
            auto_compact_threshold=120000,
            current_task="Inspecting the workspace first",
            background_tasks=1,
        )
        assert "approve" in toolbar
        assert "qwen3.5" in toolbar
        assert "snake-game" in toolbar
        assert "ctx 20%" in toolbar
        assert "bg 1" in toolbar
        assert "Ctrl+G editor" in toolbar

    def test_hibernation_reply_mentions_reset_and_unload(self):
        reply = _build_hibernation_reply(
            workspace=r"C:\Users\prash\projects\local-codex",
            model="qwen3.5:latest",
            session_name="local-codex",
            shell_cwd=r"C:\Users\prash\projects\local-codex",
            total_tokens=42000,
            auto_compact_threshold=120000,
            free_ram_before=2.6,
            free_ram_after=5.1,
            unload_detail="Stopped `qwen3.5:latest`.",
        )
        assert "Session hibernated" in reply
        assert "42,000 tokens" in reply
        assert "2.6 GB" in reply
        assert "Stopped `qwen3.5:latest`." in reply

    def test_hibernate_session_resets_messages_and_persists_state(self, monkeypatch, tmp_path):
        from app import main as main_module
        from app import config
        from app.agents import session as session_module

        monkeypatch.setattr(session_module, "ensure_session", lambda workspace: {"name": "Demo"})
        monkeypatch.setattr(main_module.shell_agent, "get_cwd", lambda: str(tmp_path))
        monkeypatch.setattr(config, "get_available_system_memory_gib", lambda: 3.0)
        monkeypatch.setattr(config, "stop_local_model", lambda model: (True, f"Stopped `{model}`."))

        messages, sess_in, sess_out, reply = _hibernate_session(
            workspace=str(tmp_path),
            model="qwen3.5:latest",
            system_prompt="SYSTEM",
            total_tokens=60000,
            auto_compact_threshold=120000,
        )

        assert sess_in == 0
        assert sess_out == 0
        assert len(messages) == 1
        assert messages[0].content == "SYSTEM"
        assert "Session hibernated" in reply
        metadata = memory.load_session_metadata(str(tmp_path))
        assert metadata is not None
        assert metadata["last_hibernated_model"] == "qwen3.5:latest"
        history = memory.load_recent_activity(str(tmp_path), limit=1)
        assert history
        assert "/hibernate" in history[-1]["user"]


class TestTerminalHelpers:
    def test_clear_terminal_uses_console(self, monkeypatch):
        calls = []
        from app import main as main_module

        monkeypatch.setattr(main_module.console, "clear", lambda: calls.append("clear"))
        _clear_terminal()
        assert calls == ["clear"]


class TestProgressMessages:
    def test_build_progress_message_includes_detail(self):
        message = _build_progress_message("Inspecting the workspace first", "I’ll summarize purpose and blockers.")
        assert message.startswith("● Inspecting the workspace first")
        assert "summarize purpose and blockers" in message

    def test_intent_progress_message_for_brainstorm(self):
        message = _build_intent_progress_message(
            "brainstorm",
            "i always wanted to build a tool for time management",
        )
        assert message is not None
        assert "idea space" in message[0].lower()
        assert "practical" in (message[1] or "").lower()

    def test_intent_progress_message_for_project_summary(self):
        message = _build_intent_progress_message(
            "explain",
            "go through the folder and tell me what you understand",
        )
        assert message is not None
        assert "Inspecting the workspace first" == message[0]


class TestSessionModes:
    def test_normalize_session_mode_falls_back_to_approve(self):
        assert _normalize_session_mode("weird") == "approve"

    def test_build_mode_reply_mentions_behavior(self):
        reply = _build_mode_reply("plan")
        assert "Current mode" in reply
        assert "Inspect and plan work" in reply

    def test_build_reasoning_reply_mentions_setting(self):
        reply = _build_reasoning_reply(False)
        assert "hidden" in reply


class TestGreetingHelpers:
    def test_simple_greeting_detected(self):
        assert _is_simple_greeting("hi")
        assert _is_simple_greeting("Hello!")
        assert _is_simple_greeting("good morning")
        assert _is_simple_greeting("hi buddy")
        assert _is_simple_greeting("hello there")

    def test_non_greeting_not_detected(self):
        assert not _is_simple_greeting("help me debug this")
        assert not _is_simple_greeting("/help")

    def test_greeting_reply_mentions_codemitra_capabilities(self):
        reply = _build_greeting_reply()
        assert "CodeMitra" in reply
        assert "local coding assistant" in reply
        assert "run commands" in reply

    def test_small_talk_detected(self):
        assert _is_small_talk("how are you doing")
        assert _is_small_talk("thanks")
        assert _is_small_talk("hi buddy how are you doing")
        assert not _is_small_talk("ok lets got to projects folder")

    def test_small_talk_reply_is_stable(self):
        reply = _build_small_talk_reply("how are you doing")
        assert "ready to help" in reply.lower()

    def test_small_talk_classification_handles_blended_greeting(self):
        assert _classify_intent("hi buddy how are you doing") == "chat"

    def test_understand_alias_detected(self):
        assert _is_understand_alias_request("understand")
        assert _is_understand_alias_request("explain this")
        assert _classify_intent("tell me about this") == "explain"


class TestPlanFirstHeuristics:
    def test_large_build_request_prefers_plan(self):
        assert _should_plan_first("build a snake game using python and pygame with arrow key controls")

    def test_fix_request_prefers_plan(self):
        assert _should_plan_first("fix the login bug in the auth flow with failing tests")

    def test_simple_chat_does_not_prefer_plan(self):
        assert not _should_plan_first("hi")
        assert not _should_plan_first("what can you do?")

    def test_continue_does_not_prefer_plan(self):
        assert not _should_plan_first("continue")
        assert not _should_plan_first("next step")

    def test_slash_commands_do_not_prefer_plan(self):
        assert not _should_plan_first("/plan build an api")

    def test_polite_build_request_prefers_plan(self):
        assert _should_plan_first("i want to build a simple snake game using python")

    def test_cleanup_request_prefers_plan(self):
        assert _should_plan_first("remove any unwanted files from this project")

    def test_simple_folder_create_does_not_prefer_plan(self):
        assert not _should_plan_first("create a folder named goal_tracker in projects")

    def test_simple_file_create_does_not_prefer_plan(self):
        assert not _should_plan_first("create a file named notes.txt")


class TestSoftPrefixes:
    def test_strip_soft_prefix(self):
        assert _strip_soft_prefixes("can you build an api") == "build an api"
        assert _strip_soft_prefixes("i need you to refactor auth") == "refactor auth"


class TestCommandHelp:
    def test_detects_command_help(self):
        assert _is_command_help_request("can you give me commands to run the code")
        assert _is_command_help_request("how do i run this app")

    def test_non_command_help_ignored(self):
        assert not _is_command_help_request("run the tests now")

    def test_extract_web_search_query_detects_explicit_request(self):
        assert _extract_web_search_query("search the web for python packaging tutorials") == "python packaging tutorials"
        assert _extract_web_search_query("please look up fastapi docs") == "fastapi docs"

    def test_extract_url_from_input_detects_url(self):
        assert _extract_url_from_input("read this page https://example.com/docs?q=1.") == "https://example.com/docs?q=1"
        assert _extract_url_from_input("no link here") is None

    def test_parse_run_command_detects_background_flag(self):
        command, background = _parse_run_command("/run --background python -m http.server")
        assert background is True
        assert command == "python -m http.server"

    def test_parse_run_command_defaults_to_foreground(self):
        command, background = _parse_run_command("/run pytest -q")
        assert background is False
        assert command == "pytest -q"

    def test_build_run_command_reply_uses_powershell_activation(self, tmp_path):
        src = tmp_path / "src" / "snake_agent"
        src.mkdir(parents=True)
        (src / "cli.py").write_text("print('hi')", encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("pygame\n", encoding="utf-8")

        reply = _build_run_command_reply(str(tmp_path))

        assert ".\\.venv\\Scripts\\Activate.ps1" in reply
        assert "python -m venv .venv" in reply
        assert "python .\\src\\snake_agent\\cli.py" in reply
        assert "pip install -r .\\requirements.txt" in reply

    def test_build_run_command_reply_uses_pyproject_when_present(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
        (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")

        reply = _build_run_command_reply(str(tmp_path))

        assert "pip install -e ." in reply


class TestProjectSummary:
    def test_detects_project_summary_request(self):
        assert _is_project_summary_request("go through the folder and tell me what you understand")
        assert _is_project_summary_request("move to snake-game and understand it")

    def test_detects_current_folder_request(self):
        assert _is_current_folder_request("where are we, in which dir we are in and what folders does it contain")
        assert _classify_intent("now tell me about this folder") == "explain"

    def test_build_project_summary_mentions_entrypoint_and_blockers(self, tmp_path):
        (tmp_path / "README.md").write_text("# Snake Agent\nSimple snake game project\n", encoding="utf-8")
        src = tmp_path / "src" / "snake_agent"
        src.mkdir(parents=True)
        (src / "cli.py").write_text("print('hi')", encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("pygame\n", encoding="utf-8")

        summary = _build_project_summary(str(tmp_path))

        assert "Simple snake game project" in summary
        assert ".\\src\\snake_agent\\cli.py" in summary
        assert "No `.venv` is present yet." in summary

    def test_build_current_folder_reply_uses_active_path(self, tmp_path):
        nested = tmp_path / "snake-game"
        nested.mkdir()
        (nested / "app.py").write_text("print('hi')\n", encoding="utf-8")
        (nested / "assets").mkdir()

        reply = _build_current_folder_reply(str(nested), workspace=str(tmp_path))

        assert "Current folder" in reply
        assert str(nested) in reply
        assert "snake-game" in reply
        assert "`assets/`" in reply
        assert "`app.py`" in reply

    def test_extract_navigation_target_handles_natural_language(self):
        assert _extract_navigation_target("ok lets got to projects folder") == "projects"
        assert _extract_navigation_target("move into snake-game") == "snake-game"
        assert _extract_navigation_target("switch to src directory") == "src"
        assert _extract_navigation_target("lets navigate to projects folder so that we can work on snake-game") == "projects"
        assert _extract_navigation_target("great lets move to snake-game and understand it") == "snake-game"
        assert _extract_navigation_target("enter src") == "src"

    def test_extract_workspace_selection_target_matches_directory_name(self, tmp_path):
        (tmp_path / "snake-game").mkdir()
        (tmp_path / "goal_tracker").mkdir()

        assert _extract_workspace_selection_target("lets work with snake game", str(tmp_path)) == "snake-game"
        assert _extract_workspace_selection_target("lets work on goal tracker", str(tmp_path)) == "goal_tracker"

    def test_extract_workspace_selection_target_ignores_missing_directory(self, tmp_path):
        (tmp_path / "snake-game").mkdir()

        assert _extract_workspace_selection_target("lets work with weather app", str(tmp_path)) is None

    def test_handle_cleanup_request_targets_current_project(self, monkeypatch, tmp_path):
        project = tmp_path / "snake-game"
        project.mkdir()
        (project / "README.md").write_text("# Snake\n", encoding="utf-8")
        (project / "__pycache__").mkdir()
        monkeypatch.setattr("app.main.console.print", lambda *args, **kwargs: None)
        monkeypatch.setattr("app.main._choose_approval_option", lambda *args, **kwargs: "deny")

        reply = _handle_cleanup_request("i want simple python snake game remove others please", str(project))

        assert "Cleanup target: ." in reply or "cleanup plan" in reply.lower()


class TestIntentRouting:
    def test_classifies_run_help(self):
        assert _classify_intent("how do i run this app") == "run-help"

    def test_classifies_project_summary(self):
        assert _classify_intent("go through the folder and tell me what you understand") == "explain"
        assert _classify_intent("understand") == "explain"

    def test_classifies_cleanup_as_change(self):
        assert _classify_intent("remove any unwanted files from this project") == "change"
        assert _classify_intent("i want simple python snake game remove others please") == "change"

    def test_classifies_plan_request(self):
        assert _classify_intent("build a snake game using python and pygame") == "plan"

    def test_classifies_project_wide_rename_as_plan(self):
        assert _classify_intent("update wherever you find snake-agent to snake-game throughout the codebase") == "plan"

    def test_classifies_simple_folder_create_as_change(self):
        prompt = "create a folder named goal_tracker in projects"
        assert _is_simple_change_request(prompt)
        assert _classify_intent(prompt) == "change"

    def test_classifies_brainstorm_request(self):
        assert _is_brainstorm_request("lets work on something interesting do you have any ideas")
        assert _classify_intent("lets work on something interesting do you have any ideas") == "brainstorm"

    def test_actionable_setup_request_does_not_route_to_brainstorm(self):
        prompt = (
            "create a folder named Med_RAG and make .venv in that folder and setup obsidian "
            "and other docs that will help us start planning and brainstorming our ideas and build the project"
        )
        assert not _is_brainstorm_request(prompt)
        assert _classify_intent(prompt) == "change"

    def test_classifies_aspirational_product_prompt_as_brainstorm(self):
        prompt = (
            "i always wanted to build a tool that will help track my goals at work and personal "
            "which is connected to pomodora to improve my time management"
        )
        assert _is_brainstorm_request(prompt)
        assert _classify_intent(prompt) == "brainstorm"

    def test_detects_explicit_command(self):
        assert _looks_like_explicit_command("python main.py")
        assert _looks_like_explicit_command("please run `pytest -q`")
        assert not _looks_like_explicit_command("run the app for me")


class TestProjectDetection:
    def test_detect_project_state(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
        (tmp_path / ".venv").mkdir()
        (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")

        state = _detect_project_state(str(tmp_path), has_memory=True, has_plan=False)

        assert state["entrypoint"] == ".\\main.py"
        assert state["venv_exists"] is True
        assert state["dependency_source"] == "pyproject.toml"
        assert state["has_memory"] is True

    def test_detect_project_state_finds_top_level_cli_entrypoint(self, tmp_path):
        package_dir = tmp_path / "snake-game"
        package_dir.mkdir()
        (package_dir / "cli.py").write_text("print('hi')", encoding="utf-8")

        state = _detect_project_state(str(tmp_path))

        assert state["entrypoint"] == ".\\snake-game\\cli.py"

    def test_build_startup_status_panel(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")
        panel = _build_startup_status(str(tmp_path), has_memory=False, has_plan=True)
        assert panel is not None
        assert "Session Snapshot" in str(panel.title)
        rendered = _render_rich(panel)
        assert "Context" in rendered
        assert "131,072 max" in rendered
        assert "compact at 120,000" in rendered
        assert "Session:" in rendered
        assert "Next:" in rendered

    def test_build_startup_project_brief_summarizes_workspace(self, tmp_path):
        (tmp_path / "README.md").write_text("# Demo\nA sample coding assistant.\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
        (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
        (tmp_path / "tests").mkdir()

        brief = _build_startup_project_brief(str(tmp_path))

        assert brief is not None
        assert "Auto-detected project brief" in brief
        assert "A sample coding assistant" in brief
        assert "pyproject.toml" in brief
        assert ".\\main.py" in brief
        assert "**Tests:** present" in brief

    def test_build_startup_project_brief_returns_none_for_empty_workspace(self, tmp_path):
        brief = _build_startup_project_brief(str(tmp_path))
        assert brief is None

    def test_build_startup_walkthrough_panel(self):
        panel = _build_startup_walkthrough()
        rendered = _render_rich(panel)
        assert "Start Here" in rendered
        assert "what do you understand about this project?" in rendered
        assert "/plan build a goal tracker app" in rendered
        assert "/search" in rendered
        assert "/review" in rendered


class TestOperatorReplies:
    def test_build_model_reply_reports_local_only_mode(self):
        reply = _build_model_reply("qwen3.5:latest", "kimi-k2.5:cloud", cloud_codegen_enabled=False)
        assert "qwen3.5:latest" in reply
        assert "Local-only" in reply
        assert "/model list" in reply

    def test_build_model_inventory_reply_marks_active_model_and_hidden_models(self):
        reply = _build_model_inventory_reply(
            "qwen3.5:latest",
            "kimi-k2.5:cloud",
            cloud_codegen_enabled=False,
            model_inventory=[
                SimpleNamespace(name="qwen3.5:latest", size_text="6.6 GB", recommended=True),
                SimpleNamespace(name="gpt-oss:20b", size_text="13 GB", recommended=False),
            ],
        )
        assert "Recommended on this hardware" in reply
        assert "qwen3.5:latest" in reply
        assert "(active)" in reply
        assert "Hidden because they exceed the recommended budget" in reply
        assert "gpt-oss:20b" in reply

    def test_handle_model_command_lists_models(self, monkeypatch):
        from app import config

        monkeypatch.setattr(
            config,
            "get_local_model_inventory",
            lambda: [
                SimpleNamespace(name="qwen3.5:latest", size_text="6.6 GB", recommended=True),
                SimpleNamespace(name="gpt-oss:20b", size_text="13 GB", recommended=False),
            ],
        )
        monkeypatch.setattr(config, "get_total_system_memory_gib", lambda: 23.6)
        monkeypatch.setattr(config, "get_recommended_model_budget_gib", lambda: 11.8)
        reply = _handle_model_command(
            "/model list",
            "qwen3.5:latest",
            "kimi-k2.5:cloud",
            cloud_codegen_enabled=False,
        )
        assert "Local models" in reply
        assert "Detected system RAM" in reply
        assert "gpt-oss:20b" in reply

    def test_handle_model_command_removes_model(self, monkeypatch):
        from app import config

        monkeypatch.setattr(config, "remove_local_model", lambda name: (True, f"Removed `{name}`."))
        monkeypatch.setattr(
            config,
            "get_local_model_inventory",
            lambda: [SimpleNamespace(name="qwen3.5:latest", size_text="6.6 GB", recommended=True)],
        )
        monkeypatch.setattr(config, "get_total_system_memory_gib", lambda: 23.6)
        monkeypatch.setattr(config, "get_recommended_model_budget_gib", lambda: 11.8)
        reply = _handle_model_command(
            "/model remove gemma4:latest",
            "qwen3.5:latest",
            "kimi-k2.5:cloud",
            cloud_codegen_enabled=False,
        )
        assert "Removed `gemma4:latest`." in reply
        assert "Local models" in reply

    def test_handle_model_command_blocks_active_model_removal(self):
        reply = _handle_model_command(
            "/model remove qwen3.5:latest",
            "qwen3.5:latest",
            "kimi-k2.5:cloud",
            cloud_codegen_enabled=False,
        )
        assert "Cannot remove the active chat model" in reply

    def test_build_tasks_reply_for_empty_background_queue(self):
        from app.agents import shell as shell_agent

        shell_agent.reset_background_tasks()
        reply = _build_tasks_reply("/tasks")

        assert "No background tasks yet" in reply
        assert "/run --background <command>" in reply

    def test_build_tasks_reply_lists_running_task(self, monkeypatch):
        from app import main as main_mod

        task = SimpleNamespace(
            id="bg-1",
            command="python -m http.server",
            cwd=r"C:\Users\prash\projects\demo",
            status="running",
            exit_code=None,
        )
        monkeypatch.setattr(main_mod.shell_agent, "list_background_tasks", lambda: [task])

        reply = _build_tasks_reply("/tasks")

        assert "Background tasks" in reply
        assert "bg-1" in reply
        assert "python -m http.server" in reply

    def test_build_tasks_reply_stop_reports_existing_completed_task(self, monkeypatch):
        from app import main as main_mod

        task = SimpleNamespace(
            id="bg-1",
            command="python worker.py",
            cwd=r"C:\Users\prash\projects\demo",
            status="completed",
        )
        monkeypatch.setattr(main_mod.shell_agent, "get_background_task", lambda task_id: task if task_id == "bg-1" else None)
        monkeypatch.setattr(main_mod.shell_agent, "stop_background_task", lambda task_id: pytest.fail("stop should not be called for completed tasks"))

        reply = _build_tasks_reply("/tasks stop bg-1")

        assert "already `completed`" in reply

    def test_pick_model_uses_only_recommended_models(self, monkeypatch):
        from app import config
        from app import main as main_module

        monkeypatch.setattr(
            config,
            "get_local_model_inventory",
            lambda: [
                SimpleNamespace(name="gpt-oss:20b", size_text="13 GB", recommended=False),
                SimpleNamespace(name="qwen2.5-coder:7b", size_text="4.7 GB", recommended=True),
                SimpleNamespace(name="qwen3.5:4b", size_text="3.4 GB", recommended=True),
            ],
        )
        monkeypatch.setattr(config, "get_total_system_memory_gib", lambda: 23.6)
        monkeypatch.setattr(config, "get_recommended_model_budget_gib", lambda: 11.8)
        monkeypatch.setattr(main_module.console, "input", lambda _: "1")
        monkeypatch.setattr(main_module.console, "print", lambda *args, **kwargs: None)

        chosen = _pick_model({})
        assert chosen == "qwen2.5-coder:7b"

    def test_build_status_reply_mentions_plan_and_usage(self, tmp_path):
        from app.agents import shell as shell_agent
        shell_agent.configure(workspace=str(tmp_path), stream_to_console=False, confirm_fn=None)
        memory.write_plan(str(tmp_path), goal="Ship it", steps=["Do thing", "Verify"])
        reply = _build_status_reply(
            str(tmp_path),
            "qwen3.5:latest",
            "kimi-k2.5:cloud",
            cloud_codegen_enabled=False,
            session_mode="approve",
            show_reasoning=False,
            total_tokens=400,
            auto_compact_threshold=120000,
            num_ctx=131072,
        )
        assert "Session status" in reply
        assert "Session:" in reply
        assert "0/2 done" in reply
        assert "400 tokens" in reply
        assert str(tmp_path) in reply
        assert "approve" in reply
        assert "131,072" in reply
        assert "120,000" in reply
        assert "Git:" in reply
        assert "Commit readiness:" in reply

    def test_build_git_summary_reports_not_repo(self, monkeypatch, tmp_path):
        from app import main as main_mod

        monkeypatch.setattr(main_mod, "_is_git_repo", lambda workspace: False)

        assert _build_git_summary(str(tmp_path)) == "Not a git repository"

    def test_build_git_summary_reports_branch_upstream_and_counts(self, monkeypatch, tmp_path):
        from app import main as main_mod

        def fake_output(workspace, args):
            joined = " ".join(args)
            if joined == "rev-parse --abbrev-ref HEAD":
                return "feature/git-status"
            if joined == "rev-parse --abbrev-ref --symbolic-full-name @{u}":
                return "origin/feature/git-status"
            if joined == "status --short":
                return "M  app.py\n M tests/test_app.py\n?? notes.md"
            return ""

        monkeypatch.setattr(main_mod, "_is_git_repo", lambda workspace: True)
        monkeypatch.setattr(main_mod, "_git_output", fake_output)

        summary = _build_git_summary(str(tmp_path))

        assert "`feature/git-status`" in summary
        assert "upstream `origin/feature/git-status`" in summary
        assert "1 staged" in summary
        assert "1 unstaged" in summary
        assert "1 untracked" in summary

    def test_build_commit_readiness_reports_clean_tree(self, monkeypatch, tmp_path):
        from app import main as main_mod

        monkeypatch.setattr(main_mod, "_is_git_repo", lambda workspace: True)
        monkeypatch.setattr(main_mod, "_git_output", lambda workspace, args: "")

        assert _build_commit_readiness(str(tmp_path)) == "Clean working tree; nothing to commit"

    def test_build_commit_readiness_reports_no_staged_changes(self, monkeypatch, tmp_path):
        from app import main as main_mod

        monkeypatch.setattr(main_mod, "_is_git_repo", lambda workspace: True)
        monkeypatch.setattr(main_mod, "_git_output", lambda workspace, args: " M app.py\n?? notes.md")

        assert _build_commit_readiness(str(tmp_path)) == "Not ready: no staged changes (2 unstaged/untracked)"

    def test_build_commit_readiness_reports_ready_staged_changes(self, monkeypatch, tmp_path):
        from app import main as main_mod

        monkeypatch.setattr(main_mod, "_is_git_repo", lambda workspace: True)
        monkeypatch.setattr(main_mod, "_git_output", lambda workspace, args: "M  app.py\nA  tests/test_app.py")

        assert _build_commit_readiness(str(tmp_path)) == "Ready: 2 staged changes"

    def test_build_commit_readiness_reports_partial_commit(self, monkeypatch, tmp_path):
        from app import main as main_mod

        monkeypatch.setattr(main_mod, "_is_git_repo", lambda workspace: True)
        monkeypatch.setattr(main_mod, "_git_output", lambda workspace, args: "M  app.py\n M app.py\n?? notes.md")

        assert _build_commit_readiness(str(tmp_path)) == "Partially ready: 1 staged, 1 unstaged and 1 untracked outside the commit"

    def test_build_history_reply_reads_recent_activity(self, tmp_path):
        memory.append_activity(str(tmp_path), "first ask", "first reply")
        memory.append_activity(str(tmp_path), "second ask", "second reply")
        reply = _build_history_reply(str(tmp_path), limit=2)
        assert "Recent history" in reply
        assert "second ask" in reply
        assert "second reply" in reply

    def test_build_change_set_diff_reply_uses_recorded_change(self, tmp_path):
        memory.record_last_change_set(
            str(tmp_path),
            {
                "entries": [
                    {
                        "kind": "create_file",
                        "path": str(tmp_path / "app.py"),
                        "existed": True,
                        "before": "print('old')\n",
                        "after": "print('new')\n",
                    }
                ]
            },
        )
        reply = _build_change_set_diff_reply(str(tmp_path))
        assert "Last CodeMitra change set" in reply
        assert "print('old')" in reply
        assert "print('new')" in reply

    def test_build_change_set_review_input_uses_recorded_change(self, tmp_path):
        memory.record_last_change_set(
            str(tmp_path),
            {
                "entries": [
                    {
                        "kind": "create_file",
                        "path": str(tmp_path / "app.py"),
                        "existed": True,
                        "before": "print('old')\n",
                        "after": "print('new')\n",
                    }
                ]
            },
        )
        review_input = _build_change_set_review_input(str(tmp_path))
        assert review_input is not None
        assert "Last CodeMitra change set" in review_input
        assert "print('old')" in review_input
        assert "print('new')" in review_input

    def test_build_diff_reply_without_git_or_changes_reports_empty(self, tmp_path):
        reply = _build_diff_reply(str(tmp_path))
        assert "No diff is available yet." in reply

    def test_cmd_review_without_changes_reports_empty(self, tmp_path):
        reply = _cmd_review(str(tmp_path), SimpleNamespace())
        assert "Nothing to review yet" in reply

    def test_cmd_review_uses_change_set_when_available(self, monkeypatch, tmp_path):
        from app import main as main_mod

        memory.record_last_change_set(
            str(tmp_path),
            {
                "entries": [
                    {
                        "kind": "create_file",
                        "path": str(tmp_path / "app.py"),
                        "existed": True,
                        "before": "print('old')\n",
                        "after": "print('new')\n",
                    }
                ]
            },
        )

        monkeypatch.setattr(main_mod, "_is_git_repo", lambda workspace: False)
        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)

        class FakeReviewLLM:
            def invoke(self, messages):
                return SimpleNamespace(content="Potential issue in app.py.")

        reply = _cmd_review(str(tmp_path), FakeReviewLLM())
        assert "Potential issue" in reply

    def test_parse_review_target_defaults_to_working(self):
        assert _parse_review_target("/review") == "working"

    def test_parse_review_target_supports_staged(self):
        assert _parse_review_target("/review staged") == "staged"

    def test_cmd_review_supports_staged_git_review(self, monkeypatch, tmp_path):
        from app import main as main_mod

        monkeypatch.setattr(main_mod, "_is_git_repo", lambda workspace: True)
        monkeypatch.setattr(
            main_mod,
            "_build_git_review_input",
            lambda workspace, staged: ("staged git diff", "Git status:\nM app.py\n\nDiff:\n+change") if staged else None,
        )
        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)

        class FakeReviewLLM:
            def invoke(self, messages):
                return SimpleNamespace(content="Review found no blocking issues.")

        reply = _cmd_review(str(tmp_path), FakeReviewLLM(), target="staged")
        assert "no blocking issues" in reply.lower()

    def test_cmd_resume_summarizes_session(self, monkeypatch, tmp_path):
        from app import main as main_mod

        memory.append_activity(str(tmp_path), "first ask", "first reply")
        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)

        reply = _cmd_resume(str(tmp_path))
        assert "Session resume" in reply
        assert str(tmp_path) in reply
        assert "first ask" in reply

    def test_cmd_rename_sets_session_name(self, tmp_path):
        reply = _cmd_rename("/rename Deep Work", str(tmp_path))
        assert "Deep Work" in reply
        metadata = memory.load_session_metadata(str(tmp_path))
        assert metadata is not None
        assert metadata["name"] == "Deep Work"

    def test_cmd_rename_without_name_shows_current_name(self, tmp_path):
        memory.ensure_session_metadata(str(tmp_path), default_name="demo")
        reply = _cmd_rename("/rename", str(tmp_path))
        assert "Current session name" in reply
        assert "demo" in reply

    def test_cmd_explain_requires_file(self, tmp_path):
        reply = _cmd_explain("/explain", str(tmp_path), SimpleNamespace())
        assert "Usage:" in reply

    def test_cmd_explain_reads_file_and_returns_summary(self, monkeypatch, tmp_path):
        from app import main as main_mod

        target = tmp_path / "app.py"
        target.write_text("def run():\n    return 1\n", encoding="utf-8")
        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)

        class FakeExplainLLM:
            def invoke(self, messages):
                return SimpleNamespace(content="This file exposes a small run entrypoint.")

        reply = _cmd_explain(f"/explain {target.name}", str(tmp_path), FakeExplainLLM())
        assert "run entrypoint" in reply

    def test_cmd_symbols_requires_name(self, tmp_path):
        reply = _cmd_symbols("/symbols", str(tmp_path))
        assert "Usage:" in reply

    def test_cmd_symbols_returns_definition_and_usage_summary(self, monkeypatch, tmp_path):
        from app import main as main_mod

        (tmp_path / "main.py").write_text("from utils import helper\nhelper()\n", encoding="utf-8")
        (tmp_path / "utils.py").write_text("def helper():\n    pass\n", encoding="utf-8")
        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)

        reply = _cmd_symbols("/symbols helper", str(tmp_path))
        assert "Symbol: `helper`" in reply
        assert "Definitions" in reply
        assert "Usages" in reply

    def test_build_fix_usage_mentions_last_command(self):
        reply = _build_fix_usage("pytest -q")
        assert "/fix pytest -q" in reply

    def test_cmd_fix_succeeds_after_retry(self, monkeypatch, tmp_path):
        from app import main as main_mod

        shell_results = [
            ShellResult(command="pytest", cwd=str(tmp_path), exit_code=1, output_lines=["FAILED test_example"]),
            ShellResult(command="pytest", cwd=str(tmp_path), exit_code=0, output_lines=["2 passed"]),
        ]
        calls = {"filesystem": 0}

        monkeypatch.setattr(main_mod.console, "print", lambda *args, **kwargs: None)
        monkeypatch.setattr(main_mod.shell_agent, "render", lambda result: result.output)
        monkeypatch.setattr(
            main_mod.shell_agent,
            "execute",
            lambda command, cwd, console=None: shell_results.pop(0),
        )

        def fake_run(llm, request, console=None):
            calls["filesystem"] += 1
            return AgentResponse(
                request=request,
                steps=[ToolResult(tool="create_file", args={"path": "app.py"}, output="✓ Created file: app.py")],
                summary="patched",
            )

        monkeypatch.setattr(main_mod.filesystem, "run", fake_run)
        monkeypatch.setattr(main_mod, "render", lambda response: response.summary)

        reply = _cmd_fix("pytest", str(tmp_path), codegen_llm=SimpleNamespace())

        assert "now passes" in reply
        assert calls["filesystem"] == 1

    def test_cmd_fix_stops_when_no_code_changes_applied(self, monkeypatch, tmp_path):
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
                output_lines=["Traceback", "AssertionError"],
            ),
        )
        monkeypatch.setattr(
            main_mod.filesystem,
            "run",
            lambda llm, request, console=None: AgentResponse(
                request=request,
                steps=[ToolResult(tool="read_file", args={"path": "app.py"}, output="print('hi')")],
                summary="inspected only",
            ),
        )
        monkeypatch.setattr(main_mod, "render", lambda response: response.summary)

        reply = _cmd_fix("pytest", str(tmp_path), codegen_llm=SimpleNamespace())

        assert "no code changes were applied" in reply.lower()

    def test_cmd_brainstorm_saves_note(self, tmp_path):
        class FakeLLM:
            def invoke(self, messages):
                return SimpleNamespace(content="Here are three strong directions.")

        reply = _cmd_brainstorm("/brainstorm build something fun", str(tmp_path), FakeLLM())

        assert "Saved in brainstorm notes" in reply
        saved = memory.load_brainstorm(str(tmp_path))
        assert saved is not None
        assert "build something fun" in saved
        assert "three strong directions" in saved


class TestCleanupFlow:
    def test_detects_cleanup_request(self):
        assert _is_cleanup_request("remove any unwanted files from this project")

    def test_find_cleanup_candidates(self, tmp_path):
        (tmp_path / "demo-live").mkdir()
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "src").mkdir()

        candidates = _find_cleanup_candidates(str(tmp_path))

        assert "demo-live" in candidates
        assert "__pycache__" in candidates
        assert "src" not in candidates

    def test_cleanup_preview_lists_candidates(self):
        preview = _build_cleanup_preview("C:\\tmp", ["demo-live", "__pycache__"])
        assert "demo-live" in preview
        assert "__pycache__" in preview

    def test_resolve_cleanup_root_prefers_named_folder(self, tmp_path):
        (tmp_path / "snake-game").mkdir()
        (tmp_path / "local-codex").mkdir()

        resolved = _resolve_cleanup_root(str(tmp_path), "remove unwanted files from snake-game folder")

        assert resolved == tmp_path / "snake-game"

    def test_resolve_cleanup_root_returns_none_for_umbrella_workspace(self, tmp_path):
        (tmp_path / "snake-game").mkdir()
        (tmp_path / "local-codex").mkdir()

        resolved = _resolve_cleanup_root(str(tmp_path), "remove unwanted files")

        assert resolved is None

    def test_detects_delete_project_request(self):
        assert _is_delete_project_request("can you delete this project so i can start fresh again")

    def test_build_root_delete_reply(self, tmp_path):
        reply = _build_root_delete_reply(str(tmp_path / "snake-agent"))
        assert "cannot delete the current project root from within itself" in reply
        assert "Remove-Item" in reply


class TestRenamePreview:
    def test_build_move_preview_mentions_scope(self, tmp_path):
        src = tmp_path / "snake-agent"
        src.mkdir()
        preview = _build_move_preview(str(src), str(tmp_path / "snake-game"))
        assert "Source type: folder" in preview
        assert "Imports and package names stay unchanged" in preview

    def test_build_move_preview_reports_missing_source(self, tmp_path):
        preview = _build_move_preview(str(tmp_path / "missing"), str(tmp_path / "snake-game"))
        assert "Source path: not found" in preview

    def test_build_root_rename_reply_for_current_workspace(self, tmp_path):
        reply = _build_root_rename_reply("can you change the snake-agent name to snake-game", str(tmp_path / "snake-agent"))
        assert reply is not None
        assert "cannot rename the root folder from within itself" in reply
        assert "Rename-Item" in reply


class TestPlanStartConfirm:
    def test_confirm_plan_start_defaults_yes(self, monkeypatch):
        from app import main as main_mod

        monkeypatch.setattr(main_mod, "_choose_approval_option", lambda *args, **kwargs: "approve")
        assert _confirm_plan_start() is True

    def test_confirm_plan_start_accepts_no(self, monkeypatch):
        from app import main as main_mod

        monkeypatch.setattr(main_mod, "_choose_approval_option", lambda *args, **kwargs: "deny")
        assert _confirm_plan_start() is False


class TestApprovalMenus:
    def test_confirm_shell_can_trust_command_in_directory(self, monkeypatch, tmp_path):
        from app import main as main_mod
        from app.agents import shell as shell_agent

        shell_agent.configure(workspace=str(tmp_path), stream_to_console=False, confirm_fn=None)
        monkeypatch.setattr(main_mod, "_choose_approval_option", lambda *args, **kwargs: "trust")

        assert _confirm_shell("pytest tests\\test_main_ux.py", str(tmp_path)) is True
        assert memory.is_shell_command_trusted(str(tmp_path), str(tmp_path), "pytest") is True

    def test_confirm_shell_skips_menu_for_trusted_command(self, monkeypatch, tmp_path):
        from app import main as main_mod
        from app.agents import shell as shell_agent

        shell_agent.configure(workspace=str(tmp_path), stream_to_console=False, confirm_fn=None)
        memory.trust_shell_command(str(tmp_path), str(tmp_path), "pytest")
        monkeypatch.setattr(
            main_mod,
            "_choose_approval_option",
            lambda *args, **kwargs: pytest.fail("trusted command should bypass chooser"),
        )

        assert _confirm_shell("pytest -q", str(tmp_path)) is True

    def test_confirm_tool_uses_chooser_result(self, monkeypatch, tmp_path):
        from app import main as main_mod

        target = tmp_path / "app.py"
        target.write_text("print('old')\n", encoding="utf-8")
        monkeypatch.setattr(main_mod, "_choose_approval_option", lambda *args, **kwargs: "approve")

        assert _confirm_tool("create_file", {"path": str(target), "content": "print('new')\n"}) is True


class TestDiffPreview:
    def test_build_diff_preview_shows_before_and_after_lines(self, tmp_path):
        target = tmp_path / "app.py"
        target.write_text("print('old')\n", encoding="utf-8")

        preview = _build_diff_preview(str(target), "print('new')\n")

        assert "--- current\\app.py" in preview
        assert "+++ new\\app.py" in preview
        assert "-print('old')" in preview
        assert "+print('new')" in preview

    def test_build_diff_preview_truncates_long_output(self, tmp_path):
        target = tmp_path / "big.py"
        target.write_text("\n".join(f"old_{i}" for i in range(80)), encoding="utf-8")

        preview = _build_diff_preview(
            str(target),
            "\n".join(f"new_{i}" for i in range(80)),
            max_lines=12,
        )

        assert "more lines omitted" in preview
