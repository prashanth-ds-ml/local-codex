"""Tests for app/agents/reader.py — code reader tools."""
import pathlib
import pytest
from app.agents import reader as reader_agent


@pytest.fixture(autouse=True)
def reset_workspace(tmp_path):
    reader_agent.configure(workspace=str(tmp_path))
    yield
    reader_agent.configure(workspace=None)


# ── get_file_tree ─────────────────────────────────────────────────────────────

class TestGetFileTree:
    def test_shows_files(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1")
        (tmp_path / "utils.py").write_text("y = 2")
        result = reader_agent.get_file_tree.invoke({"path": str(tmp_path)})
        assert "main.py" in result
        assert "utils.py" in result

    def test_shows_subdirectory(self, tmp_path):
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "app.py").write_text("")
        result = reader_agent.get_file_tree.invoke({"path": str(tmp_path)})
        assert "src" in result

    def test_ignores_venv(self, tmp_path):
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "pip.py").write_text("")
        result = reader_agent.get_file_tree.invoke({"path": str(tmp_path)})
        assert ".venv" not in result

    def test_ignores_pycache(self, tmp_path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "foo.pyc").write_text("")
        result = reader_agent.get_file_tree.invoke({"path": str(tmp_path)})
        assert "__pycache__" not in result

    def test_nonexistent_path(self, tmp_path):
        result = reader_agent.get_file_tree.invoke({"path": str(tmp_path / "nope")})
        assert "✗" in result

    def test_path_outside_workspace_denied(self, tmp_path):
        result = reader_agent.get_file_tree.invoke({"path": "C:\\Windows"})
        assert "Permission denied" in result or "✗" in result


# ── read_file ─────────────────────────────────────────────────────────────────

class TestReadFile:
    def test_reads_content(self, tmp_path):
        p = tmp_path / "hello.py"
        p.write_text("print('hello')")
        result = reader_agent.read_file.invoke({"path": str(p)})
        assert "print('hello')" in result

    def test_includes_line_numbers(self, tmp_path):
        p = tmp_path / "multi.py"
        p.write_text("a = 1\nb = 2\nc = 3")
        result = reader_agent.read_file.invoke({"path": str(p)})
        assert "1 │" in result
        assert "3 │" in result

    def test_respects_line_range(self, tmp_path):
        p = tmp_path / "long.py"
        p.write_text("\n".join(f"line_{i}" for i in range(100)))
        result = reader_agent.read_file.invoke({"path": str(p), "start_line": 5, "end_line": 10})
        assert "line_4" in result   # 1-based → index 4
        assert "line_9" in result
        assert "line_0" not in result

    def test_missing_file(self, tmp_path):
        result = reader_agent.read_file.invoke({"path": str(tmp_path / "missing.py")})
        assert "✗" in result

    def test_outside_workspace_denied(self, tmp_path):
        result = reader_agent.read_file.invoke({"path": "/etc/passwd"})
        assert "Permission denied" in result or "✗" in result


# ── search_in_files ───────────────────────────────────────────────────────────

class TestSearchInFiles:
    def test_finds_pattern(self, tmp_path):
        (tmp_path / "a.py").write_text("def hello():\n    pass\n")
        (tmp_path / "b.py").write_text("x = 1\n")
        result = reader_agent.search_in_files.invoke({
            "pattern": "def hello",
            "path": str(tmp_path),
            "file_glob": "*.py",
        })
        assert "a.py" in result
        assert "def hello" in result.lower()

    def test_no_matches_returns_friendly_message(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        result = reader_agent.search_in_files.invoke({
            "pattern": "NEVEREXISTS_XYZ",
            "path": str(tmp_path),
        })
        assert "No matches" in result

    def test_case_insensitive_by_default(self, tmp_path):
        (tmp_path / "a.py").write_text("class FooBar:\n    pass\n")
        result = reader_agent.search_in_files.invoke({
            "pattern": "foobar",
            "path": str(tmp_path),
        })
        assert "FooBar" in result

    def test_invalid_regex_returns_error(self, tmp_path):
        result = reader_agent.search_in_files.invoke({
            "pattern": "[invalid((",
            "path": str(tmp_path),
        })
        assert "✗" in result


# ── find_definition ───────────────────────────────────────────────────────────

class TestFindDefinition:
    def test_finds_function(self, tmp_path):
        (tmp_path / "utils.py").write_text("def compute(x):\n    return x * 2\n")
        result = reader_agent.find_definition.invoke({
            "name": "compute",
            "path": str(tmp_path),
        })
        assert "utils.py" in result
        assert "def compute" in result

    def test_finds_class(self, tmp_path):
        (tmp_path / "models.py").write_text("class Snake:\n    pass\n")
        result = reader_agent.find_definition.invoke({
            "name": "Snake",
            "path": str(tmp_path),
        })
        assert "models.py" in result

    def test_not_found_message(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        result = reader_agent.find_definition.invoke({
            "name": "NonExistentFn",
            "path": str(tmp_path),
        })
        assert "No definition found" in result


# ── grep_symbol ───────────────────────────────────────────────────────────────

class TestGrepSymbol:
    def test_finds_usages(self, tmp_path):
        (tmp_path / "main.py").write_text("from utils import helper\nhelper()\n")
        (tmp_path / "utils.py").write_text("def helper():\n    pass\n")
        result = reader_agent.grep_symbol.invoke({
            "symbol": "helper",
            "path": str(tmp_path),
        })
        assert "main.py" in result
        assert "utils.py" in result

    def test_not_found_message(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        result = reader_agent.grep_symbol.invoke({
            "symbol": "completely_missing_xyz",
            "path": str(tmp_path),
        })
        assert "No usages" in result
