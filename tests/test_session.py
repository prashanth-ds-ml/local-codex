"""Tests for app/agents/session.py."""

from app import memory
from app.agents import session as session_agent


class TestSessionAgent:
    def test_ensure_session_creates_metadata(self, tmp_path):
        metadata = session_agent.ensure_session(str(tmp_path))
        assert metadata["name"] == tmp_path.name

    def test_rename_session_updates_name(self, tmp_path):
        session_agent.ensure_session(str(tmp_path))
        metadata = session_agent.rename_session(str(tmp_path), "Focus Sprint")
        assert metadata["name"] == "Focus Sprint"

    def test_build_resume_reply_includes_recent_activity(self, tmp_path):
        memory.append_activity(str(tmp_path), "what changed?", "here is the summary")
        reply = session_agent.build_resume_reply(str(tmp_path))
        assert "Session resume" in reply
        assert "what changed?" in reply

    def test_build_resume_reply_includes_active_plan_checkpoint(self, tmp_path):
        metadata = memory.ensure_session_metadata(str(tmp_path))
        memory.save_session_metadata(
            str(tmp_path),
            {
                **metadata,
                "plan_execution": {
                    "goal": "Ship feature",
                    "approved": True,
                    "status": "paused",
                },
                "active_plan_step": {
                    "goal": "Ship feature",
                    "index": 1,
                    "text": "Run pytest",
                    "status": "paused",
                },
            },
        )

        reply = session_agent.build_resume_reply(str(tmp_path))

        assert "Plan execution" in reply
        assert "`approved` · `paused`" in reply
        assert "Plan checkpoint" in reply
        assert "Step 2 `paused` - Run pytest" in reply
        assert "Use `/plan next` to continue." in reply

    def test_build_resume_reply_includes_last_compaction(self, tmp_path):
        metadata = memory.ensure_session_metadata(str(tmp_path))
        memory.save_session_metadata(
            str(tmp_path),
            {
                **metadata,
                "last_compaction": {
                    "reason": "auto",
                    "compacted_at": "2026-05-11T12:00:00",
                    "turns_compacted": 4,
                    "usage_tokens_before": 120000,
                },
            },
        )

        reply = session_agent.build_resume_reply(str(tmp_path))

        assert "Last compaction" in reply
        assert "`auto` at 2026-05-11T12:00:00" in reply
        assert "4 turns" in reply
        assert "120,000 tokens before compact" in reply

    def test_render_resume_returns_panel(self):
        panel = session_agent.render_resume("## Session resume")
        assert panel is not None
        assert "Session Resume" in str(panel.title)


class TestSessionMetadataTrust:
    def test_trust_shell_command_persists_per_directory(self, tmp_path):
        memory.trust_shell_command(str(tmp_path), str(tmp_path), "pytest")

        assert memory.is_shell_command_trusted(str(tmp_path), str(tmp_path), "pytest") is True
        assert memory.is_shell_command_trusted(str(tmp_path), str(tmp_path), "python") is False
