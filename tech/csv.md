# CSV (the lesson's sample events)

## What it is

**CSV** stands for "comma-separated values". It is the simplest way to store a table in a text file: one row per line, the cells of a row separated by commas, and the first line holding the column names. A spreadsheet program opens it as a table; so does Python's `csv` module. If a cell contains a comma or a quote, it is wrapped in double quotes (and quotes inside are doubled). Everything in a CSV file is text: a program that wants a number must convert it.

## Why this repository uses it

The lesson gives a small table of events (`events.csv`) and states the numbers it expects. `data/events-sample.csv` is that table and `CsvEventStore` reads it, so `make dora-sample` reproduces the lesson's numbers **without a database**. The same `Event` objects can come from a CSV file, from PostgreSQL or from the simulation: the code that computes the metrics does not know the difference.

## Where it appears

| Path | Use |
|---|---|
| `data/events-sample.csv` | The lesson's sample: columns `ts,service,type,ref`. |
| `src/goldenpath/infrastructure/csv_store.py` | `CsvEventStore`: reads and appends. |
| `Makefile` | `dora-sample`: `goldenpath metrics --csv data/events-sample.csv`. |
| `src/goldenpath/interfaces/cli.py` | `--csv` on `metrics`, `trace` and `deployments`. |

## How it works underneath

`csv.writer(handle).writerow([...])` writes one row, quoting where needed. `csv.DictReader(handle)` reads the first line as the header and returns each following row as a dictionary keyed by the column names. Files are opened with `newline=""` so that Python does not change line endings the csv module is already managing. Opening in mode `"a"` appends; mode `"w"` replaces.

## Walkthrough of this repository's use

### The file

```
ts,service,type,ref
2026-09-01T09:00,orders,commit,a1
2026-09-01T10:30,orders,commit,a2
2026-09-01T14:00,orders,deploy,d1:a1+a2
2026-09-02T11:00,orders,commit,a3
2026-09-02T15:00,orders,deploy,d2:a3
```

Line 1 is the header. Each other line is one event: a time without seconds (read as UTC), the service, the type and the ref. A deployment's commits are in its ref, joined by `+` (`d1:a1+a2`). There are 18 events and no `detail` column.

### Reading: `CsvEventStore.all`

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- `if not self._path.exists(): return []` treats a missing file as no events. `self._path.open(newline="")` opens for reading (`newline=""` stops Python changing line endings the csv module manages itself). `csv.DictReader(handle)` returns each row as a dictionary keyed by the header. The list comprehension builds a validated `Event` per row: `parse_timestamp(row["ts"])`, `EventType(row["type"])`, `row["ref"]`, and `row.get("detail") or ""` (the sample has no `detail` column, so `get` returns `None`, and `or ""` turns it into empty text). The result is sorted by time: `sorted(events, key=lambda event: event.ts)`.

### Writing: `CsvEventStore.append`

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- `existing = set(self.all())` collects the events already in the file into a **set** (events are frozen dataclasses, so they can be members of a set); `new = [event for event in events if event not in existing]` keeps only the others, so appending the same events twice stores them once. `is_new_file = not self._path.exists() or self._path.stat().st_size == 0` is true for a missing or empty file, and then `writer.writerow(["ts", "service", "type", "ref", "detail"])` writes the header (this file has the extra `detail` column). `with self._path.open("a", newline="") as handle:` opens for **appending**. Each event becomes one row: `event.ts.strftime("%Y-%m-%dT%H:%M:%S")` formats the time as text. `return len(new)` says how many were new. `clear()` deletes the file (`unlink(missing_ok=True)`).

### Why it matters

`make dora-sample` prints the lesson's numbers from this file alone; the unit tests read it too (`len(events) == 18` and the first event is commit `a1`); and the integration test loads the same events into PostgreSQL to prove that SQL and Python agree ([pytest.md](pytest.md), [dora-metrics.md](dora-metrics.md)).

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
