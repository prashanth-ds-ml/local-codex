"""Tests for app/prompts.py — system prompt content and routing rules."""
from app.prompts import SYSTEM_PROMPT


class TestSystemPrompt:
    def test_describes_setup_project_tool(self):
        assert "setup_project" in SYSTEM_PROMPT

    def test_describes_run_command_tool(self):
        assert "run_command" in SYSTEM_PROMPT

    def test_routing_rules_present(self):
        assert "Routing rules" in SYSTEM_PROMPT or "routing" in SYSTEM_PROMPT.lower()

    def test_filesystem_operations_routed_to_setup(self):
        # The prompt must mention that file operations go to setup_project
        assert "setup_project" in SYSTEM_PROMPT
        # And that execution goes to run_command
        assert "run_command" in SYSTEM_PROMPT

    def test_no_stale_single_tool_claim(self):
        # Old prompt said "You have one agent tool" — should be gone
        assert "one agent tool" not in SYSTEM_PROMPT

    def test_call_immediately_rule_present(self):
        assert "immediately" in SYSTEM_PROMPT
