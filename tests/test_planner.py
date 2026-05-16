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
        memory.mark_step_done(str(tmp_path), 0)
        memory.mark_step_done(str(tmp_path), 1)
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

    def test_render_flow_panel(self, tmp_path):
        memory.write_plan(str(tmp_path), goal="Build something", steps=["Step 1", "Step 2"])
        plan = planner_agent._parse_plan(str(tmp_path))
        panel = planner_agent.render_flow(plan, current_step=plan.steps[0])
        assert panel is not None
        assert "Task Flow" in str(panel.title)


# ── Step model ────────────────────────────────────────────────────────────────

class TestStep:
    def test_step_defaults_not_done(self):
        step = planner_agent.Step(index=0, text="Do something")
        assert step.done is False

    def test_step_can_be_marked_done(self):
        step = planner_agent.Step(index=0, text="Do something", done=True)
        assert step.done is True

    def test_empty_plan_is_not_done(self):
        plan = planner_agent.Plan(goal="X", steps=[])
        assert plan.is_done is False


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

    def test_empty_step_plan_returns_guard_message(self, tmp_path):
        memory.write_plan(str(tmp_path), goal="X", steps=[])
        result = planner_agent.run_plan(llm=None, workspace=str(tmp_path))
        assert "no actionable steps" in result.lower()

    def test_run_plan_records_completed_active_step_checkpoint(self, monkeypatch, tmp_path):
        memory.write_plan(str(tmp_path), goal="Ship feature", steps=["Inspect app.py"])
        monkeypatch.setattr(planner_agent, "_route_step", lambda llm, step_text: "direct")

        class FakeLLM:
            def invoke(self, messages):
                return type("Resp", (), {"content": "Inspected app.py."})()

        planner_agent.run_plan(FakeLLM(), str(tmp_path), max_steps=1)
        metadata = memory.load_session_metadata(str(tmp_path))

        assert metadata is not None
        assert metadata["active_plan_step"]["index"] == 0
        assert metadata["active_plan_step"]["text"] == "Inspect app.py"
        assert metadata["active_plan_step"]["status"] == "completed"

    def test_run_plan_records_interrupted_active_step_checkpoint(self, monkeypatch, tmp_path):
        memory.write_plan(str(tmp_path), goal="Ship feature", steps=["Patch app.py"])
        monkeypatch.setattr(planner_agent, "_route_step", lambda llm, step_text: "direct")

        def interrupt(*args, **kwargs):
            raise KeyboardInterrupt()

        monkeypatch.setattr(planner_agent, "execute_step", interrupt)

        with pytest.raises(KeyboardInterrupt):
            planner_agent.run_plan(llm=object(), workspace=str(tmp_path), max_steps=1)

        metadata = memory.load_session_metadata(str(tmp_path))
        assert metadata is not None
        assert metadata["active_plan_step"]["index"] == 0
        assert metadata["active_plan_step"]["text"] == "Patch app.py"
        assert metadata["active_plan_step"]["status"] == "interrupted"

    def test_run_plan_marks_absolute_step_index_after_prior_completion(self, monkeypatch, tmp_path):
        memory.write_plan(str(tmp_path), goal="Ship feature", steps=["Inspect app.py", "Patch app.py", "Run pytest"])
        memory.mark_step_done(str(tmp_path), 0)
        monkeypatch.setattr(planner_agent, "_route_step", lambda llm, step_text: "direct")

        class FakeLLM:
            def invoke(self, messages):
                return type("Resp", (), {"content": "Patched app.py."})()

        planner_agent.run_plan(FakeLLM(), str(tmp_path), max_steps=1)
        plan = planner_agent._parse_plan(str(tmp_path))

        assert plan is not None
        assert [step.done for step in plan.steps] == [True, True, False]


class TestPlanExecutionState:
    def test_create_plan_resets_approval_state(self, tmp_path):
        class FakeLLM:
            def invoke(self, messages):
                return type("Resp", (), {"content": "1. Inspect app.py"})()

        plan = planner_agent.create_plan(FakeLLM(), "Ship feature", str(tmp_path))
        metadata = memory.load_session_metadata(str(tmp_path))

        assert plan.goal == "Ship feature"
        assert metadata is not None
        assert metadata["plan_execution"]["approved"] is False
        assert metadata["plan_execution"]["status"] == "draft"

    def test_approve_plan_persists_current_goal(self, tmp_path):
        memory.write_plan(str(tmp_path), goal="Ship feature", steps=["Inspect app.py"])

        reply = planner_agent.approve_plan(str(tmp_path))
        metadata = memory.load_session_metadata(str(tmp_path))

        assert "Approved the active plan" in reply
        assert metadata is not None
        assert metadata["plan_execution"]["approved"] is True
        assert metadata["plan_execution"]["goal"] == "Ship feature"
        assert planner_agent.is_plan_approved(str(tmp_path)) is True

    def test_pause_plan_marks_active_checkpoint_paused(self, tmp_path):
        memory.write_plan(str(tmp_path), goal="Ship feature", steps=["Inspect app.py"])
        metadata = memory.ensure_session_metadata(str(tmp_path))
        memory.save_session_metadata(
            str(tmp_path),
            {
                **metadata,
                "active_plan_step": {
                    "goal": "Ship feature",
                    "index": 0,
                    "text": "Inspect app.py",
                    "status": "running",
                },
            },
        )

        reply = planner_agent.pause_plan(str(tmp_path))
        metadata = memory.load_session_metadata(str(tmp_path))

        assert "Paused the active plan" in reply
        assert metadata is not None
        assert metadata["plan_execution"]["status"] == "paused"
        assert metadata["active_plan_step"]["status"] == "paused"


class TestCreatePlanFallback:
    def test_create_plan_falls_back_when_llm_returns_empty(self, tmp_path):
        class FakeLLM:
            def invoke(self, messages):
                return type("Resp", (), {"content": ""})()

        plan = planner_agent.create_plan(FakeLLM(), "Create a folder", str(tmp_path))

        assert len(plan.steps) == 1
        assert "Clarify or restate the goal" in plan.steps[0].text


# ── Config: auto_compact_threshold ───────────────────────────────────────────

class TestAutoCompactConfig:
    def test_default_in_config(self):
        from app.config import _DEFAULTS
        assert "auto_compact_threshold" in _DEFAULTS
        assert _DEFAULTS["auto_compact_threshold"] == 120000
        assert _DEFAULTS["num_ctx"] == 131072

    def test_loaded_from_toml(self, tmp_path):
        (tmp_path / "codemitra.toml").write_text(
            'auto_compact_threshold = 4000\nnum_ctx = 16000\n', encoding="utf-8"
        )
        from app.config import load
        cfg = load(cwd=str(tmp_path))
        assert cfg["auto_compact_threshold"] == 4000
        assert cfg["num_ctx"] == 16000

    def test_api_key_loaded_from_dotenv(self, tmp_path):
        (tmp_path / ".env").write_text(
            'OLLAMA_API_KEY="dotenv-secret"\n', encoding="utf-8"
        )
        from app.config import load
        cfg = load(cwd=str(tmp_path))
        assert cfg["ollama_api_key"] == "dotenv-secret"
