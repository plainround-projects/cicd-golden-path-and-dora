"""Events in a CSV file: `ts,service,type,ref[,detail]`, the format of the lesson's sample."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from goldenpath.domain.events import Event, EventType, parse_timestamp


class CsvEventStore:
    """An `EventStore` on one CSV file. Reads are whole-file; fine for a sample and for tests."""

    def __init__(self, path: Path) -> None:
        """`path` is created on the first append."""
        self._path = path

    def append(self, events: Iterable[Event]) -> int:
        """Add events that are not already in the file."""
        existing = set(self.all())
        new = [event for event in events if event not in existing]
        is_new_file = not self._path.exists() or self._path.stat().st_size == 0
        with self._path.open("a", newline="") as handle:
            writer = csv.writer(handle)
            if is_new_file:
                writer.writerow(["ts", "service", "type", "ref", "detail"])
            for event in new:
                writer.writerow(
                    [event.ts.strftime("%Y-%m-%dT%H:%M:%S"), event.service, event.type.value, event.ref, event.detail]
                )
        return len(new)

    def all(self) -> list[Event]:
        """Every event, oldest first."""
        if not self._path.exists():
            return []
        with self._path.open(newline="") as handle:
            events = [
                Event(
                    parse_timestamp(row["ts"]),
                    row["service"],
                    EventType(row["type"]),
                    row["ref"],
                    row.get("detail") or "",
                )
                for row in csv.DictReader(handle)
            ]
        return sorted(events, key=lambda event: event.ts)

    def clear(self) -> None:
        """Delete the file."""
        self._path.unlink(missing_ok=True)
