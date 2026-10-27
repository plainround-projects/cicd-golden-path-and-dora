"""The catalog as files: `catalog/teams.yaml` (committed) and one YAML file per registered service (generated state)."""

from __future__ import annotations

from pathlib import Path

import yaml

from goldenpath.domain.catalog import CatalogEntry, from_mapping


class FileCatalog:
    """Registered teams come from a committed file; registered services are written under `entities/`."""

    def __init__(self, teams_file: Path, entities_dir: Path) -> None:
        """Both paths may be missing until first use."""
        self._teams_file = teams_file
        self._entities_dir = entities_dir

    def teams(self) -> frozenset[str]:
        """The teams that may own a service."""
        data = yaml.safe_load(self._teams_file.read_text()) or {}
        return frozenset(str(team) for team in data.get("teams", []))

    def register(self, entry: CatalogEntry) -> None:
        """Write (or replace) the entry's file."""
        self._entities_dir.mkdir(parents=True, exist_ok=True)
        (self._entities_dir / f"{entry.name}.yaml").write_text(yaml.safe_dump(entry.as_mapping(), sort_keys=False))

    def entries(self) -> list[CatalogEntry]:
        """Every registered entry, by name."""
        if not self._entities_dir.exists():
            return []
        return [from_mapping(yaml.safe_load(path.read_text())) for path in sorted(self._entities_dir.glob("*.yaml"))]
