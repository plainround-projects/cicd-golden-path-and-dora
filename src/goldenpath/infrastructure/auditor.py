"""Audit a generated repository against the golden-path contract: reads its files, applies the domain's rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from goldenpath.application.ports import Catalog
from goldenpath.domain import catalog as catalog_rules
from goldenpath.domain import rules
from goldenpath.domain.errors import InvalidCatalogEntryError
from goldenpath.domain.rules import Finding

_SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}


def read_text_files(directory: Path) -> dict[str, str]:
    """Every text file under `directory` as `{relative path: text}`; binary files and VCS folders are skipped."""
    files: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if path.is_dir() or _SKIP_DIRS & set(relative.parts):
            continue
        try:
            files[relative.as_posix()] = path.read_text()
        except UnicodeDecodeError:
            continue
    return files


def load_workflow(text: str) -> dict[str, Any]:
    """Parse a workflow. PyYAML reads the key `on` as the boolean True; put it back under "on"."""
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise ValueError("a workflow must be a mapping")
    if True in document:
        document["on"] = document.pop(True)
    return document


class RepositoryAuditor:
    """Implements the `Auditor` port for a repository on disk."""

    def __init__(self, catalog: Catalog) -> None:
        """The catalog supplies the list of registered teams for the owner check."""
        self._catalog = catalog

    def audit(self, directory: Path) -> list[Finding]:
        """Findings, empty when the repository conforms."""
        files = read_text_files(directory)
        findings: list[Finding] = []
        workflows = sorted(
            path for path in files if path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))
        )
        if not workflows:
            findings.append(Finding("GP-NOWORKFLOW", "required checks", "the repository has no workflow"))
        for path in workflows:
            findings.extend(rules.check_workflow(load_workflow(files[path])))
        if "protection.json" in files:
            findings.extend(rules.check_protection(json.loads(files["protection.json"])))
        else:
            findings.append(Finding("GP-CHECKS", "required checks", "protection.json is missing"))
        findings.extend(self._catalog_findings(files))
        findings.extend(rules.scan_for_credentials(files))
        findings.extend(rules.unreplaced_placeholders(files))
        return findings

    def _catalog_findings(self, files: dict[str, str]) -> list[Finding]:
        if "catalog-info.yaml" not in files:
            return [Finding("GP-CATALOG", "catalog", "catalog-info.yaml is missing")]
        try:
            catalog_rules.validate(
                catalog_rules.from_mapping(yaml.safe_load(files["catalog-info.yaml"])), self._catalog.teams()
            )
        except InvalidCatalogEntryError as error:
            return [Finding("GP-CATALOG", "catalog", str(error))]
        return []
