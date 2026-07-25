from skill_harvester.parser import parse_skill


def test_valid_skill() -> None:
    content = """---
name: code-review
description: Use this skill when reviewing a pull request for correctness and security.
license: MIT
---
## Workflow
1. Inspect the diff.
2. Run tests.
3. Report findings with file references.
"""
    parsed = parse_skill(content, ".agents/skills/code-review/SKILL.md")
    assert parsed.valid
    assert parsed.name == "code-review"
    assert parsed.parent_name_matches
    assert parsed.description_valid


def test_missing_frontmatter_is_invalid() -> None:
    parsed = parse_skill("# Instructions\nDo something", "skills/example/SKILL.md")
    assert not parsed.valid
    assert "missing_yaml_frontmatter" in parsed.errors
