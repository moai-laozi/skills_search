from __future__ import annotations

import logging
from typing import Any

from skill_harvester.db import SkillDatabase, encode_json
from skill_harvester.github_client import GitHubAPIError, GitHubClient
from skill_harvester.parser import parse_skill
from skill_harvester.scoring import score_skill
from skill_harvester.security import scan_security
from skill_harvester.utils import normalize_markdown, sha256_text, utc_now_iso

LOGGER = logging.getLogger(__name__)


def _security_to_dict(security: Any) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": finding.rule_id,
            "severity": finding.severity,
            "message": finding.message,
            "matches": finding.matches,
        }
        for finding in security.findings
    ]


def collect_candidates(client: GitHubClient, config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    github_cfg = config["github"]
    candidates: dict[str, dict[str, Any]] = {}
    max_total = int(github_cfg["max_candidates_total"])
    max_per_query = int(github_cfg["max_candidates_per_query"])
    blocked = {owner.lower() for owner in config["search"].get("blocked_owners", [])}

    for query_value in config["search"]["queries"]:
        query = str(query_value).strip()
        if not query:
            continue
        LOGGER.info("Searching GitHub code: %s", query)
        found_for_query = 0
        try:
            for item in client.search_code(
                query,
                per_page=int(github_cfg["per_page"]),
                max_pages=int(github_cfg["max_pages_per_query"]),
            ):
                repo = item.get("repository") or {}
                owner = str((repo.get("owner") or {}).get("login") or "").lower()
                if owner in blocked:
                    continue
                full_name = str(repo.get("full_name") or "")
                path = str(item.get("path") or "")
                if not full_name or not path or path.rsplit("/", 1)[-1] != "SKILL.md":
                    continue
                key = f"{full_name}:{path}"
                if key not in candidates:
                    candidates[key] = {"item": item, "queries": []}
                    found_for_query += 1
                if query not in candidates[key]["queries"]:
                    candidates[key]["queries"].append(query)
                if found_for_query >= max_per_query or len(candidates) >= max_total:
                    break
        except GitHubAPIError as exc:
            LOGGER.error("Search query failed and was skipped: %s", exc)
        LOGGER.info("Candidate total after query: %d", len(candidates))
        if len(candidates) >= max_total:
            LOGGER.warning("Reached github.max_candidates_total=%d", max_total)
            break
    return candidates


def discover(config: dict[str, Any], token: str | None = None) -> dict[str, int]:
    client = GitHubClient(config, token=token)
    candidates = collect_candidates(client, config)
    now = utc_now_iso()
    processed = 0
    skipped = 0
    failed = 0

    with SkillDatabase(config["storage"]["database_path"]) as database:
        for canonical_key, candidate in candidates.items():
            item = candidate["item"]
            repository_stub = item.get("repository") or {}
            repository_url = str(repository_stub.get("url") or "")
            try:
                repository = client.get_repository(repository_url)
                if bool(config["search"].get("skip_archived_repositories", True)) and repository.get("archived"):
                    skipped += 1
                    continue
                if int(repository.get("stargazers_count") or 0) < int(config["search"].get("minimum_repository_stars", 0)):
                    skipped += 1
                    continue

                content, blob_sha, raw_url = client.get_code_content(str(item["url"]))
                parsed = parse_skill(content, str(item.get("path") or "SKILL.md"))
                security = scan_security(content)
                score = score_skill(parsed, repository, security, config)

                owner = str((repository.get("owner") or {}).get("login") or "")
                repo_name = str(repository.get("name") or "")
                full_name = str(repository.get("full_name") or f"{owner}/{repo_name}")
                license_info = repository.get("license") or {}
                normalized = normalize_markdown(content)

                record = {
                    "canonical_key": canonical_key,
                    "owner": owner,
                    "repository": repo_name,
                    "repository_full_name": full_name,
                    "repository_url": str(repository.get("html_url") or ""),
                    "skill_url": str(item.get("html_url") or ""),
                    "raw_url": raw_url,
                    "path": str(item.get("path") or ""),
                    "blob_sha": blob_sha or str(item.get("sha") or ""),
                    "name": parsed.name,
                    "description": parsed.description,
                    "body": parsed.body,
                    "metadata_json": encode_json(parsed.metadata),
                    "content_sha256": sha256_text(content),
                    "normalized_sha256": sha256_text(normalized),
                    "repository_stars": int(repository.get("stargazers_count") or 0),
                    "repository_forks": int(repository.get("forks_count") or 0),
                    "repository_archived": 1 if repository.get("archived") else 0,
                    "repository_pushed_at": repository.get("pushed_at"),
                    "repository_license": str(license_info.get("spdx_id") or ""),
                    "valid": 1 if parsed.valid else 0,
                    "parse_errors_json": encode_json(parsed.errors),
                    "parse_warnings_json": encode_json(parsed.warnings),
                    "referenced_paths_json": encode_json(parsed.referenced_paths),
                    "line_count": parsed.line_count,
                    "estimated_tokens": parsed.estimated_tokens,
                    "risk_level": security.risk_level,
                    "security_findings_json": encode_json(_security_to_dict(security)),
                    "score_total": score.total,
                    "score_grade": score.grade,
                    "score_details_json": encode_json(score.details),
                    "category": score.category,
                    "query_hits_json": encode_json(candidate["queries"]),
                    "discovered_at": now,
                    "last_seen_at": now,
                }
                database.upsert(record)
                processed += 1
                LOGGER.info(
                    "[%s | %.1f | %s] %s",
                    score.grade,
                    score.total,
                    security.risk_level,
                    canonical_key,
                )
            except (GitHubAPIError, KeyError, TypeError, ValueError) as exc:
                failed += 1
                LOGGER.warning("Failed candidate %s: %s", canonical_key, exc)
        database.refresh_duplicates()
        stats = database.stats()

    stats.update({"processed_this_run": processed, "skipped_this_run": skipped, "failed_this_run": failed})
    return stats
