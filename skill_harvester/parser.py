from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

import yaml

from skill_harvester.models import ParsedSkill
from skill_harvester.utils import estimated_tokens

_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONTMATTER_RE = re.compile(r"\A\ufeff?---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_REFERENCE_RE = re.compile(
    r"(?<![\w.-])((?:scripts|references|assets)/[A-Za-z0-9_./@+ -]+)",
    re.IGNORECASE,
)


def _fallback_frontmatter(block: str) -> dict[str, Any]:
    """Best-effort parser for common malformed YAML such as unquoted colons."""
    metadata: dict[str, Any] = {}
    current_key: str | None = None
    continuation: list[str] = []

    def flush() -> None:
        nonlocal current_key, continuation
        if current_key is not None and continuation:
            metadata[current_key] = "\n".join(continuation).strip()
        current_key = None
        continuation = []

    for raw_line in block.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", raw_line)
        if match and not raw_line.startswith((" ", "\t")):
            flush()
            key, value = match.groups()
            if value in {"|", ">"}:
                current_key = key
            else:
                metadata[key] = value.strip().strip('"\'')
        elif current_key is not None:
            continuation.append(raw_line.strip())
    flush()
    return metadata


def parse_skill(content: str, path: str) -> ParsedSkill:
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    errors: list[str] = []
    warnings: list[str] = []
    metadata: dict[str, Any] = {}
    body = content.strip()
    has_frontmatter = False

    match = _FRONTMATTER_RE.search(content)
    if match:
        has_frontmatter = True
        yaml_block = match.group(1)
        body = content[match.end() :].strip()
        try:
            parsed = yaml.safe_load(yaml_block) or {}
            if not isinstance(parsed, dict):
                errors.append("frontmatter_not_mapping")
            else:
                metadata = parsed
        except yaml.YAMLError:
            metadata = _fallback_frontmatter(yaml_block)
            warnings.append("frontmatter_used_fallback_parser")
            if not metadata:
                errors.append("frontmatter_unparseable")
    else:
        errors.append("missing_yaml_frontmatter")

    path_obj = PurePosixPath(path)
    parent_name = path_obj.parent.name if path_obj.parent.name not in {"", "."} else ""
    inferred_name = parent_name or path_obj.stem.lower()

    name_present = "name" in metadata
    raw_name = metadata.get("name", inferred_name)
    name = str(raw_name).strip() if raw_name is not None else ""
    raw_description = metadata.get("description", "")
    description = str(raw_description).strip() if raw_description is not None else ""

    name_valid = name_present and bool(name) and len(name) <= 64 and bool(_NAME_RE.fullmatch(name))
    if not name_present or not name:
        errors.append("missing_name")
    elif not name_valid:
        errors.append("invalid_name")

    description_valid = 1 <= len(description) <= 1024
    if not description:
        errors.append("missing_description")
    elif len(description) > 1024:
        errors.append("description_too_long")

    parent_name_matches = not parent_name or name == parent_name
    if name and parent_name and not parent_name_matches:
        warnings.append("name_does_not_match_parent_directory")

    if not body:
        errors.append("empty_body")

    references = sorted({m.group(1).strip().rstrip(".,);`") for m in _REFERENCE_RE.finditer(body)})
    line_count = len(content.splitlines())
    token_estimate = estimated_tokens(content)

    fatal = {
        "missing_yaml_frontmatter",
        "frontmatter_not_mapping",
        "frontmatter_unparseable",
        "missing_name",
        "invalid_name",
        "missing_description",
        "description_too_long",
        "empty_body",
    }
    valid = not any(error in fatal for error in errors)

    return ParsedSkill(
        name=name,
        description=description,
        body=body,
        metadata=metadata,
        valid=valid,
        errors=errors,
        warnings=warnings,
        line_count=line_count,
        estimated_tokens=token_estimate,
        referenced_paths=references,
        has_frontmatter=has_frontmatter,
        name_valid=name_valid,
        description_valid=description_valid,
        parent_name_matches=parent_name_matches,
    )
