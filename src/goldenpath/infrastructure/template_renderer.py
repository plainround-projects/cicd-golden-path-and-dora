"""Render the template folder into a new repository folder, replacing placeholders in text files."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path

_SKIP = {"__pycache__", ".DS_Store"}


class FileTemplateRenderer:
    """Copies `template/` and replaces `__NAME__`-style placeholders. File modes are kept (scripts stay executable)."""

    def __init__(self, template: Path) -> None:
        """`template` is the folder holding the golden path."""
        self._template = template

    def render(self, destination: Path, substitutions: Mapping[str, str]) -> list[str]:
        """Write the template to `destination` (which must not exist); return the relative paths written."""
        if destination.exists():
            raise FileExistsError(f"{destination} already exists")
        written = []
        for source in sorted(self._template.rglob("*")):
            relative = source.relative_to(self._template)
            if source.is_dir() or _SKIP & set(relative.parts):
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            text = target.read_text()
            for placeholder, value in substitutions.items():
                text = text.replace(placeholder, value)
            target.write_text(text)
            written.append(relative.as_posix())
        return written
