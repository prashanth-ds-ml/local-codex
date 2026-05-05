"""Tests for app/agents/filesystem.py — PermissionGuard, destructive confirm, tools."""
import pathlib
import pytest
from app.agents import filesystem


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
