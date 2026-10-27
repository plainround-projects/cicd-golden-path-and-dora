# psycopg 3

## What it is

PostgreSQL is a separate program ([postgresql.md](postgresql.md)). For a Python program to use it, something must open a network connection to the server, send SQL text, wait for the answer and turn the answer into Python values. That "something" is a **driver**, and the driver for PostgreSQL is **psycopg** (this is version 3, a rewrite of the older `psycopg2`). It is a **third-party library**: code written by other people that you install, as opposed to the standard library that ships with Python.

This repository pins `psycopg==3.3.6` and `psycopg-binary==3.3.6` in the lock files. The second package contains the pre-compiled C part of the driver, so no compiler is needed to install it. The project's `pyproject.toml` asks for `psycopg[binary]>=3.2,<4`: the square brackets request the optional "binary" extra, and the range means version 3.2 up to but not including 4.

Ideas used below:

- A **connection** is one open conversation with the server. Opening one takes time, so some programs keep a pool of them; this service is small and simply opens a short-lived connection per call.
- A **cursor** is an object that runs a statement and holds its result.
- **Parameters**: values passed separately from the SQL text. The driver sends the text and the values on different paths, so a value can never be read as SQL ([sql.md](sql.md)).
- A **transaction** ([postgresql.md](postgresql.md)): psycopg opens one automatically with the first statement. Using the connection in a `with` block commits at the end if no error happened, and rolls back if one did.

## Why this repository uses it

The event store is PostgreSQL ([postgresql.md](postgresql.md)), and `PostgresEventStore` is the adapter that implements the `EventStore` port with psycopg. It is the only module in the platform that imports `psycopg`; an import-linter contract forbids it in the inner layers ([import-linter.md](import-linter.md)). The integration tests use psycopg too, for clean-up.

## Where it appears

| Path | Use |
|---|---|
| `src/goldenpath/infrastructure/postgres_store.py` | `append`, `all`, `clear`. |
| `tests/integration/conftest.py` | The `store` fixture and its clean-up. |
| `tests/integration/test_postgres_store_and_sql.py` | The store, the collector and the SQL queries against a live database. |
| `pyproject.toml` | `dependencies = ["psycopg[binary]>=3.2,<4", "pyyaml>=6"]`. |
| `requirements.lock` | `psycopg==3.3.6` and `psycopg-binary==3.3.6` with hashes. |

## How it works underneath

`psycopg.connect(dsn)` opens a TCP connection to the host and port in the connection string, logs in with the user and password, and returns a `Connection`. `connection.execute(sql, params)` sends the statement and the parameters separately; the server fills in the placeholders. Python values are converted both ways: a `datetime` with a time zone becomes `timestamptz`, `bool` becomes `boolean`, `int` becomes `integer`, and result columns come back as Python values inside **tuples** (fixed-size groups). Errors are exception classes: a failure to connect raises `psycopg.OperationalError`; a row that breaks a `CHECK` rule raises `psycopg.errors.CheckViolation`.

## Walkthrough of this repository's use

```python
"""The `EventStore` port on PostgreSQL (sql/001_schema.sql creates the table)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import psycopg

from goldenpath.domain.events import Event, EventType

_CONNECT_TIMEOUT_SECONDS = 60


class PostgresEventStore:
    """Opens a short-lived connection per call. A duplicate event (same service, type, ref and time) is ignored."""

    def __init__(self, dsn: str) -> None:
        """`dsn` is a libpq connection URI."""
        self._dsn = dsn

    def _connect(self) -> psycopg.Connection[tuple[Any, ...]]:
        return psycopg.connect(self._dsn, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
```

- **Line 1**: docstring. **Line 5**: `Iterable` is the type hint for "something you can loop over"; **line 8**: `import psycopg`. **Line 12**: `_CONNECT_TIMEOUT_SECONDS = 60`, generous on purpose: a loaded laptop can take many seconds to accept a connection.
- **Lines 15 to 20**: the class stores the connection string `dsn` ("data source name": `postgresql://user:password@host:port/db`, built by `Settings.dsn`, [dotenv.md](dotenv.md)). **Lines 22 to 23**, `_connect`: `psycopg.connect(self._dsn, connect_timeout=...)` opens a connection; the return type `psycopg.Connection[tuple[Any, ...]]` says result rows come back as tuples.

```python
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
```

- **Lines 25 to 36**, `append(events)`: `with self._connect() as connection, connection.cursor() as cursor:` opens the connection and a cursor (the object that runs statements) in one `with`. When the block ends normally the work is **committed** (made permanent); if an error leaves it, it is **rolled back** (undone); then the connection is closed. For each event `cursor.execute(statement, values)` sends the statement and the five values separately. `event.type.value` is the text of the enumeration member; `event.ts` is a time-zone-aware `datetime`, which psycopg stores as `timestamptz`. The whole batch is one **transaction**: all events are stored or none are. `inserted += cursor.rowcount` counts only new rows, so the return value is how many events were new.
- **Lines 38 to 42**, `all`: `connection.execute("SELECT ... ORDER BY ts, id").fetchall()` returns a list of tuples. The list comprehension `[Event(ts, service, EventType(kind), ref, detail) for ts, service, kind, ref, detail in rows]` unpacks each tuple into five names and builds a validated `Event` again.
- **Lines 44 to 47**, `clear`: `connection.execute("TRUNCATE events")` (the simulation starts from an empty store).

### The integration tests

```python
"""Integration tests need PostgreSQL from docker-compose.yml: `make up` first."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from goldenpath.infrastructure.postgres_store import PostgresEventStore
from goldenpath.infrastructure.settings import Settings


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings.from_env()


@pytest.fixture
def store(settings: Settings) -> Iterator[PostgresEventStore]:
    """A store whose rows for the test services are removed before and after, so tests never see each other's data."""
    cleanup(settings)
    yield PostgresEventStore(settings.dsn)
    cleanup(settings)


def cleanup(settings: Settings) -> None:
    with psycopg.connect(settings.dsn) as connection:
        connection.execute("DELETE FROM events WHERE service LIKE 'it-%'")
```

`settings` is built once (`scope="session"`); `store` calls `cleanup(settings)` before and after each test, and `cleanup` opens its own connection with `psycopg.connect(settings.dsn)` and runs `DELETE FROM events WHERE service LIKE 'it-%'`, removing every row whose service name starts with `it-` ([pytest.md](pytest.md)).

## Try it yourself

```bash
.venv/bin/python -c "import psycopg; print(psycopg.__version__)"
```
Expect `3.3.6`.

```bash
make up
make test-integration
```
Runs the store, collector and SQL tests against the database. Expect all to pass.

```bash
.venv/bin/goldenpath emit commit orders try-1 --direct --ts 2026-09-01T09:00
.venv/bin/goldenpath emit commit orders try-1 --direct --ts 2026-09-01T09:00
```
Writes straight to the store (`--direct`; the arguments are type, service, ref). The first prints `recorded commit try-1: 1 new`. The second sends the identical event and prints `recorded commit try-1: 0 new`: the unique constraint ignored it. Needs `make up`; clean up with `make simulate` or `make down`. (Not re-run when this note was written, because Docker was out of capacity.)

## Mistakes people make

- Formatting values into SQL with f-strings.
- Forgetting the comma in a one-item tuple.
- One transaction per event, which is slow and not atomic.
- Letting a short connect timeout fail on a busy machine.
- Logging the DSN.

## Check yourself

1. Why are the SQL and the values sent separately? *So values can never be read as SQL.*
2. What does `rowcount` tell `append`? *Whether the row was new (1) or ignored as a duplicate (0).*
3. What happens at the end of `with connection:`? *Commit on success, rollback on an error, then close.*
4. Why is `psycopg` only imported in `postgres_store.py`? *The import-linter contract keeps the inner layers free of it.*
5. What does `TRUNCATE` do? *Deletes every row of the table.*

## Further reading

- psycopg 3: https://www.psycopg.org/psycopg3/docs/ (3.3.6)
- Parameters: https://www.psycopg.org/psycopg3/docs/basic/params.html
- Transactions: https://www.psycopg.org/psycopg3/docs/basic/transactions.html
