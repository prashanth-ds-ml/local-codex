"""Tests for app/agents/filesystem.py — PermissionGuard, destructive confirm, tools."""
import pathlib
import pytest
from langchain_core.messages import AIMessage
from app.agents import filesystem
from app import memory


@pytest.fixture(autouse=True)
def reset_guard(tmp_path):
    """Reset filesystem guard to a clean state before each test."""
    filesystem.configure(workspace=str(tmp_path), confirm_fn=None)
    yield
    filesystem.configure(workspace=None, confirm_fn=None)


# ── PermissionGuard.check_path ────────────────────────────────────────────────

class TestCheckPath:
    def test_path_inside_workspace_allowed(self, tmp_path):
        guard = filesystem.PermissionGuard(workspace=str(tmp_path))
        assert guard.check_path(str(tmp_path / "foo.py")) is None

    def test_path_outside_workspace_denied(self, tmp_path):
        guard = filesystem.PermissionGuard(workspace=str(tmp_path))
        err = guard.check_path("/etc/passwd")
        assert err is not None
        assert "Permission denied" in err

    def test_no_workspace_always_allows(self, tmp_path):
        guard = filesystem.PermissionGuard(workspace=None)
        assert guard.check_path("/etc/passwd") is None

    def test_allowed_root_permits_extra_path(self, tmp_path):
        extra = tmp_path.parent / "shared"
        extra.mkdir(exist_ok=True)
        guard = filesystem.PermissionGuard(workspace=str(tmp_path), allowed_roots=[str(extra)])
        assert guard.check_path(str(extra / "notes.txt")) is None


# ── Destructive tools in _DEFAULT_TOOLS ──────────────────────────────────────

class TestDefaultTools:
    def test_all_destructive_tools_in_defaults(self):
        missing = filesystem._DESTRUCTIVE_TOOLS - filesystem._DEFAULT_TOOLS
        assert missing == set(), f"Missing from _DEFAULT_TOOLS: {missing}"


# ── confirm_fn for destructive tools ─────────────────────────────────────────

class TestDestructiveConfirm:
    def test_denied_skips_delete(self, tmp_path):
        target = tmp_path / "todelete.txt"
        target.write_text("hello")
        filesystem.configure(workspace=str(tmp_path), confirm_fn=lambda tool, args: False)
        result = filesystem.delete_file.invoke({"path": str(target)})
        assert "Skipped" in result
        assert target.exists()  # file must still be there

    def test_approved_deletes_file(self, tmp_path):
        target = tmp_path / "todelete.txt"
        target.write_text("hello")
        filesystem.configure(workspace=str(tmp_path), confirm_fn=lambda tool, args: True)
        result = filesystem.delete_file.invoke({"path": str(target)})
        assert "✓" in result
        assert not target.exists()

    def test_non_destructive_tools_skip_confirm(self, tmp_path):
        called = []
        filesystem.configure(
            workspace=str(tmp_path),
            confirm_fn=lambda tool, args: called.append(tool) or True,
        )
        # create_file is not destructive — confirm_fn should NOT be called by the guard
        # (it's called inside the agent loop, not inside the tool itself)
        p = str(tmp_path / "new.py")
        filesystem.create_file.invoke({"path": p, "content": ""})
        # confirm_fn not invoked at the tool level for non-destructive tools
        assert called == []


# ── create_file tool ──────────────────────────────────────────────────────────

class TestCreateFile:
    def test_creates_file_with_content(self, tmp_path):
        p = tmp_path / "hello.py"
        filesystem.configure(workspace=str(tmp_path))
        result = filesystem.create_file.invoke({"path": str(p), "content": "print('hi')"})
        assert "✓" in result
        assert p.read_text() == "print('hi')"

    def test_creates_parent_directories(self, tmp_path):
        p = tmp_path / "src" / "utils" / "helpers.py"
        filesystem.configure(workspace=str(tmp_path))
        result = filesystem.create_file.invoke({"path": str(p), "content": ""})
        assert "✓" in result
        assert p.exists()

    def test_unchanged_file_reports_without_rewriting(self, tmp_path):
        p = tmp_path / "hello.py"
        p.write_text("print('hi')", encoding="utf-8")
        filesystem.configure(workspace=str(tmp_path))
        result = filesystem.create_file.invoke({"path": str(p), "content": "print('hi')"})
        assert "unchanged" in result.lower()


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        if not self.responses:
            raise AssertionError("No fake LLM responses left")
        return self.responses.pop(0)


class TestWriteDiffApproval:
    def test_overwrite_prompts_and_skip_preserves_existing_file(self, tmp_path):
        target = tmp_path / "app.py"
        target.write_text("print('old')", encoding="utf-8")

        approvals = []
        filesystem.configure(
            workspace=str(tmp_path),
            confirm_fn=lambda tool, args: approvals.append((tool, args["path"])) or False,
            require_diff_approval=True,
        )

        llm = FakeLLM([
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "create_file",
                    "args": {"path": str(target), "content": "print('new')"},
                    "id": "call-1",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="done"),
        ])

        result = filesystem.run(llm, "update the file")

        assert approvals == [("create_file", str(target))]
        assert "Skipped" in result.steps[0].output
        assert target.read_text(encoding="utf-8") == "print('old')"

    def test_new_file_does_not_prompt_for_diff(self, tmp_path):
        target = tmp_path / "new.py"
        approvals = []
        filesystem.configure(
            workspace=str(tmp_path),
            confirm_fn=lambda tool, args: approvals.append(tool) or True,
            require_diff_approval=True,
        )

        llm = FakeLLM([
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "create_file",
                    "args": {"path": str(target), "content": "print('new')"},
                    "id": "call-1",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="done"),
        ])

        filesystem.run(llm, "create the file")

        assert approvals == []
        assert target.read_text(encoding="utf-8") == "print('new')"

    def test_run_records_change_set_for_overwrite(self, tmp_path):
        target = tmp_path / "app.py"
        target.write_text("print('old')\n", encoding="utf-8")

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
            AIMessage(content="done"),
        ])

        filesystem.run(llm, "update the file")

        change_set = memory.load_last_change_set(str(tmp_path))
        assert change_set is not None
        assert change_set["entries"][0]["kind"] == "create_file"
        assert change_set["entries"][0]["before"] == "print('old')\n"


# ── list_directory tool ───────────────────────────────────────────────────────

class TestListDirectory:
    def test_lists_files_and_dirs(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "subdir").mkdir()
        filesystem.configure(workspace=str(tmp_path))
        result = filesystem.list_directory.invoke({"path": str(tmp_path)})
        assert "a.py" in result
        assert "subdir" in result

    def test_empty_directory(self, tmp_path):
        filesystem.configure(workspace=str(tmp_path))
        result = filesystem.list_directory.invoke({"path": str(tmp_path)})
        assert "empty" in result.lower()

    def test_broken_entry_does_not_crash(self, tmp_path, monkeypatch):
        target = tmp_path / "ghost.txt"
        target.write_text("hello", encoding="utf-8")
        original_is_file = pathlib.Path.is_file

        def flaky_is_file(path_obj):
            if path_obj == target:
                raise FileNotFoundError("broken junction target")
            return original_is_file(path_obj)

        monkeypatch.setattr(pathlib.Path, "is_file", flaky_is_file)
        filesystem.configure(workspace=str(tmp_path))
        result = filesystem.list_directory.invoke({"path": str(tmp_path)})
        assert "ghost.txt" in result

    def test_relative_dot_uses_workspace_not_process_cwd(self, tmp_path, monkeypatch):
        (tmp_path / "inside.txt").write_text("hello", encoding="utf-8")
        monkeypatch.chdir(tmp_path.parent)
        filesystem.configure(workspace=str(tmp_path))
        result = filesystem.list_directory.invoke({"path": "."})
        assert "inside.txt" in result


class TestMoveFile:
    def test_missing_source_reports_clear_error(self, tmp_path):
        filesystem.configure(workspace=str(tmp_path))
        result = filesystem.move_file.invoke(
            {"src": str(tmp_path / "missing"), "dest": str(tmp_path / "renamed")}
        )
        assert "source does not exist" in result

    def test_existing_destination_reports_clear_error(self, tmp_path):
        src = tmp_path / "snake-agent"
        dest = tmp_path / "snake-game"
        src.mkdir()
        dest.mkdir()
        filesystem.configure(workspace=str(tmp_path))
        result = filesystem.move_file.invoke({"src": str(src), "dest": str(dest)})
        assert "destination already exists" in result

    def test_undo_last_change_set_restores_file_content(self, tmp_path):
        target = tmp_path / "app.py"
        target.write_text("print('old')\n", encoding="utf-8")

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
            AIMessage(content="done"),
        ])

        filesystem.run(llm, "update the file")
        result = filesystem.undo_last_change_set(str(tmp_path))

        assert "Undid 1 change step" in result
        assert target.read_text(encoding="utf-8") == "print('old')\n"
        assert memory.load_last_change_set(str(tmp_path)) is None


class TestFilesystemSummary:
    def test_partial_failure_does_not_claim_full_success(self, tmp_path):
        src = tmp_path / "snake-agent"
        dest = tmp_path / "snake-game"
        src.mkdir()
        filesystem.configure(workspace=str(tmp_path), confirm_fn=lambda tool, args: True)

        llm = FakeLLM([
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "move_file",
                        "args": {"src": str(src), "dest": str(dest)},
                        "id": "call-1",
                        "type": "tool_call",
                    },
                    {
                        "name": "move_file",
                        "args": {"src": str(src), "dest": str(dest)},
                        "id": "call-2",
                        "type": "tool_call",
                    },
                ],
            ),
            AIMessage(content="The snake-agent directory has been successfully moved to snake-game."),
        ])

        result = filesystem.run(llm, "rename the folder")

        assert result.ok_count == 1
        assert result.err_count == 1
        assert "Completed" in result.summary
        assert "error" in result.summary
        assert "source does not exist" in result.summary


class TestExecuteCleanup:
    def test_execute_cleanup_removes_preapproved_items(self, tmp_path):
        doomed = tmp_path / "demo-live"
        doomed.mkdir()
        filesystem.configure(workspace=str(tmp_path), confirm_fn=lambda tool, args: False)

        result = filesystem.execute_cleanup(["demo-live"])

        assert result.ok_count == 1
        assert result.err_count == 0
        assert not doomed.exists()
