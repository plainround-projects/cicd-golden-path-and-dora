# PostgreSQL 16

## What it is

PostgreSQL ("Postgres") is a **relational database server**: a program that keeps data in **tables** (rows and columns) on disk and answers SQL commands ([sql.md](sql.md)) over the network. It guarantees that a **transaction** (a group of changes) happens completely or not at all, and it enforces **constraints** (rules a row must satisfy).

## Why this repository uses it

The platform's event store is one table, `events`. Every DORA metric is computed from it ([dora-metrics.md](dora-metrics.md)). The database also **defends** the data: its constraints repeat the Python validation, so even a buggy writer cannot store an event that cannot be placed on a timeline.

## Where it appears

| Path | Use |
|---|---|
| `docker-compose.yml` | Service `db`: `postgres:16.4-alpine` on `127.0.0.1:55441`. |
| `.github/workflows/ci.yml` | A `services: postgres:` container for the `integration` job. |
| `sql/001_schema.sql` | The `events` table, an index, two views. |
| `sql/002_seed.sql`, `sql/003_queries.sql` | Sample rows and the metric queries in SQL. |
| `src/goldenpath/infrastructure/postgres_store.py` | The adapter ([psycopg.md](psycopg.md)). |
| `tests/integration/` | Tests against the live database, including the SQL queries. |

## How it works underneath

- One server process accepts connections on a port (5432 inside the container) and starts a worker per connection.
- Data lives in a data directory, protected by a write-ahead log. Here the directory is on `tmpfs` (memory), so each run starts empty.
- A **view** is a saved query that behaves like a table. A **unique constraint** also creates an index. An **index** makes some lookups fast.
- A connection string (DSN) looks like `postgresql://user:password@host:port/database`.
- `timestamptz` stores a moment in UTC and shows it in the session's time zone.

## Walkthrough of this repository's use

### The table and its constraints (`sql/001_schema.sql`)

```sql
CREATE TABLE IF NOT EXISTS events (
    id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts      timestamptz NOT NULL,
    service text        NOT NULL,
    type    text        NOT NULL,
    ref     text        NOT NULL,
    detail  text        NOT NULL DEFAULT '',
    CONSTRAINT events_service_format CHECK (service ~ '^[a-z][a-z0-9-]{1,38}$'),
    CONSTRAINT events_type_known     CHECK (type IN ('commit', 'deploy', 'failed', 'recovered')),
    CONSTRAINT events_ref_format     CHECK (ref ~ '^[A-Za-z0-9._:+-]{1,200}$'),
    CONSTRAINT events_deploy_ref     CHECK (type <> 'deploy' OR ref LIKE '%:%'),
    CONSTRAINT events_detail_only_on_failed CHECK (detail = '' OR type = 'failed'),
    CONSTRAINT events_unique UNIQUE (service, type, ref, ts)
);
```
- `GENERATED ALWAYS AS IDENTITY` numbers the rows automatically; `ALWAYS` means nobody can supply a number by mistake.
- Each `CHECK` is a rule the **database** enforces. `~` means "matches this regular expression". The first three repeat the patterns in `domain/events.py`. `events_deploy_ref` says a deploy must contain `:` (`d1:a1+a2`). `events_detail_only_on_failed` says only `failed` events carry a reason.
- `events_unique` makes a **retried pipeline step** harmless: the same `(service, type, ref, ts)` is stored once. The adapter writes `ON CONFLICT DO NOTHING`.
- The `ts` comment states the rule of the whole project: the time comes from the pipeline's clock for every type, never from a developer-set field.

```sql
CREATE INDEX IF NOT EXISTS events_service_type_ts_idx ON events (service, type, ts);
```
Speeds up "all deploy events of one service in time order".

### Views

```sql
CREATE OR REPLACE VIEW deploy_commits AS
SELECT e.service,
       split_part(e.ref, ':', 1) AS deploy_id,
       e.ts                      AS deployed_at,
       nullif(c.commit_ref, '')  AS commit_ref
FROM events e
CROSS JOIN LATERAL unnest(string_to_array(split_part(e.ref, ':', 2), '+')) AS c(commit_ref)
WHERE e.type = 'deploy'
UNION ALL
SELECT e.service, split_part(e.ref, ':', 1), e.ts, NULL
FROM events e
WHERE e.type = 'deploy' AND split_part(e.ref, ':', 2) = '';
```
A deploy event's ref is `d1:a1+a2`. `split_part(ref, ':', 1)` is the part before the colon (`d1`); part 2 is `a1+a2`. `string_to_array(..., '+')` turns that into an array; `unnest` turns an array into rows; `CROSS JOIN LATERAL` lets the right side see the current row of `events`, so one deploy becomes one row per commit. `nullif(x, '')` turns an empty string into `NULL`. The second `SELECT` handles an **empty deployment** (no commits), which gets one row with a `NULL` commit. `UNION ALL` stacks the two results.

```sql
CREATE OR REPLACE VIEW lead_times AS
SELECT d.service, d.commit_ref, c.ts AS committed_at, d.deploy_id, d.deployed_at,
       extract(epoch FROM d.deployed_at - c.ts) / 3600.0 AS hours
FROM deploy_commits d
JOIN events c ON c.service = d.service AND c.type = 'commit' AND c.ref = d.commit_ref;
```
For each commit that reached production, join its `commit` event with the deployment, and compute the difference in hours (`extract(epoch FROM interval)` is seconds).

### The container

`POSTGRES_PASSWORD` has no default in the compose file (`:?`), the port is bound to `127.0.0.1`, and the health check uses TCP because the image's setup server listens only on a socket ([docker-compose.md](docker-compose.md)).

## Try it yourself

```bash
make up
docker compose exec -T db psql -U platform -d events -c '\d events'
```
Shows the columns, the unique constraint, the index and all the `CHECK` rules.

```bash
docker compose exec -T db psql -U platform -d events -c "INSERT INTO events (ts, service, type, ref) VALUES (now(), 'orders', 'deploy', 'no-colon');"
```
Expect `ERROR: new row for relation "events" violates check constraint "events_deploy_ref"`.

```bash
docker compose exec -T db psql -U platform -d events -f /dev/stdin < sql/002_seed.sql
docker compose exec -T db psql -U platform -d events -c "SELECT commit_ref, hours FROM lead_times WHERE service = 'sample-orders' ORDER BY commit_ref;"
```
The first command loads the lesson's sample week; the second shows the lead time of each commit in hours (`a1` is 5 hours: committed 09:00, deployed 14:00).

```bash
docker compose exec -T db psql -U platform -d events -f /dev/stdin < sql/003_queries.sql
```
Runs the three example queries.

## Mistakes people make

- Storing times as text or without a time zone.
- Letting only the application validate; the database enforces the same rules.
- Counting a retried event twice. The unique constraint prevents it.
- Exposing the database port to the network.
- Forgetting that `tmpfs` data disappears at `make down`.

## Check yourself

1. Why do both Python and SQL check the service name? *The database defends the data against any writer.*
2. What does `UNIQUE (service, type, ref, ts)` do for a retried step? *The repeat is ignored, so it is stored once.*
3. What does `unnest` do? *Turns an array into one row per element.*
4. What is a view? *A saved query that behaves like a table.*
5. Why is `ts` `timestamptz`? *It is an exact moment, independent of any time zone.*

## Further reading

- PostgreSQL 16 documentation: https://www.postgresql.org/docs/16/
- Constraints: https://www.postgresql.org/docs/16/ddl-constraints.html
- Views: https://www.postgresql.org/docs/16/sql-createview.html
- `LATERAL`: https://www.postgresql.org/docs/16/queries-table-expressions.html#QUERIES-LATERAL
- `INSERT ... ON CONFLICT`: https://www.postgresql.org/docs/16/sql-insert.html#SQL-ON-CONFLICT
