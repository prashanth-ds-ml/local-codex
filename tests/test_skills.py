"""Tests for CodeMitra skill discovery."""

from app import skills


class TestSkillDiscovery:
    def test_discovers_skill_frontmatter(self, tmp_path):
        skill_dir = tmp_path / "skills" / "repo-analyzer"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: repo-analyzer\n"
            "description: Analyze repositories before editing.\n"
            "---\n"
            "\n"
            "# Repo Analyzer\n",
            encoding="utf-8",
        )

        discovered = skills.discover(str(tmp_path))

        assert len(discovered) == 1
        assert discovered[0].name == "repo-analyzer"
        assert discovered[0].path.replace("/", "\\") == "skills\\repo-analyzer\\SKILL.md"

    def test_ignores_skill_dirs_outside_workspace(self, tmp_path):
        outside = tmp_path.parent / "outside-skills"
        outside.mkdir(exist_ok=True)

        discovered = skills.discover(str(tmp_path), [str(outside)])

        assert discovered == []

    def test_format_prompt_lists_skill_index_and_read_instruction(self, tmp_path):
        skill = skills.Skill(
            name="rag-pipeline",
            description="Build or review RAG pipelines.",
            path="skills\\rag-pipeline\\SKILL.md",
        )

        prompt = skills.format_prompt([skill])

        assert "Available CodeMitra Skills" in prompt
        assert "read that skill's `SKILL.md`" in prompt
        assert "`rag-pipeline`" in prompt

    def test_find_supports_exact_and_partial_match(self):
        registry = [
            skills.Skill("repo-analyzer", "Analyze repos.", "skills\\01-repo-analyzer\\SKILL.md"),
            skills.Skill("rag-pipeline", "Build RAG.", "skills\\05-rag-pipeline\\SKILL.md"),
        ]

        assert skills.find(registry, "repo-analyzer").name == "repo-analyzer"
        assert skills.find(registry, "05-rag-pipeline").name == "rag-pipeline"
        assert skills.find(registry, "rag").name == "rag-pipeline"

    def test_find_returns_none_for_ambiguous_partial_match(self):
        registry = [
            skills.Skill("rag-pipeline", "Build RAG.", "skills\\05-rag-pipeline\\SKILL.md"),
            skills.Skill("rag-evaluation", "Evaluate RAG.", "skills\\15-rag-evaluation\\SKILL.md"),
        ]

        assert skills.find(registry, "rag") is None

    def test_read_body_uses_workspace_relative_path(self, tmp_path):
        skill_dir = tmp_path / "skills" / "repo-analyzer"
        skill_dir.mkdir(parents=True)
        body = "---\nname: repo-analyzer\ndescription: Analyze repos.\n---\n# Repo Analyzer\n"
        (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
        skill = skills.Skill("repo-analyzer", "Analyze repos.", "skills\\repo-analyzer\\SKILL.md")

        assert skills.read_body(str(tmp_path), skill) == body
