"""The `EventStore` port on PostgreSQL (sql/001_schema.sql creates the table)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import psycopg

from goldenpath.domain.events import Event, EventType

_CONNECT_TIMEOUT_SECONDS = 5


class PostgresEventStore:
    """Opens a short-lived connection per call. A duplicate event (same service, type, ref and time) is ignored."""

    def __init__(self, dsn: str) -> None:
        """`dsn` is a libpq connection URI."""
        self._dsn = dsn

    def _connect(self) -> psycopg.Connection[tuple[Any, ...]]:
        return psycopg.connect(self._dsn, connect_timeout=_CONNECT_TIMEOUT_SECONDS)

    def append(self, events: Iterable[Event]) -> int:
        """Insert events; return how many were new."""
        inserted = 0
        with self._connect() as connection, connection.cursor() as cursor:
            for event in events:
                cursor.execute(
                    "INSERT INTO events (ts, service, type, ref, detail) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (event.ts, event.service, event.type.value, event.ref, event.detail),
                )
                inserted += cursor.rowcount
        return inserted

    def all(self) -> list[Event]:
        """Every event, oldest first."""
        with self._connect() as connection:
            rows = connection.execute("SELECT ts, service, type, ref, detail FROM events ORDER BY ts, id").fetchall()
        return [Event(ts, service, EventType(kind), ref, detail) for ts, service, kind, ref, detail in rows]

    def clear(self) -> None:
        """Delete every event."""
        with self._connect() as connection:
            connection.execute("TRUNCATE events")
