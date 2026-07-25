from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "github": {
        "api_url": "https://api.github.com",
        "api_version": "2026-03-10",
        "token_env": "GH_SEARCH_TOKEN",
        "fallback_token_env": "GITHUB_TOKEN",
        "request_timeout_seconds": 30,
        "request_interval_seconds": 0.15,
        "max_retries": 4,
        "max_retry_wait_seconds": 90,
        "search_interval_seconds": 7,
        "per_page": 100,
        "max_pages_per_query": 1,
        "max_candidates_total": 500,
        "max_candidates_per_query": 100,
        "max_file_bytes": 250000,
    },
    "search": {
        "queries": ["filename:SKILL.md path:skills"],
        "trusted_owners": [],
        "blocked_owners": [],
        "skip_archived_repositories": True,
        "minimum_repository_stars": 0,
    },
    "storage": {
        "database_path": "data/skills.db",
        "jsonl_path": "data/skills.jsonl",
        "report_directory": "reports",
    },
    "scoring": {
        "recommended_score": 70,
        "review_score": 50,
        "maximum_skill_lines": 500,
        "maximum_estimated_tokens": 5000,
        "freshness_days": 730,
    },
    "report": {
        "top_n": 100,
        "include_invalid": True,
        "write_dated_report": True,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError("Configuration root must be a YAML mapping.")
    config = _deep_merge(DEFAULT_CONFIG, loaded)
    queries = config["search"].get("queries", [])
    if not isinstance(queries, list) or not any(str(q).strip() for q in queries):
        raise ValueError("search.queries must contain at least one query.")
    return config
