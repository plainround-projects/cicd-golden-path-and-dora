"""The service catalog entry every generated service gets, and the rule that its owner is a team."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, Final

from goldenpath.domain.errors import InvalidCatalogEntryError

LIFECYCLES: Final = ("experimental", "production", "deprecated")
_NAME: Final = re.compile(r"^[a-z][a-z0-9-]{1,38}$")
_TEAM: Final = re.compile(r"^team-[a-z][a-z0-9-]{1,30}$")


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """`catalog-info.yaml`: who owns the service, where its runbook is and what it promises."""

    name: str
    owner: str
    lifecycle: str
    runbook: str
    slo: str

    def as_mapping(self) -> dict[str, str]:
        """The entry as the mapping written to YAML."""
        return {
            "name": self.name,
            "owner": self.owner,
            "lifecycle": self.lifecycle,
            "runbook": self.runbook,
            "slo": self.slo,
        }


def validate(entry: CatalogEntry, teams: Collection[str]) -> CatalogEntry:
    """Return the entry when it keeps the contract; raise `InvalidCatalogEntryError` naming the first broken rule."""
    if not _NAME.match(entry.name):
        raise InvalidCatalogEntryError(f"name must be 2-39 characters of a-z, 0-9 and '-', got {entry.name!r}")
    if not _TEAM.match(entry.owner):
        raise InvalidCatalogEntryError(f"owner must be a team named team-<name>, not a person: {entry.owner!r}")
    if entry.owner not in teams:
        raise InvalidCatalogEntryError(f"owner {entry.owner!r} is not a registered team ({', '.join(sorted(teams))})")
    if entry.lifecycle not in LIFECYCLES:
        raise InvalidCatalogEntryError(f"lifecycle must be one of {', '.join(LIFECYCLES)}, got {entry.lifecycle!r}")
    if not entry.runbook.startswith("https://"):
        raise InvalidCatalogEntryError("runbook must be an https:// link")
    if not entry.slo.strip():
        raise InvalidCatalogEntryError("slo must say what the service promises")
    return entry


def from_mapping(data: Mapping[str, Any]) -> CatalogEntry:
    """Build an entry from parsed YAML; a missing key is an error that names it."""
    try:
        return CatalogEntry(**{key: str(data[key]) for key in ("name", "owner", "lifecycle", "runbook", "slo")})
    except KeyError as missing:
        raise InvalidCatalogEntryError(f"catalog entry has no {missing.args[0]!r}") from None
