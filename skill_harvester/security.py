from __future__ import annotations

import re
from dataclasses import dataclass

from skill_harvester.models import SecurityFinding, SecurityResult


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    severity: str
    message: str
    pattern: re.Pattern[str]


RULES: tuple[Rule, ...] = (
    Rule("pipe_remote_shell", "critical", "Downloads remote content and pipes it into a shell.", re.compile(r"(?:curl|wget)[^\n|]{0,300}\|\s*(?:sudo\s+)?(?:ba)?sh\b", re.I)),
    Rule("destructive_root_delete", "critical", "Contains a potentially destructive recursive delete.", re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(?:/|~|\$HOME)(?:\s|$)", re.I)),
    Rule("decoded_shell_execution", "critical", "Decodes or evaluates content before shell execution.", re.compile(r"(?:base64\s+(?:--decode|-d)|eval\s*\().{0,200}(?:\|\s*(?:ba)?sh|exec)", re.I | re.S)),
    Rule("credential_exfiltration", "critical", "May transmit tokens, keys, or credentials to a remote endpoint.", re.compile(r"(?:curl|wget|requests\.(?:post|put)|fetch\().{0,400}(?:GITHUB_TOKEN|API_KEY|SECRET|PASSWORD|\.ssh|credentials)", re.I | re.S)),
    Rule("sensitive_file_access", "high", "References sensitive credential or key files.", re.compile(r"(?:~?/)?\.(?:ssh|aws|config/gcloud)|credentials|id_rsa|id_ed25519|\.npmrc|\.pypirc", re.I)),
    Rule("privilege_escalation", "high", "Requests elevated privileges.", re.compile(r"\bsudo\b|\bsu\s+-?\b", re.I)),
    Rule("environment_dump", "high", "May enumerate environment variables, which can expose secrets.", re.compile(r"(?:^|[;&|]\s*)(?:env|printenv|set)\s*(?:$|[;&|])", re.I | re.M)),
    Rule("global_shell_configuration", "medium", "Modifies global shell, Git, or system configuration.", re.compile(r"(?:git\s+config\s+--global|>>?\s*~?/\.(?:bashrc|zshrc|profile)|/etc/)", re.I)),
    Rule("unbounded_permissions", "medium", "Uses broadly permissive file permissions.", re.compile(r"\bchmod\s+(?:-R\s+)?777\b", re.I)),
    Rule("unpinned_package_install", "low", "Installs packages without an obvious pinned version.", re.compile(r"\b(?:pip(?:3)?\s+install|npm\s+install\s+-g|apt(?:-get)?\s+install)\b(?![^\n]{0,120}(?:==|@[0-9]|=[0-9]))", re.I)),
    Rule("network_download", "low", "Uses a network download command; inspect before execution.", re.compile(r"\b(?:curl|wget)\b", re.I)),
)

_SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def scan_security(content: str) -> SecurityResult:
    findings: list[SecurityFinding] = []
    highest = "none"
    for rule in RULES:
        matches = []
        for match in rule.pattern.finditer(content):
            snippet = re.sub(r"\s+", " ", match.group(0)).strip()
            matches.append(snippet[:240])
            if len(matches) >= 3:
                break
        if matches:
            findings.append(SecurityFinding(rule.rule_id, rule.severity, rule.message, matches))
            if _SEVERITY_RANK[rule.severity] > _SEVERITY_RANK[highest]:
                highest = rule.severity
    return SecurityResult(risk_level=highest, findings=findings)
