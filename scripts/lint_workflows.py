"""Lint the platform's own workflow and the template's against the golden-path rules (`make lint` runs this)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from goldenpath.domain import rules
from goldenpath.infrastructure.auditor import load_workflow

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Print every finding; exit 1 when there is one."""
    findings = []
    template_workflow = ROOT / "template" / ".github" / "workflows" / "ci.yml"
    findings += [
        (template_workflow, finding) for finding in rules.check_workflow(load_workflow(template_workflow.read_text()))
    ]
    protection = ROOT / "template" / "protection.json"
    findings += [(protection, finding) for finding in rules.check_protection(json.loads(protection.read_text()))]
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        document = load_workflow(path.read_text())
        findings += [
            (path, finding)
            for finding in rules.check_workflow(document)
            if finding.code in {"GP-PIN", "GP-MOVING", "GP-PERMS"}
        ]
    for path, finding in findings:
        print(f"{path.relative_to(ROOT)}: {finding.code} {finding.message}")
    print("workflows ok" if not findings else f"{len(findings)} problem(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
