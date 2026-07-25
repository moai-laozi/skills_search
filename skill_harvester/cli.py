from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

from skill_harvester.config import load_config
from skill_harvester.db import SkillDatabase
from skill_harvester.discovery import discover
from skill_harvester.github_client import GitHubAPIError
from skill_harvester.reporting import generate_reports


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill-harvester",
        description="Discover, inspect, score, deduplicate, and report public Agent Skills from GitHub.",
    )
    parser.add_argument("--config", default="config/config.yml", help="Path to YAML configuration file.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logs.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("discover", help="Search GitHub and update the local SQLite catalog.")
    subparsers.add_parser("generate-report", help="Generate Markdown, CSV, and JSONL reports from the database.")
    subparsers.add_parser("run", help="Run discovery and then generate reports.")
    subparsers.add_parser("stats", help="Print database statistics.")
    return parser


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _configure_logging(args.verbose)
    try:
        config = load_config(args.config)
        if args.command == "discover":
            _print(discover(config))
        elif args.command == "generate-report":
            _print(generate_reports(config))
        elif args.command == "run":
            result = {"discovery": discover(config), "outputs": generate_reports(config)}
            _print(result)
        elif args.command == "stats":
            with SkillDatabase(config["storage"]["database_path"]) as database:
                _print(database.stats())
        else:
            raise AssertionError(f"Unhandled command: {args.command}")
        return 0
    except (FileNotFoundError, ValueError, GitHubAPIError, OSError) as exc:
        logging.getLogger(__name__).error("%s", exc)
        if os.getenv("GITHUB_ACTIONS") == "true":
            print(f"::error::{exc}")
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
