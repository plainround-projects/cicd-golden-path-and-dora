# SQL

## What it is

SQL is the language for talking to a relational database. Statements **define** structure (`CREATE TABLE`, `CREATE VIEW`, `CREATE INDEX`), **change** data (`INSERT`, `DELETE`) and **read** data (`SELECT`). You say *what* you want; the database chooses *how*. This repository uses the PostgreSQL 16 dialect ([postgresql.md](postgresql.md)).

## Why this repository uses it

The lesson says the four delivery metrics come from events alone. SQL shows the same numbers a second way: the Python domain computes them from `Event` objects, and the SQL in `sql/003_queries.sql` computes them from the table. A test checks that both produce the same numbers on the lesson's sample data.

## Where it appears

| Path | What it does |
|---|---|
| `sql/001_schema.sql` | DDL: the `events` table, an index, views `deploy_commits` and `lead_times`. |
| `sql/002_seed.sql` | Sample events. |
| `sql/003_queries.sql` | Step 4 (deployments with commits), step 5 (trace one lead time; the four metrics). |
| `src/goldenpath/infrastructure/postgres_store.py` | `INSERT ... ON CONFLICT DO NOTHING`, `SELECT`, `TRUNCATE`. |
| `tests/integration/test_postgres_store_and_sql.py` | Runs the queries and compares them with the Python result. |

## How it works underneath

A `SELECT` is read in this logical order: `FROM` (which tables), `WHERE` (which rows), `GROUP BY` (collapse into groups), the select list (what to output), `ORDER BY`, `LIMIT`. A **CTE** (`WITH name AS (...)`) names a sub-query so later parts can use it. A **window of time** is just a `WHERE ts >= a AND ts < b`. `NULL` means "unknown"; `NULL = NULL` is not true.

## Walkthrough of this repository's use

### Trace one lead time (step 5)

```sql
SELECT l.commit_ref, l.committed_at, l.deploy_id, l.deployed_at, round(l.hours::numeric, 1) AS hours
FROM lead_times l
WHERE l.service = 'sample-orders' AND l.commit_ref = 'a5';
```
`l` is an **alias** for the view. `::numeric` converts the type so `round(x, 1)` works. The result names the two events the number is the difference of.

### Deployments with their commits (step 4)

```sql
SELECT service, deploy_id, deployed_at, coalesce(string_agg(commit_ref, ', ' ORDER BY commit_ref), '(none)') AS commits
FROM deploy_commits
WHERE service = 'sample-orders'
GROUP BY service, deploy_id, deployed_at
ORDER BY deployed_at;
```
`string_agg` joins the commits of each group into one text. `coalesce(x, y)` returns `x`, or `y` when `x` is `NULL`: an empty deployment shows `(none)`.

### The four metrics in one query

```sql
WITH scope AS (
    SELECT * FROM events WHERE service LIKE 'sample-%'
), window_ AS (
    SELECT date_trunc('day', min(ts)) AS start_at,
           ceil(extract(epoch FROM max(ts) - date_trunc('day', min(ts))) / (7 * 86400.0)) AS weeks
    FROM scope
), ...
```
- `scope`: only the sample services. `LIKE 'sample-%'`: starts with `sample-`.
- `window_`: the data's own window. `date_trunc('day', min(ts))` is midnight of the first day; `ceil(.../(7*86400.0))` rounds the span up to whole weeks (`86400` seconds in a day). The Python function `window_of` does the same.

```sql
real_deploys AS (
    SELECT DISTINCT d.service, d.deploy_id, d.deployed_at
    FROM deploy_commits d, window_ w
    WHERE d.commit_ref IS NOT NULL AND d.deployed_at >= w.start_at AND d.deployed_at < w.start_at + w.weeks * interval '7 days'
      AND d.service LIKE 'sample-%'
),
```
Deployments inside the window that contain at least one commit. An empty deployment does not count for frequency.

```sql
failures AS (
    SELECT f.service, f.ref AS deploy_id, f.ts AS failed_at,
           (SELECT min(r.ts) FROM events r WHERE r.service = f.service AND r.type = 'recovered' AND r.ref = f.ref AND r.ts >= f.ts) AS recovered_at
    FROM events f WHERE f.type = 'failed' AND f.service LIKE 'sample-%'
)
```
Each `failed` event with the first later `recovered` event for the same deployment (a **correlated sub-query**: it refers to `f` from the outside).

```sql
SELECT d.service,
       round(count(*)::numeric / max(w.weeks), 1)                                             AS deploys_per_week,
       round((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY l.hours) FROM lead_times l JOIN real_deploys x USING (service, deploy_id) WHERE l.service = d.service)::numeric, 1) AS median_lead_time_hours,
       round(100.0 * count(DISTINCT f.deploy_id) / count(*))                                  AS change_fail_rate_percent,
       round((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM f2.recovered_at - f2.failed_at) / 60) FROM failures f2 WHERE f2.service = d.service AND f2.recovered_at IS NOT NULL)::numeric) AS median_recovery_minutes
FROM real_deploys d CROSS JOIN window_ w
LEFT JOIN failures f ON f.service = d.service AND f.deploy_id = d.deploy_id
GROUP BY d.service ORDER BY d.service;
```
- Deployment frequency: deployments divided by weeks.
- `percentile_cont(0.5) WITHIN GROUP (ORDER BY x)` is the **median**.
- Change fail rate: distinct failed deployments divided by deployments. `LEFT JOIN` keeps deployments that never failed (they get `NULL` failure columns).
- Recovery time: median minutes from `failed` to `recovered`.

### Writing events from Python

```python
"INSERT INTO events (ts, service, type, ref, detail) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING"
```
Five placeholders; a repeated event is ignored. `cursor.rowcount` tells how many rows were really inserted.

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
