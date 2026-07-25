from skill_harvester.config import DEFAULT_CONFIG
from skill_harvester.parser import parse_skill
from skill_harvester.scoring import score_skill
from skill_harvester.security import scan_security


def test_structured_skill_scores_above_empty_skill() -> None:
    good = """---
name: testing-helper
description: Use this skill when adding regression tests or debugging test failures.
---
## Workflow
1. Reproduce the failure.
2. Add a minimal regression test.
3. Run the complete test suite.

## Validation
Do not claim completion until the new test fails before the fix and passes after it.

## Example
```bash
pytest -q
```
"""
    weak = """---
name: helper
description: Helps with things.
---
Be helpful.
"""
    repo = {
        "owner": {"login": "someone"},
        "stargazers_count": 10,
        "pushed_at": "2026-01-01T00:00:00Z",
        "license": {"spdx_id": "MIT"},
    }
    good_parsed = parse_skill(good, "skills/testing-helper/SKILL.md")
    weak_parsed = parse_skill(weak, "skills/helper/SKILL.md")
    good_score = score_skill(good_parsed, repo, scan_security(good), DEFAULT_CONFIG)
    weak_score = score_skill(weak_parsed, repo, scan_security(weak), DEFAULT_CONFIG)
    assert good_score.total > weak_score.total
