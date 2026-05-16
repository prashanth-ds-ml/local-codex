"""Tests for app/agents/explainer.py."""

from types import SimpleNamespace

from app.agents import explainer, reader as reader_agent


class TestExplainerAgent:
    def test_run_explains_file(self, tmp_path):
        reader_agent.configure(workspace=str(tmp_path))
        target = tmp_path / "main.py"
        target.write_text("def main():\n    return 1\n", encoding="utf-8")

        class FakeLLM:
            def invoke(self, messages):
                return SimpleNamespace(content="This file defines the main entrypoint.")

        response = explainer.run(FakeLLM(), str(tmp_path), "main.py")
        assert "main entrypoint" in response.summary

    def test_run_returns_reader_error_for_missing_file(self, tmp_path):
        reader_agent.configure(workspace=str(tmp_path))

        class FakeLLM:
            def invoke(self, messages):
                raise AssertionError("LLM should not be called for missing files")

        response = explainer.run(FakeLLM(), str(tmp_path), "missing.py")
        assert "File not found" in response.summary

    def test_render_returns_panel(self):
        response = explainer.ExplainResponse(path="app.py", summary="Useful summary.")
        panel = explainer.render(response)
        assert panel is not None
        assert "Explain" in str(panel.title)
