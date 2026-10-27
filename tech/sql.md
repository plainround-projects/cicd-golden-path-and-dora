# SQL

## What it is

**SQL** (said "S-Q-L" or "sequel") is the language you use to talk to a relational database ([postgresql.md](postgresql.md)). You do not tell the database *how* to do something step by step; you describe *what* you want, and the database works out how.

SQL statements come in three families:

- **Defining structure** (DDL, data-definition language): `CREATE TABLE`, `CREATE INDEX`.
- **Changing data** (DML, data-manipulation language): `INSERT` adds rows, `DELETE` removes rows, `UPDATE` changes them.
- **Reading data**: `SELECT`.

Rules of the language: a statement ends with a semicolon. Keywords are not case-sensitive (this project writes them in capitals). Text values are written in single quotes: `'sample-orders'`. `--` starts a comment to the end of the line. `NULL` means "unknown or absent": it is not equal to anything, not even to itself.

This repository uses the PostgreSQL 16 dialect.

## Why this repository uses it

The lesson says the four delivery metrics come from events alone. SQL computes them a second way: the Python domain computes them from `Event` objects, and the SQL in `sql/003_queries.sql` computes them from the table. A test checks that both produce the same numbers on the lesson's sample data.

## Where it appears

| Path | What it does |
|---|---|
| `sql/001_schema.sql` | DDL: the table `events`, an index, the views `deploy_commits` and `lead_times` ([postgresql.md](postgresql.md) explains it line by line). |
| `sql/002_seed.sql` | DML: replaces the lesson's sample events. |
| `sql/003_queries.sql` | Step 4 and step 5 of the lesson as queries. |
| `src/goldenpath/infrastructure/postgres_store.py` | `INSERT ... ON CONFLICT DO NOTHING`, `SELECT`, `TRUNCATE`. |
| `tests/integration/test_postgres_store_and_sql.py` | Runs the queries and compares them with Python. |

## How it works underneath

The database reads the text, checks it, and **plans** it: decides which indexes to use and in what order to do things. `EXPLAIN` in front of a query shows the plan.

A `SELECT` is read in this logical order, whatever order you write the parts in: `FROM` (which table), `WHERE` (keep only rows that satisfy a condition), `GROUP BY` (collapse rows into groups so counts and totals can be made per group), the select list (which columns or calculations to output), `ORDER BY` (sort), `LIMIT` (keep only the first N rows).

A **placeholder** is a hole in a statement for a value that is sent separately. Python's database library writes it as `%s`. Because the value travels separately from the statement text, it can never be mistaken for SQL. Gluing values into SQL text instead is the classic security hole called **SQL injection**.

## Walkthrough of this repository's use

### `sql/002_seed.sql`: the lesson's sample week

```sql
-- DML: the lesson's sample week, for two services, so the queries in 003_queries.sql have the numbers the lesson expects.
-- The services are named sample-orders and sample-billing so the sample never mixes with the services the demos create.
-- Re-running is safe: the sample rows are replaced.
DELETE FROM events WHERE service IN ('sample-orders', 'sample-billing');

INSERT INTO events (ts, service, type, ref, detail) VALUES
    ('2026-09-01 09:00+00', 'sample-orders', 'commit',    'a1', ''),
    ('2026-09-01 10:30+00', 'sample-orders', 'commit',    'a2', ''),
    ('2026-09-01 14:00+00', 'sample-orders', 'deploy',    'd1:a1+a2', ''),
    ('2026-09-02 11:00+00', 'sample-orders', 'commit',    'a3', ''),
    ('2026-09-02 15:00+00', 'sample-orders', 'deploy',    'd2:a3', ''),
    ('2026-09-02 15:10+00', 'sample-orders', 'failed',    'd2', 'health-check'),
```

- **Lines 1 to 3** (comments): the sample for two services named `sample-orders` and `sample-billing`, so the sample never mixes with the services the demos create; re-running replaces the rows.
- **Line 4**: `DELETE FROM events WHERE service IN ('sample-orders', 'sample-billing');` removes the earlier sample rows (`IN (...)` matches any listed value). Deleting first makes the script **idempotent**.
- **Lines 6 to 19**: `INSERT INTO events (ts, service, type, ref, detail) VALUES (...), (...);` adds all rows in one statement. Each parenthesis is a row in the column order given; `'2026-09-01 09:00+00'` is a moment with an offset from UTC of zero. The rows are the same events as `data/events-sample.csv`; the two `failed` events carry the detail `health-check`.

### `sql/003_queries.sql`

```sql
-- The queries the project's README and tests run. Each starts with a one-line comment on what it shows.
-- Run them with: docker compose exec -T db psql -U platform -d events -f /dev/stdin < sql/003_queries.sql

-- Step 4: every production deployment of a service with the commits it contained.
SELECT service, deploy_id, deployed_at, coalesce(string_agg(commit_ref, ', ' ORDER BY commit_ref), '(none)') AS commits
FROM deploy_commits
WHERE service = 'sample-orders'
GROUP BY service, deploy_id, deployed_at
ORDER BY deployed_at;

-- Step 5: trace one lead time to its two events: the commit event and the deployment event.
SELECT l.commit_ref, l.committed_at, l.deploy_id, l.deployed_at, round(l.hours::numeric, 1) AS hours
FROM lead_times l
WHERE l.service = 'sample-orders' AND l.commit_ref = 'a5';
```

- **Lines 4 to 9**: *every production deployment of a service with the commits it contained.* `SELECT service, deploy_id, deployed_at, coalesce(string_agg(commit_ref, ', ' ORDER BY commit_ref), '(none)') AS commits FROM deploy_commits WHERE service = 'sample-orders' GROUP BY service, deploy_id, deployed_at ORDER BY deployed_at;`. `GROUP BY` collapses the rows of each deployment into one; `string_agg(x, ', ' ORDER BY x)` joins the commits into one text; `coalesce(a, b)` gives `a` or, when it is `NULL`, `b` (so an empty deployment shows `(none)`); `AS commits` names the output column.
- **Lines 11 to 14**: *trace one lead time to its two events.* `SELECT l.commit_ref, l.committed_at, l.deploy_id, l.deployed_at, round(l.hours::numeric, 1) AS hours FROM lead_times l WHERE l.service = 'sample-orders' AND l.commit_ref = 'a5';`. `l` is a short alias for the view; `::numeric` converts the type so `round(x, 1)` can round to one decimal.

```sql
-- Step 5: the four metrics per service, in SQL. The window is the data's own: midnight of the first day, whole weeks.
-- Remove the sample filter to measure every service. The numbers must equal `make dora-sample` (the Python domain).
WITH scope AS (
    SELECT * FROM events WHERE service LIKE 'sample-%'
), window_ AS (
    SELECT date_trunc('day', min(ts)) AS start_at,
           ceil(extract(epoch FROM max(ts) - date_trunc('day', min(ts))) / (7 * 86400.0)) AS weeks
    FROM scope
), real_deploys AS (
    SELECT DISTINCT d.service, d.deploy_id, d.deployed_at
    FROM deploy_commits d, window_ w
    WHERE d.commit_ref IS NOT NULL AND d.deployed_at >= w.start_at AND d.deployed_at < w.start_at + w.weeks * interval '7 days'
      AND d.service LIKE 'sample-%'
), failures AS (
    SELECT f.service, f.ref AS deploy_id, f.ts AS failed_at,
           (SELECT min(r.ts) FROM events r WHERE r.service = f.service AND r.type = 'recovered' AND r.ref = f.ref AND r.ts >= f.ts) AS recovered_at
    FROM events f WHERE f.type = 'failed' AND f.service LIKE 'sample-%'
)
SELECT d.service,
       round(count(*)::numeric / max(w.weeks), 1)                                             AS deploys_per_week,
       round((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY l.hours)
              FROM lead_times l JOIN real_deploys x USING (service, deploy_id) WHERE l.service = d.service)::numeric, 1) AS median_lead_time_hours,
       round(100.0 * count(DISTINCT f.deploy_id) / count(*))                                  AS change_fail_rate_percent,
       round((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM f2.recovered_at - f2.failed_at) / 60)
              FROM failures f2 WHERE f2.service = d.service AND f2.recovered_at IS NOT NULL)::numeric) AS median_recovery_minutes
FROM real_deploys d
CROSS JOIN window_ w
LEFT JOIN failures f ON f.service = d.service AND f.deploy_id = d.deploy_id
GROUP BY d.service
ORDER BY d.service;
```

*The four metrics per service, in SQL.* A `WITH name AS (...)` clause (a CTE) names a sub-query so later parts can use it.

- **Lines 18 to 20**, `scope`: the sample services only (`service LIKE 'sample-%'`, where `%` stands for any characters).
- **Lines 20 to 23**, `window_`: `date_trunc('day', min(ts))` is midnight of the first day; `ceil(extract(epoch FROM max(ts) - date_trunc('day', min(ts))) / (7 * 86400.0))` is the number of whole weeks needed, rounding up (`86400` seconds in a day). The Python function `window_of` does the same.
- **Lines 24 to 28**, `real_deploys`: `SELECT DISTINCT` (no repeated rows) deployments that contain a commit and fall inside the window: `d.deployed_at >= w.start_at AND d.deployed_at < w.start_at + w.weeks * interval '7 days'`.
- **Lines 29 to 33**, `failures`: each `failed` event with `(SELECT min(r.ts) FROM events r WHERE ... r.type = 'recovered' AND r.ref = f.ref AND r.ts >= f.ts) AS recovered_at`: a sub-query that refers to the outer row `f` finds the earliest recovery for the same deployment at or after the failure.
- **Lines 34 to 45**, the result: `round(count(*)::numeric / max(w.weeks), 1)` deployments per week; `percentile_cont(0.5) WITHIN GROUP (ORDER BY l.hours)` is the **median** lead time (`percentile_cont` computes a percentile; 0.5 is the middle); `round(100.0 * count(DISTINCT f.deploy_id) / count(*))` the change fail rate in percent; the median of `extract(epoch FROM f2.recovered_at - f2.failed_at) / 60` the recovery time in minutes. `LEFT JOIN failures f ON ...` keeps deployments that never failed (their failure columns are `NULL`). `GROUP BY d.service ORDER BY d.service`. The comment on lines 16 and 17 says the numbers must equal `make dora-sample`.

### SQL written inside Python

<!-- fmt:off -->
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
<!-- fmt:on -->

- **Lines 30 to 34**: `cursor.execute("INSERT INTO events (ts, service, type, ref, detail) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", (values...))`. Five `%s` placeholders and a tuple of five values, sent separately so a value can never be read as SQL. `ON CONFLICT DO NOTHING` skips a row that would break the unique constraint (a repeated event). **Line 35**: `inserted += cursor.rowcount` adds 1 if a row was really added, 0 if skipped.
- **Line 41**: `SELECT ts, service, type, ref, detail FROM events ORDER BY ts, id` reads everything in time order (`id` breaks ties). **Line 47**: `TRUNCATE events` deletes every row at once.

## Try it yourself

```bash
make up
docker compose exec -T db psql -U platform -d events -f /dev/stdin < sql/002_seed.sql
docker compose exec -T db psql -U platform -d events -f /dev/stdin < sql/003_queries.sql
```
The seed file holds the lesson's sample week for two services (`sample-orders` and `sample-billing`), and the last query prints one row per sample service.

```bash
make dora-sample
```
The Python numbers for the same data (`--csv data/events-sample.csv`). They must equal the SQL ones.

```bash
make test-integration
```
Includes the test that compares SQL with Python.

## Mistakes people make

- A median computed as an average.
- Forgetting `LEFT JOIN` and losing the deployments that never failed.
- Dividing integers: `count(*) / 7` truncates. Cast with `::numeric`.
- Building SQL by gluing text; here the adapter uses placeholders.
- Using `NOT IN` with possible `NULL`s.

## Check yourself

1. What does `coalesce` do? *Returns the first non-`NULL` argument.*
2. What does `percentile_cont(0.5)` compute? *The median.*
3. What does a CTE give you? *A named sub-query to build the answer step by step.*
4. Why `LEFT JOIN failures`? *To keep deployments that never failed.*
5. Why compute the metrics in both Python and SQL? *To prove the definitions agree.*

## Further reading

- PostgreSQL 16 SQL commands: https://www.postgresql.org/docs/16/sql-commands.html
- `WITH` queries: https://www.postgresql.org/docs/16/queries-with.html
- Ordered-set aggregates (`percentile_cont`): https://www.postgresql.org/docs/16/functions-aggregate.html#FUNCTIONS-ORDEREDSET-TABLE
- Date and time functions: https://www.postgresql.org/docs/16/functions-datetime.html
