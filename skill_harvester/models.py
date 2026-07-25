from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ParsedSkill:
    name: str
    description: str
    body: str
    metadata: dict[str, Any]
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    line_count: int = 0
    estimated_tokens: int = 0
    referenced_paths: list[str] = field(default_factory=list)
    has_frontmatter: bool = False
    name_valid: bool = False
    description_valid: bool = False
    parent_name_matches: bool = False


@dataclass(slots=True)
class SecurityFinding:
    rule_id: str
    severity: str
    message: str
    matches: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SecurityResult:
    risk_level: str
    findings: list[SecurityFinding] = field(default_factory=list)


@dataclass(slots=True)
class ScoreResult:
    total: float
    grade: str
    category: str
    details: dict[str, Any]
