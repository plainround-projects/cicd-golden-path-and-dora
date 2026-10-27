"""The golden-path contract as checks: what a generated repository must keep, whatever a team changes.

Three things cannot be turned off, each with the reason that gets it a defender when someone finds it annoying:

1. Required checks on `main`: a red `main` stops everyone, so it is a shared problem.
2. Signed artifacts, verified before deploy: we must know that what runs is what CI built.
3. Short-lived deploy credentials from the CI identity (OIDC): a stored key leaks, and a leaked key lasts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

REQUIRED_CHECKS: Final = ("lint", "test", "release")
_PINNED: Final = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
_MOVING: Final = re.compile(r"(:latest\b|@(main|master|latest)\b)")
_CREDENTIAL_PATTERNS: Final = {
    "an AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "an AWS secret access key": re.compile(r"aws_secret_access_key\s*[:=]\s*\S+", re.IGNORECASE),
    "a private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "a GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "a stored cloud or registry secret in the workflow": re.compile(
        r"secrets\.[A-Z0-9_]*(ACCESS_KEY|SECRET_KEY|PRIVATE_KEY|PASSWORD|CLIENT_SECRET|SERVICE_ACCOUNT)[A-Z0-9_]*"
    ),
}


@dataclass(frozen=True, slots=True)
class Finding:
    """One violation of the contract: a stable code, the control it breaks, and what to change."""

    code: str
    control: str
    message: str


def _steps(document: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    return [(job_id, step) for job_id, job in document.get("jobs", {}).items() for step in job.get("steps", [])]


def check_workflow(document: Mapping[str, Any]) -> list[Finding]:
    """Check a parsed workflow against the three non-negotiables and the pinning rule."""
    findings: list[Finding] = []
    steps = _steps(document)
    commands = "\n".join(str(step.get("run", "")) for _, step in steps)
    for job_id, step in steps:
        used = step.get("uses")
        if used and not used.startswith("./") and not _PINNED.match(used):
            findings.append(
                Finding("GP-PIN", "supply chain", f"{used!r} in job {job_id!r} is not pinned to a full commit SHA")
            )
        if _MOVING.search(str(used or "") + str(step.get("run", ""))):
            findings.append(
                Finding("GP-MOVING", "supply chain", f"job {job_id!r} uses a moving name (latest, main or master)")
            )
    if "make sign" not in commands and "cosign sign" not in commands:
        findings.append(Finding("GP-SIGN", "signed artifacts", "no step signs the artifact"))
    if "make verify" not in commands and "cosign verify" not in commands:
        findings.append(Finding("GP-VERIFY", "signed artifacts", "no step verifies the signature before deploy"))
    release_permissions = {}
    for job in document.get("jobs", {}).values():
        if "release" in str(job.get("name", "")) or any(
            "make release" in str(s.get("run", "")) for s in job.get("steps", [])
        ):
            release_permissions = job.get("permissions", {})
    if release_permissions.get("id-token") != "write":
        findings.append(
            Finding(
                "GP-OIDC",
                "short-lived credentials",
                "the release job does not ask for an identity token (id-token: write)",
            )
        )
    top = document.get("permissions")
    if not isinstance(top, dict) or top.get("contents") != "read" or "id-token" in top:
        findings.append(
            Finding(
                "GP-PERMS",
                "short-lived credentials",
                "top-level permissions must be contents: read only; grant id-token per job",
            )
        )
    return findings


def check_protection(payload: Mapping[str, Any]) -> list[Finding]:
    """The branch-protection payload must require the checks, strictly, for administrators too."""
    findings = []
    checks = payload.get("required_status_checks") or {}
    missing = [name for name in REQUIRED_CHECKS if name not in checks.get("contexts", [])]
    if missing:
        findings.append(Finding("GP-CHECKS", "required checks", f"required checks missing: {', '.join(missing)}"))
    if not checks.get("strict"):
        findings.append(
            Finding("GP-STRICT", "required checks", "the branch must be required to be up to date (strict)")
        )
    if not payload.get("enforce_admins"):
        findings.append(Finding("GP-ADMINS", "required checks", "the rules must apply to administrators too"))
    if not payload.get("required_pull_request_reviews"):
        findings.append(Finding("GP-PR", "required checks", "a pull request must be required before merging"))
    return findings


def scan_for_credentials(files: Mapping[str, str]) -> list[Finding]:
    """Search text files for what a long-lived credential looks like."""
    findings = []
    for path, text in sorted(files.items()):
        for what, pattern in _CREDENTIAL_PATTERNS.items():
            if pattern.search(text):
                findings.append(Finding("GP-SECRET", "short-lived credentials", f"{path} contains {what}"))
    return findings


def unreplaced_placeholders(files: Mapping[str, str]) -> list[Finding]:
    """A generated repository must not still hold a `__NAME__`-style placeholder."""
    return [
        Finding("GP-PLACEHOLDER", "template", f"{path} still contains a placeholder")
        for path, text in sorted(files.items())
        if re.search(r"__[A-Z_]+__", text)
    ]


def summarize(findings: Sequence[Finding]) -> str:
    """One line per finding, or `conforms` when there are none."""
    if not findings:
        return "conforms to the golden path contract"
    return "\n".join(f"{finding.code}  [{finding.control}]  {finding.message}" for finding in findings)
