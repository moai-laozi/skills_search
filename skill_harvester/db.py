from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from skill_harvester.utils import ensure_parent, stable_json


SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_key TEXT NOT NULL UNIQUE,
    owner TEXT NOT NULL,
    repository TEXT NOT NULL,
    repository_full_name TEXT NOT NULL,
    repository_url TEXT NOT NULL,
    skill_url TEXT NOT NULL,
    raw_url TEXT,
    path TEXT NOT NULL,
    blob_sha TEXT,
    name TEXT,
    description TEXT,
    body TEXT,
    metadata_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    normalized_sha256 TEXT NOT NULL,
    repository_stars INTEGER NOT NULL DEFAULT 0,
    repository_forks INTEGER NOT NULL DEFAULT 0,
    repository_archived INTEGER NOT NULL DEFAULT 0,
    repository_pushed_at TEXT,
    repository_license TEXT,
    valid INTEGER NOT NULL DEFAULT 0,
    parse_errors_json TEXT NOT NULL,
    parse_warnings_json TEXT NOT NULL,
    referenced_paths_json TEXT NOT NULL,
    line_count INTEGER NOT NULL DEFAULT 0,
    estimated_tokens INTEGER NOT NULL DEFAULT 0,
    risk_level TEXT NOT NULL,
    security_findings_json TEXT NOT NULL,
    score_total REAL NOT NULL DEFAULT 0,
    score_grade TEXT NOT NULL,
    score_details_json TEXT NOT NULL,
    category TEXT NOT NULL,
    query_hits_json TEXT NOT NULL,
    duplicate_of TEXT,
    discovered_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skills_score ON skills(score_total DESC);
CREATE INDEX IF NOT EXISTS idx_skills_normalized_sha ON skills(normalized_sha256);
CREATE INDEX IF NOT EXISTS idx_skills_risk ON skills(risk_level);
CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category);
"""


class SkillDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = ensure_parent(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SkillDatabase":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc_type is None:
            self.connection.commit()
        self.close()

    def upsert(self, record: dict[str, Any]) -> None:
        columns = [
            "canonical_key", "owner", "repository", "repository_full_name", "repository_url",
            "skill_url", "raw_url", "path", "blob_sha", "name", "description", "body",
            "metadata_json", "content_sha256", "normalized_sha256", "repository_stars",
            "repository_forks", "repository_archived", "repository_pushed_at", "repository_license",
            "valid", "parse_errors_json", "parse_warnings_json", "referenced_paths_json",
            "line_count", "estimated_tokens", "risk_level", "security_findings_json",
            "score_total", "score_grade", "score_details_json", "category", "query_hits_json",
            "discovered_at", "last_seen_at",
        ]
        values = [record[column] for column in columns]
        updates = [f"{column}=excluded.{column}" for column in columns if column not in {"canonical_key", "discovered_at"}]
        sql = f"""
            INSERT INTO skills ({','.join(columns)})
            VALUES ({','.join('?' for _ in columns)})
            ON CONFLICT(canonical_key) DO UPDATE SET {','.join(updates)}
        """
        self.connection.execute(sql, values)

    def refresh_duplicates(self) -> None:
        self.connection.execute("UPDATE skills SET duplicate_of = NULL")
        groups = self.connection.execute(
            """
            SELECT normalized_sha256
            FROM skills
            WHERE normalized_sha256 <> ''
            GROUP BY normalized_sha256
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for group in groups:
            rows = self.connection.execute(
                """
                SELECT canonical_key
                FROM skills
                WHERE normalized_sha256 = ?
                ORDER BY score_total DESC, repository_stars DESC, discovered_at ASC
                """,
                (group["normalized_sha256"],),
            ).fetchall()
            winner = rows[0]["canonical_key"]
            for row in rows[1:]:
                self.connection.execute(
                    "UPDATE skills SET duplicate_of = ? WHERE canonical_key = ?",
                    (winner, row["canonical_key"]),
                )
        self.connection.commit()

    def fetch_all(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM skills ORDER BY score_total DESC, repository_stars DESC, canonical_key ASC"
        ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, int]:
        row = self.connection.execute(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN valid = 1 THEN 1 ELSE 0 END) AS valid,
              SUM(CASE WHEN score_grade = 'recommended' AND duplicate_of IS NULL THEN 1 ELSE 0 END) AS recommended,
              SUM(CASE WHEN score_grade = 'review' AND duplicate_of IS NULL THEN 1 ELSE 0 END) AS review,
              SUM(CASE WHEN risk_level IN ('high', 'critical') THEN 1 ELSE 0 END) AS high_risk,
              SUM(CASE WHEN duplicate_of IS NOT NULL THEN 1 ELSE 0 END) AS duplicates
            FROM skills
            """
        ).fetchone()
        return {key: int(row[key] or 0) for key in row.keys()}


def encode_json(value: Any) -> str:
    return stable_json(value)


def decode_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
