"""Tests for app/agents/codeintel.py."""

from app.agents import codeintel, reader as reader_agent


class TestCodeIntelAgent:
    def test_run_returns_definition_and_usage_sections(self, tmp_path):
        reader_agent.configure(workspace=str(tmp_path))
        (tmp_path / "main.py").write_text("from utils import helper\nhelper()\n", encoding="utf-8")
        (tmp_path / "utils.py").write_text("def helper():\n    pass\n", encoding="utf-8")

        response = codeintel.run(str(tmp_path), "helper")
        assert "Definitions" in response.summary
        assert "Usages" in response.summary
        assert "helper" in response.summary

    def test_render_returns_panel(self):
        response = codeintel.CodeIntelResponse(symbol="helper", summary="summary")
        panel = codeintel.render(response)
        assert panel is not None
        assert "Code Intelligence" in str(panel.title)
