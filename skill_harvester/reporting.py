from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from skill_harvester.db import SkillDatabase, decode_json
from skill_harvester.utils import ensure_directory, ensure_parent, markdown_escape, truncate


def _public_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_key": row["canonical_key"],
        "name": row["name"],
        "description": row["description"],
        "category": row["category"],
        "score": row["score_total"],
        "grade": row["score_grade"],
        "risk_level": row["risk_level"],
        "valid": bool(row["valid"]),
        "duplicate_of": row["duplicate_of"],
        "repository": row["repository_full_name"],
        "repository_stars": row["repository_stars"],
        "repository_license": row["repository_license"],
        "repository_pushed_at": row["repository_pushed_at"],
        "skill_url": row["skill_url"],
        "path": row["path"],
        "parse_errors": decode_json(row["parse_errors_json"], []),
        "parse_warnings": decode_json(row["parse_warnings_json"], []),
        "security_findings": decode_json(row["security_findings_json"], []),
        "score_details": decode_json(row["score_details_json"], {}),
        "query_hits": decode_json(row["query_hits_json"], []),
        "discovered_at": row["discovered_at"],
        "last_seen_at": row["last_seen_at"],
    }


def _table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_无结果。_\n"
    lines = [
        "| 分数 | 风险 | 分类 | Skill | 仓库 | Stars | 说明 |",
        "|---:|---|---|---|---|---:|---|",
    ]
    for row in rows:
        name = markdown_escape(row["name"] or Path(row["path"]).parent.name or "unnamed")
        link = row["skill_url"]
        skill_cell = f"[{name}]({link})" if link else name
        repo_url = row["repository_url"]
        repo_name = markdown_escape(row["repository_full_name"])
        repo_cell = f"[{repo_name}]({repo_url})" if repo_url else repo_name
        lines.append(
            "| {score:.1f} | {risk} | {category} | {skill} | {repo} | {stars} | {desc} |".format(
                score=float(row["score_total"]),
                risk=markdown_escape(row["risk_level"]),
                category=markdown_escape(row["category"]),
                skill=skill_cell,
                repo=repo_cell,
                stars=int(row["repository_stars"]),
                desc=markdown_escape(truncate(row["description"] or "", 140)),
            )
        )
    return "\n".join(lines) + "\n"


def generate_reports(config: dict[str, Any]) -> dict[str, str]:
    database_path = config["storage"]["database_path"]
    with SkillDatabase(database_path) as database:
        rows = database.fetch_all()
        stats = database.stats()

    report_dir = ensure_directory(config["storage"]["report_directory"])
    top_n = int(config["report"]["top_n"])
    recommended = [r for r in rows if r["score_grade"] == "recommended" and not r["duplicate_of"]][:top_n]
    review = [r for r in rows if r["score_grade"] == "review" and not r["duplicate_of"]][:top_n]
    high_risk = [r for r in rows if r["risk_level"] in {"high", "critical"} and not r["duplicate_of"]][:top_n]
    duplicates = [r for r in rows if r["duplicate_of"]][:top_n]

    generated = datetime.now(UTC).replace(microsecond=0)
    report = f"""# Agent Skills 自动搜索报告

生成时间：{generated.isoformat()}  
数据库：`{database_path}`

> 本系统只下载和静态分析 `SKILL.md`，不会执行候选 Skill 中的命令或脚本。高分仅表示值得审核，不表示可以直接安装。

## 汇总

| 指标 | 数量 |
|---|---:|
| 总记录 | {stats['total']} |
| 格式有效 | {stats['valid']} |
| 推荐审核 | {stats['recommended']} |
| 待人工复核 | {stats['review']} |
| 高/严重风险 | {stats['high_risk']} |
| 完全重复 | {stats['duplicates']} |

## 推荐审核

{_table(recommended)}

## 待人工复核

{_table(review)}

## 高风险候选

{_table(high_risk)}

## 重复内容

{_table(duplicates)}

## 使用说明

1. 先打开 Skill 链接阅读完整目录，而不只看 `SKILL.md`。
2. 检查许可证、脚本、网络访问、凭据读取和环境要求。
3. 在隔离目录或容器中测试，不要自动安装到主力 Agent 环境。
4. 真正采用前，使用同一任务进行“加载 Skill / 不加载 Skill”的 A/B 验证。
"""

    latest_md = report_dir / "latest.md"
    latest_md.write_text(report, encoding="utf-8")
    output = {"latest_report": str(latest_md)}

    if bool(config["report"].get("write_dated_report", True)):
        dated = report_dir / f"{generated.date().isoformat()}.md"
        dated.write_text(report, encoding="utf-8")
        output["dated_report"] = str(dated)

    jsonl_path = ensure_parent(config["storage"]["jsonl_path"])
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_public_record(row), ensure_ascii=False, sort_keys=True) + "\n")
    output["jsonl"] = str(jsonl_path)

    csv_path = report_dir / "latest.csv"
    public = [_public_record(row) for row in rows]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "score", "grade", "risk_level", "category", "name", "description", "repository",
            "repository_stars", "repository_license", "skill_url", "path", "duplicate_of", "last_seen_at",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(public)
    output["csv"] = str(csv_path)
    return output
