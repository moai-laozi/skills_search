from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any

from skill_harvester.models import ParsedSkill, ScoreResult, SecurityResult
from skill_harvester.utils import parse_github_datetime

_TRIGGER_WORDS = re.compile(r"\b(?:use|when|whenever|for tasks?|trigger|applies?)\b|用于|适用于|当.{0,12}时", re.I)
_STEPS = re.compile(r"(?m)^\s*(?:\d+[.)]|[-*]\s+|#{2,4}\s+(?:workflow|steps?|process|procedure|instructions?))")
_VALIDATION = re.compile(r"\b(?:test|verify|validate|assert|check|lint|compile|expected output|acceptance criteria|done when)\b|测试|验证|检查|验收", re.I)
_EXAMPLES = re.compile(r"```|\b(?:example|input|output|sample)\b|示例|输入|输出", re.I)
_EDGE_CASES = re.compile(r"\b(?:edge case|failure|error|fallback|retry|exception|troubleshoot|if .* fails?)\b|失败|错误|异常|重试|边界", re.I)
_BOUNDARIES = re.compile(r"\b(?:do not|never|must not|avoid|only|before claiming|stop if|permission)\b|不要|禁止|仅限|必须", re.I)

_CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("security", re.compile(r"security|vulnerab|threat|penetration|secret|auth|安全|漏洞", re.I)),
    ("testing", re.compile(r"test|pytest|unit test|integration|regression|测试|回归", re.I)),
    ("research", re.compile(r"research|literature|paper|citation|academic|科研|文献|论文", re.I)),
    ("data-science", re.compile(r"data analysis|pandas|numpy|matlab|scientific computing|统计|数值|数据分析", re.I)),
    ("devops", re.compile(r"docker|kubernetes|deploy|ci/cd|github actions|terraform|部署|运维", re.I)),
    ("documentation", re.compile(r"document|readme|technical writing|docs|文档|写作", re.I)),
    ("code-quality", re.compile(r"code review|refactor|debug|lint|architecture|代码审查|重构|调试", re.I)),
    ("design", re.compile(r"design|ui|ux|frontend|slide|presentation|视觉|界面|演示", re.I)),
)


def categorize(parsed: ParsedSkill) -> str:
    text = f"{parsed.name}\n{parsed.description}\n{parsed.body[:5000]}"
    for category, pattern in _CATEGORY_PATTERNS:
        if pattern.search(text):
            return category
    return "general"


def _freshness_score(pushed_at: str | None, freshness_days: int) -> float:
    pushed = parse_github_datetime(pushed_at)
    if not pushed:
        return 0.0
    age_days = max(0, (datetime.now(UTC) - pushed).days)
    if age_days <= 180:
        return 4.0
    if age_days <= freshness_days:
        return 3.0
    if age_days <= freshness_days * 2:
        return 1.0
    return 0.0


def score_skill(
    parsed: ParsedSkill,
    repository: dict[str, Any],
    security: SecurityResult,
    config: dict[str, Any],
) -> ScoreResult:
    scoring_cfg = config["scoring"]
    trusted = {owner.lower() for owner in config["search"].get("trusted_owners", [])}
    owner = str(repository.get("owner", {}).get("login", "")).lower()

    spec = 0.0
    spec += 5 if parsed.has_frontmatter else 0
    spec += 5 if parsed.name_valid else 0
    spec += 5 if parsed.description_valid else 0
    spec += 4 if parsed.parent_name_matches else 1
    spec += 3 if parsed.body else 0
    if parsed.line_count <= int(scoring_cfg["maximum_skill_lines"]):
        spec += 4
    if parsed.estimated_tokens <= int(scoring_cfg["maximum_estimated_tokens"]):
        spec += 4
    spec = min(spec, 30.0)

    instruction = 0.0
    description_and_body = f"{parsed.description}\n{parsed.body}"
    instruction += 5 if _TRIGGER_WORDS.search(parsed.description) else 1
    instruction += 7 if _STEPS.search(parsed.body) else 0
    instruction += 6 if _VALIDATION.search(parsed.body) else 0
    instruction += 4 if _EXAMPLES.search(parsed.body) else 0
    instruction += 4 if _EDGE_CASES.search(parsed.body) else 0
    instruction += 4 if _BOUNDARIES.search(parsed.body) else 0
    instruction = min(instruction, 30.0)

    stars = int(repository.get("stargazers_count") or 0)
    repo = 0.0
    repo += 8 if owner in trusted else 0
    repo += min(6.0, math.log10(stars + 1) * 2.0)
    repo += _freshness_score(repository.get("pushed_at"), int(scoring_cfg["freshness_days"]))
    license_info = repository.get("license") or {}
    spdx = str(license_info.get("spdx_id") or "").strip()
    repo += 2 if spdx and spdx not in {"NOASSERTION", "OTHER"} else 0
    repo = min(repo, 20.0)

    penalties = {"critical": 20, "high": 8, "medium": 3, "low": 1}
    safety = 20.0
    for finding in security.findings:
        safety -= penalties.get(finding.severity, 0)
    safety = max(0.0, safety)

    total = round(spec + instruction + repo + safety, 1)
    if security.risk_level == "critical":
        total = min(total, 39.9)
    if not parsed.valid:
        total = min(total, 49.9)

    recommended = float(scoring_cfg["recommended_score"])
    review = float(scoring_cfg["review_score"])
    if total >= recommended and security.risk_level in {"none", "low", "medium"} and parsed.valid:
        grade = "recommended"
    elif total >= review and security.risk_level != "critical":
        grade = "review"
    else:
        grade = "low"

    details = {
        "spec_compliance": round(spec, 1),
        "instruction_quality": round(instruction, 1),
        "repository_quality": round(repo, 1),
        "safety": round(safety, 1),
        "repository_stars": stars,
        "trusted_owner": owner in trusted,
        "contains_trigger_language": bool(_TRIGGER_WORDS.search(parsed.description)),
        "contains_steps": bool(_STEPS.search(parsed.body)),
        "contains_validation": bool(_VALIDATION.search(parsed.body)),
        "contains_examples": bool(_EXAMPLES.search(parsed.body)),
        "contains_edge_cases": bool(_EDGE_CASES.search(parsed.body)),
        "contains_boundaries": bool(_BOUNDARIES.search(parsed.body)),
        "text_length": len(description_and_body),
    }
    return ScoreResult(total=total, grade=grade, category=categorize(parsed), details=details)
