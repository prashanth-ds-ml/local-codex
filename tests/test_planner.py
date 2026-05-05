"""Tests for app/agents/planner.py — plan creation, parsing, rendering, routing."""
import pathlib
import re
import pytest
from app.agents import planner as planner_agent
from app import memory


# ── Plan parsing ──────────────────────────────────────────────────────────────

class TestParsePlan:
    def test_parses_steps(self, tmp_path):
        memory.write_plan(str(tmp_path), goal="Build a snake game", steps=[
            "Create project folder",
            "Create snake.py",
            "Run tests",
        ])
        plan = planner_agent._parse_plan(str(tmp_path))
        assert plan is not None
        assert plan.goal == "Build a snake game"
        assert len(plan.steps) == 3
        assert plan.steps[0].text == "Create project folder"

    def test_marks_done_steps(self, tmp_path):
        memory.write_plan(str(tmp_path), goal="Test", steps=["Step A", "Step B", "Step C"])
        memory.mark_step_done(str(tmp_path), 0)
        plan = planner_agent._parse_plan(str(tmp_path))
        assert plan.steps[0].done is True
        assert plan.steps[1].done is False

    def test_no_plan_returns_none(self, tmp_path):
        plan = planner_agent._parse_plan(str(tmp_path))
        assert plan is None

    def test_pending_and_completed_properties(self, tmp_path):
        memory.write_plan(str(tmp_path), goal="X", steps=["A", "B", "C"])
        memory.mark_step_done(str(tmp_path), 0)
        plan = planner_agent._parse_plan(str(tmp_path))
        assert len(plan.pending) == 2
        assert len(plan.completed) == 1

    def test_is_done_when_all_checked(self, tmp_path):
        memory.write_plan(str(tmp_path), goal="X", steps=["A", "B"])
        memory.mark_step_done(str(tmp_path), 0)  # marks A; B is now unchecked[0]
        memory.mark_step_done(str(tmp_path), 0)  # marks B
        plan = planner_agent._parse_plan(str(tmp_path))
        assert plan.is_done is True


# ── Render ────────────────────────────────────────────────────────────────────

class TestRender:
    def test_renders_panel(self, tmp_path):
        memory.write_plan(str(tmp_path), goal="Build something", steps=["Step 1", "Step 2"])
        plan = planner_agent._parse_plan(str(tmp_path))
        panel = planner_agent.render(plan)
        assert panel is not None

    def test_completed_plan_green_border(self, tmp_path):
        memory.write_plan(str(tmp_path), goal="Done", steps=["Only step"])
        memory.mark_step_done(str(tmp_path), 0)
        plan = planner_agent._parse_plan(str(tmp_path))
        panel = planner_agent.render(plan)
        assert panel.border_style == "green"

    def test_incomplete_plan_yellow_border(self, tmp_path):
        memory.write_plan(str(tmp_path), goal="In progress", steps=["A", "B"])
        plan = planner_agent._parse_plan(str(tmp_path))
        panel = planner_agent.render(plan)
        assert panel.border_style == "yellow"


# ── Step model ────────────────────────────────────────────────────────────────

class TestStep:
    def test_step_defaults_not_done(self):
        step = planner_agent.Step(index=0, text="Do something")
        assert step.done is False

    def test_step_can_be_marked_done(self):
        step = planner_agent.Step(index=0, text="Do something", done=True)
        assert step.done is True


# ── run_plan no-plan guard ────────────────────────────────────────────────────

class TestRunPlanGuard:
    def test_no_plan_returns_message(self, tmp_path):
        result = planner_agent.run_plan(llm=None, workspace=str(tmp_path))
        assert "No active plan" in result

    def test_all_done_returns_message(self, tmp_path):
        memory.write_plan(str(tmp_path), goal="X", steps=["A"])
        memory.mark_step_done(str(tmp_path), 0)
        result = planner_agent.run_plan(llm=None, workspace=str(tmp_path))
        assert "already completed" in result


# ── Config: auto_compact_threshold ───────────────────────────────────────────

class TestAutoCompactConfig:
    def test_default_in_config(self):
        from app.config import _DEFAULTS
        assert "auto_compact_threshold" in _DEFAULTS
        assert _DEFAULTS["auto_compact_threshold"] == 8000

    def test_loaded_from_toml(self, tmp_path):
        (tmp_path / "codemitra.toml").write_text(
            'auto_compact_threshold = 4000\n', encoding="utf-8"
        )
        from app.config import load
        cfg = load(cwd=str(tmp_path))
        assert cfg["auto_compact_threshold"] == 4000

    def test_api_key_loaded_from_dotenv(self, tmp_path):
        (tmp_path / ".env").write_text(
            'OLLAMA_API_KEY="dotenv-secret"\n', encoding="utf-8"
        )
        from app.config import load
        cfg = load(cwd=str(tmp_path))
        assert cfg["ollama_api_key"] == "dotenv-secret"
