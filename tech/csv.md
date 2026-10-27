# CSV (the lesson's sample events)

## What it is

CSV ("comma-separated values") is a plain-text table: one row per line, columns separated by commas, the first line naming the columns. Spreadsheets and Python's `csv` module read it.

## Why this repository uses it

The lesson gives a small table of events (`events.csv`) and states the numbers it expects. `data/events-sample.csv` is that table, and `CsvEventStore` reads it, so `make dora-sample` reproduces the lesson's numbers **without a database**. The same `Event` objects can come from a CSV file, from PostgreSQL, or from the simulation.

## Where it appears

| Path | Use |
|---|---|
| `data/events-sample.csv` | The lesson's sample: columns `ts,service,type,ref`. |
| `src/goldenpath/infrastructure/csv_store.py` | `CsvEventStore`: reads and appends. |
| `Makefile` | `dora-sample`: `goldenpath metrics --csv data/events-sample.csv`. |

## How it works underneath

`csv.DictReader` reads the header line and returns each row as a dictionary keyed by column name. Everything read is text; numbers and dates must be converted. Opening with `newline=""` stops Python from altering line endings that the csv module manages itself.

## Walkthrough of this repository's use

```
ts,service,type,ref
2026-09-01T09:00,orders,commit,a1
2026-09-01T10:30,orders,commit,a2
2026-09-01T14:00,orders,deploy,d1:a1+a2
```
Times are in minutes and read as UTC. A deployment's commits are in its ref, joined by `+`.

```python
with self._path.open(newline="") as handle:
    events = [
        Event(parse_timestamp(row["ts"]), row["service"], EventType(row["type"]), row["ref"], row.get("detail") or "")
        for row in csv.DictReader(handle)
    ]
return sorted(events, key=lambda event: event.ts)
```
Each row becomes a validated `Event` (a bad row raises `InvalidEventError`). `row.get("detail") or ""` handles the sample file, which has no `detail` column. The result is sorted by time.

```python
def append(self, events):
    existing = set(self.all())
    new = [event for event in events if event not in existing]
    is_new_file = not self._path.exists() or self._path.stat().st_size == 0
    with self._path.open("a", newline="") as handle:
        writer = csv.writer(handle)
        if is_new_file:
            writer.writerow(["ts", "service", "type", "ref", "detail"])
```
Only events not already in the file are added (an event is a frozen dataclass, so `in` compares all its fields). The header is written once, for a new or empty file, and includes the `detail` column.

## Try it yourself

```bash
head -5 data/events-sample.csv
```

```bash
make dora-sample
```
Expect:
```
service  deploys/week  median lead time  change fail rate  recovery time  batch  empty  open  refused
billing  1             62.0 h            100%              240 min        4.0    0      0     0
orders   4             4.0 h             25%               30 min         1.0    0      0     0
```

```bash
.venv/bin/python -c "
from pathlib import Path
from goldenpath.infrastructure.csv_store import CsvEventStore
events = CsvEventStore(Path('data/events-sample.csv')).all()
print(len(events), events[0].service, events[0].type.value)
"
```
Prints the number of events in the file and the first one.

## Mistakes people make

- Splitting lines on commas by hand instead of using the `csv` module.
- Forgetting `newline=""`.
- Reading times without a zone; `parse_timestamp` makes them UTC.
- Appending the same events twice; the store skips duplicates.

## Check yourself

1. Why does `make dora-sample` need no database? *It reads the CSV through `CsvEventStore`.*
2. What does `DictReader` return per row? *A dictionary keyed by the header names.*
3. How does the sample file get UTC times? *`parse_timestamp` treats a time without an offset as UTC.*
4. Why `row.get("detail") or ""`? *The sample has no `detail` column.*
5. What stops duplicates on append? *The store compares each event with those already in the file.*

## Further reading

- `csv` module: https://docs.python.org/3.12/library/csv.html
