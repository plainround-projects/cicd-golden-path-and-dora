"""One command: a new service with a pipeline, a catalog entry and an owner, checked against the contract."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from goldenpath.application.ports import Auditor, Catalog, Repositories, TemplateRenderer
from goldenpath.domain import catalog as catalog_rules
from goldenpath.domain.catalog import CatalogEntry
from goldenpath.domain.errors import DomainError
from goldenpath.domain.rules import Finding


class NonConformingServiceError(DomainError):
    """The generated repository does not keep the golden-path contract; nothing was published."""

    def __init__(self, findings: list[Finding]) -> None:
        """Keep the findings so the caller can print them."""
        super().__init__("the generated repository breaks the contract")
        self.findings = findings


@dataclass(frozen=True, slots=True)
class GeneratedService:
    """What the command produced and where the minutes went."""

    entry: CatalogEntry
    directory: Path
    commit: str
    files: tuple[str, ...]
    timings: dict[str, float] = field(default_factory=dict)


class ServiceGenerator:
    """Validates the owner, renders the template, audits it, registers the catalog entry, publishes the repository."""

    def __init__(
        self,
        renderer: TemplateRenderer,
        catalog: Catalog,
        repositories: Repositories,
        auditor: Auditor,
        platform_ref: str,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """`platform_ref` is the platform commit the service is generated from; it is written into the repository."""
        self._renderer = renderer
        self._catalog = catalog
        self._repositories = repositories
        self._auditor = auditor
        self._platform_ref = platform_ref
        self._clock = clock

    def generate(self, name: str, owner: str, destination: Path, runbook_base: str) -> GeneratedService:
        """Create the service. A person as owner, or a repository that fails the audit, is refused before publishing."""
        timings: dict[str, float] = {}
        started = self._clock()
        entry = catalog_rules.validate(
            CatalogEntry(name, owner, "production", f"{runbook_base}/{name}", "availability 99.9% over 30 days"),
            self._catalog.teams(),
        )
        files = self._renderer.render(
            destination,
            {
                "__NAME__": name,
                "__OWNER__": owner,
                "__RUNBOOK__": entry.runbook,
                "__PLATFORM_REF__": self._platform_ref,
            },
        )
        timings["render"] = self._clock() - started
        findings = self._auditor.audit(destination)
        if findings:
            raise NonConformingServiceError(findings)
        timings["audit"] = self._clock() - started - timings["render"]
        self._catalog.register(entry)
        commit = self._repositories.create(
            destination, name, f"Create {name} from golden path {self._platform_ref[:7]}"
        )
        timings["publish"] = self._clock() - started - timings["render"] - timings["audit"]
        return GeneratedService(entry, destination, commit, tuple(files), timings)
