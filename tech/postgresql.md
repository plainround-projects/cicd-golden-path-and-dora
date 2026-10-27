# PostgreSQL 16

## What it is

Programs often need to store information so that it survives when the program stops, and so that many programs can read and change it safely at once. A **database** is a program that does exactly that. **PostgreSQL** (people say "Postgres") is a database of the *relational* kind: it keeps information in **tables**.

A **table** is a grid. Each **column** has a name and a kind of value (text, whole number, true/false, date and time). Each **row** is one record. A table called `events` has one row for each delivery event, with columns such as `service`, `type` and `ts`. You talk to the database in a language called SQL ([sql.md](sql.md)).

PostgreSQL is a **server**: a program that keeps running and waits for other programs (called *clients*) to connect to it over the network. Each client says "I am this user, for this database" and then sends commands. The server listens on a **port**, a number from 1 to 65535 that identifies the door; PostgreSQL's usual port is 5432. The address a client uses is a **connection string**: `postgresql://user:password@host:port/database`.

Four more ideas you will see:

- A **transaction** is a group of changes that either all happen or none do. If something fails halfway, PostgreSQL undoes the part already done (a **rollback**). When the group is finished the client says **commit** and the changes become permanent and visible to others.
- A **constraint** is a rule the database itself enforces on a table, such as "this column can never be empty" or "this number cannot be negative". No program, however buggy, can put a violating row in.
- An **index** is a sorted side-structure that makes some searches fast, like the index of a book. A **partial index** covers only the rows that match a condition, so it stays small.
- A **primary key** is a column (or columns) whose value identifies each row uniquely.

## Why this repository uses it

The platform's event store is one table, `events`, and every DORA metric is computed from it ([dora-metrics.md](dora-metrics.md)). The database also **defends** the data: its constraints repeat the Python validation, so even a buggy writer cannot store an event that cannot be placed on a timeline.

## Where it appears

| Path | Use |
|---|---|
| `docker-compose.yml` | Service `db`: `postgres:16.4-alpine` on `127.0.0.1:55441` ([docker-compose.md](docker-compose.md)). |
| `.github/workflows/ci.yml` | A `services: postgres:` container for the `integration` job ([github-actions.md](github-actions.md)). |
| `sql/001_schema.sql` | The `events` table, an index and two views. |
| `sql/002_seed.sql`, `sql/003_queries.sql` | The lesson's sample events and the metric queries ([sql.md](sql.md)). |
| `src/goldenpath/infrastructure/postgres_store.py` | The Python adapter ([psycopg.md](psycopg.md)). |
| `tests/integration/` | Tests against the live database. |

## How it works underneath

- One server process listens on the port. For each connected client it starts a worker process.
- The data lives in a **data directory** on disk. To survive a crash, every change is first written to a **write-ahead log**; after a crash the server replays it. In this repository the data directory is in memory (`tmpfs`), so everything disappears when the container is removed, which is exactly what a throw-away test database should do.
- PostgreSQL has many column types. This repository uses `bigint` (a large whole number), `integer`, `text` (any length), `boolean`, and `timestamptz`, a moment in time stored in UTC and shown in whatever time zone the session uses.
- **Isolation**: while a transaction is open, other clients do not see its changes until it commits.
- The official Docker image sets up a database and user on first start from the environment variables `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD`. During that set-up it runs a temporary server that listens only on a Unix socket (a local file used like a network connection); only afterwards does the real server start on TCP. A readiness check must therefore use TCP, as the health check does.
- The tools in the image: `psql` is the interactive client (it can also read commands from a file), and `pg_isready` asks a server whether it accepts connections.

## Walkthrough of this repository's use

### The table: `sql/001_schema.sql`

```sql
-- DDL: the delivery event store. Applied by `make db`. One table, written only through the collector (or the simulation),
-- plus two views that turn deploy refs into rows so the metrics can be asked for in SQL as well as in Python.
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
    -- the same event sent twice (a retried pipeline step) is stored once
    CONSTRAINT events_unique UNIQUE (service, type, ref, ts)
);
```

- **Lines 1 and 2** (`--` starts a comment): one table, written only through the collector or the simulation, plus two views that turn deployment references into rows so the metrics can be asked for in SQL as well as in Python.
- **Line 3**: `CREATE TABLE IF NOT EXISTS events (` makes the table; `IF NOT EXISTS` makes a second run do nothing.
- **Line 4**: `id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY`: the database numbers the rows itself; `ALWAYS` forbids a client from supplying its own number; `PRIMARY KEY` means unique and never empty.
- **Line 5**: `ts timestamptz NOT NULL`: the moment of the event, stored as an exact instant (in UTC) and shown in the session's time zone. **Lines 6 to 9**: `service`, `type`, `ref` as `text NOT NULL`; `detail text NOT NULL DEFAULT ''` (a default of empty text if none is given).
- **Line 10**: `CONSTRAINT events_service_format CHECK (service ~ '^[a-z][a-z0-9-]{1,38}$')`. A named rule; `~` means "matches this regular expression" (start, a lowercase letter, then 1 to 38 lowercase letters, digits or dashes, end). The same pattern is in the Python `Event` class.
- **Line 11**: `CHECK (type IN ('commit', 'deploy', 'failed', 'recovered'))`: only the four kinds. **Line 12**: `CHECK (ref ~ '^[A-Za-z0-9._:+-]{1,200}$')`. **Line 13**: `CHECK (type <> 'deploy' OR ref LIKE '%:%')`: a deployment's ref must contain a colon (`<>` is "not equal", `LIKE '%:%'` means "contains a colon"). **Line 14**: `CHECK (detail = '' OR type = 'failed')`: a reason is allowed only on a `failed` event.
- **Lines 15 and 16**: the comment says a retried pipeline step must not duplicate an event; `CONSTRAINT events_unique UNIQUE (service, type, ref, ts)` makes the combination unique, and the adapter writes `ON CONFLICT DO NOTHING` so a repeat is silently ignored. **Line 17**: `);`.

```sql
COMMENT ON TABLE  events        IS 'Delivery events from pipelines: commit, deploy, failed, recovered. Every DORA metric is computed from this table only.';
COMMENT ON COLUMN events.ts     IS 'UTC, from the pipeline''s clock for every type, never from a developer-set field.';
COMMENT ON COLUMN events.ref    IS 'A commit id; for a deploy "<deployment id>:<commit>+<commit>"; for failed and recovered the deployment id.';
COMMENT ON COLUMN events.detail IS 'Why a deployment failed: rollback, incident, health-check or signature. Empty otherwise.';

CREATE INDEX IF NOT EXISTS events_service_type_ts_idx ON events (service, type, ts);
```

- **Lines 19 to 22**: `COMMENT ON TABLE ... IS '...'` and `COMMENT ON COLUMN ... IS '...'` store documentation inside the database (`''` inside a quoted text is one apostrophe). They state the project's central rule: `ts` is UTC from the pipeline's clock for every type, never from a developer-set field. **Line 24**: `CREATE INDEX IF NOT EXISTS events_service_type_ts_idx ON events (service, type, ts);` builds an index (a sorted side-structure, like a book's index) so "all deployments of one service in time order" is fast.

```sql
-- One row per commit of a deployment (an empty deployment has one row with a NULL commit_ref).
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

COMMENT ON VIEW deploy_commits IS 'Every production deployment with the commits it contained.';
```

- **Lines 26 to 40**: the **view** `deploy_commits`. A *view* is a saved query that behaves like a table. A deployment's ref is `d1:a1+a2`. `split_part(e.ref, ':', 1)` is the text before the first colon (`d1`) and `split_part(e.ref, ':', 2)` the text after it (`a1+a2`). `string_to_array(x, '+')` turns `a1+a2` into the array `{a1,a2}`; `unnest(array)` turns an array into one row per element; `CROSS JOIN LATERAL` lets the right-hand side refer to the current row of `events`, so one deployment becomes one row per commit. `nullif(c.commit_ref, '')` turns an empty text into `NULL` (unknown). `WHERE e.type = 'deploy'` keeps only deployments. `UNION ALL` stacks the second query under the first: **lines 35 to 38** handle an *empty deployment* (nothing after the colon), giving one row with `NULL` as its commit. **Line 40** documents the view.

```sql
-- Lead time per commit: from the commit event to the deployment that contains it, in hours.
CREATE OR REPLACE VIEW lead_times AS
SELECT d.service,
       d.commit_ref,
       c.ts        AS committed_at,
       d.deploy_id,
       d.deployed_at,
       extract(epoch FROM d.deployed_at - c.ts) / 3600.0 AS hours
FROM deploy_commits d
JOIN events c ON c.service = d.service AND c.type = 'commit' AND c.ref = d.commit_ref;

COMMENT ON VIEW lead_times IS 'One row per commit that reached production, with the two events it is the difference of.';
```

- **Lines 42 to 51**: the view `lead_times`: for every commit that reached production, join its `commit` event with the deployment (`JOIN events c ON c.service = d.service AND c.type = 'commit' AND c.ref = d.commit_ref`) and compute `extract(epoch FROM d.deployed_at - c.ts) / 3600.0`: subtracting two moments gives an interval, `extract(epoch FROM interval)` is its length in seconds, and dividing by 3600.0 gives hours. **Line 53** documents it.

### The container

The database runs in `postgres:16.4-alpine` with no default password, published on `127.0.0.1:55441`, health-checked over TCP, with its data in memory ([docker-compose.md](docker-compose.md)). `make db` applies `sql/001_*.sql` and `sql/002_*.sql` with `psql -v ON_ERROR_STOP=1` ([make.md](make.md)).

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
