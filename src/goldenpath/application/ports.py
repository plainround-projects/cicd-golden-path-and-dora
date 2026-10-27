"""What the use cases need from the outside world."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Protocol

from goldenpath.domain.catalog import CatalogEntry
from goldenpath.domain.events import Event
from goldenpath.domain.rules import Finding


class EventSink(Protocol):
    """Anything events can be sent to: the store itself, or the collector in front of it."""

    def append(self, events: Iterable[Event]) -> int:
        """Send events; return how many were new. Sending the same event twice must not duplicate it."""


class EventStore(EventSink, Protocol):
    """Where delivery events are kept and read back."""

    def all(self) -> list[Event]:
        """Every event, oldest first."""

    def clear(self) -> None:
        """Delete every event (the simulation starts from an empty store)."""


class TemplateRenderer(Protocol):
    """Turns the template folder into a new repository folder."""

    def render(self, destination: Path, substitutions: Mapping[str, str]) -> list[str]:
        """Copy the template with placeholders replaced; return the relative paths written."""


class Catalog(Protocol):
    """The service catalog and the registered teams."""

    def teams(self) -> frozenset[str]:
        """The teams that may own a service."""

    def register(self, entry: CatalogEntry) -> None:
        """Add or replace an entry."""

    def entries(self) -> list[CatalogEntry]:
        """Every registered entry."""


class Repositories(Protocol):
    """Creates the Git repository of a new service."""

    def create(self, directory: Path, name: str, message: str) -> str:
        """Initialize, commit everything and publish; return the commit id."""


class Auditor(Protocol):
    """Checks a generated repository against the golden-path contract."""

    def audit(self, directory: Path) -> list[Finding]:
        """Findings, empty when the repository conforms."""
