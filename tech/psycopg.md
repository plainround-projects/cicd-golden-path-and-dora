# psycopg 3

## What it is

psycopg is the Python library ("driver") that talks to PostgreSQL: it opens a network connection, sends SQL, and turns the answers into Python values. Version 3 is a rewrite of `psycopg2`. Pinned: `psycopg==3.3.6` with `psycopg-binary==3.3.6` (precompiled, so no compiler is needed).

## Why this repository uses it

The event store is PostgreSQL ([postgresql.md](postgresql.md)). `PostgresEventStore` is the adapter that implements the `EventStore` port with psycopg. It is the only module in the platform that imports `psycopg`; the import-linter contract forbids it anywhere in the inner layers ([import-linter.md](import-linter.md)).

## Where it appears

| Path | Use |
|---|---|
| `src/goldenpath/infrastructure/postgres_store.py` | `append`, `all`, `clear`. |
| `tests/integration/conftest.py`, `test_postgres_store_and_sql.py` | Live-database tests, cleaning up their rows. |
| `requirements.lock` | The pinned, hashed version. |

## How it works underneath

`psycopg.connect(dsn)` opens a TCP connection and returns a **Connection**. `connection.execute(sql, params)` sends the statement and the parameters **separately**; the server fills the placeholders, so a value can never be read as SQL. Used as `with conn:`, the connection **commits** when the block ends normally, **rolls back** if an exception leaves it, and then closes. A `cursor` is an object that runs statements and holds the result; `cursor.rowcount` says how many rows the last statement changed.

## Walkthrough of this repository's use

```python
def _connect(self) -> psycopg.Connection[tuple[Any, ...]]:
    return psycopg.connect(self._dsn, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
```
A short-lived connection per call. `connect_timeout=60` is generous on purpose: a loaded laptop can take many seconds to accept a connection. The DSN comes from `Settings.dsn` ([dotenv.md](dotenv.md)).

```python
def append(self, events: Iterable[Event]) -> int:
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
```
One transaction for the whole batch: all the events are stored or none are. `ON CONFLICT DO NOTHING` ignores an event that is already there (the table has `UNIQUE (service, type, ref, ts)`), and `rowcount` is 0 for it, so the return value counts only the **new** events. `event.ts` is a timezone-aware `datetime`, which psycopg maps to `timestamptz`.

```python
rows = connection.execute("SELECT ts, service, type, ref, detail FROM events ORDER BY ts, id").fetchall()
return [Event(ts, service, EventType(kind), ref, detail) for ts, service, kind, ref, detail in rows]
```
`fetchall()` returns a list of tuples; each becomes an `Event` again, which validates it a second time. `ORDER BY ts, id` makes the order stable for equal times.

`clear()` runs `TRUNCATE events`: delete every row (the simulation starts from an empty store).

The integration tests use the `store` fixture, which deletes rows whose service starts with `it-` before and after each test.

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
