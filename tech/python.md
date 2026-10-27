# Python 3.12

## What it is

Python is a programming language. You write text files that end in `.py`. A program called the **interpreter** reads a file and runs it line by line. A **module** is one `.py` file. A **package** is a folder of modules with an `__init__.py`. This repository needs Python 3.12 or newer (`requires-python = ">=3.12"`); the generated services run on 3.12.8 in a container.

## Why this repository uses it

The platform is a tool written in Python: it renders a template into a new repository, audits it against a contract, receives delivery events over HTTP, stores them, and computes the four DORA metrics ([dora-metrics.md](dora-metrics.md)). The generated example service is also a small Python program.

## Where it appears

| Path | What it does with Python |
|---|---|
| `src/goldenpath/domain/` | Pure logic: `Event`, the metrics, the contract rules, the catalog rules, the simulation. No files, no network. |
| `src/goldenpath/application/` | Use cases (`ServiceGenerator`, `record`, `measure`) and the `Protocol` ports. |
| `src/goldenpath/infrastructure/` | Adapters: PostgreSQL, CSV, files, `git`, the template renderer, the auditor, the HTTP client, settings, logging. |
| `src/goldenpath/interfaces/` | The `goldenpath` command, the collector HTTP server, the table renderer. |
| `template/app/main.py` | The generated service (an HTTP server with `/healthz`). |
| `scripts/lint_workflows.py` | A script that applies the contract rules to the workflow files. |
| `tests/` | `unit`, `template`, `integration`, `e2e`. |

## How it works underneath

- The interpreter compiles source to **bytecode** and runs it on a virtual machine. `import x` finds module `x`, runs it once and caches it.
- A **virtual environment** (`.venv`) is a private folder with its own interpreter and libraries ([pip-and-hash-locking.md](pip-and-hash-locking.md)).
- **Type hints** (`x: int`) are notes for tools; Python ignores them at run time. [mypy](mypy.md) reads them.
- `random.Random(seed)` makes a pseudo-random generator that gives the same numbers for the same seed. That is what makes the simulation repeatable.

## Walkthrough of this repository's use

### Dataclasses that validate themselves

```python
@dataclass(frozen=True, slots=True)
class Event:
    ts: datetime
    service: str
    type: EventType
    ref: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.ts.tzinfo is None:
            raise InvalidEventError("ts must carry a time zone (UTC)")
        if not _SERVICE.match(self.service): ...
```
`@dataclass` writes `__init__` from the field list. `frozen=True` makes instances read-only. `slots=True` stores fields in fixed slots (less memory, typos rejected). `__post_init__` runs right after the generated `__init__` and refuses an event that cannot be placed on a timeline: no time zone, a bad service name, a bad ref, a `deploy` without `:` in its ref, a `detail` on anything but `failed`. **An invalid `Event` cannot exist.**

### Enumerations

```python
class EventType(StrEnum):
    COMMIT = "commit"
    DEPLOY = "deploy"
    FAILED = "failed"
    RECOVERED = "recovered"
```
`StrEnum` (Python 3.11 and newer) is a fixed set of names that are also strings. `EventType("deploy")` finds the member or raises `ValueError`; `.value` gives the text. The code compares members with `is` (`event.type is EventType.DEPLOY`).

### Regular expressions

```python
_SERVICE: Final = re.compile(r"^[a-z][a-z0-9-]{1,38}$")
```
A **regular expression** describes a text pattern: start (`^`), a lowercase letter, then 1 to 38 lowercase letters, digits or dashes, end (`$`). `Final` tells mypy the name is never reassigned. The same patterns appear in the SQL `CHECK` constraints ([postgresql.md](postgresql.md)), so the database and the code agree.

### Pure functions and the median

`compute()` in `domain/metrics.py` takes a list of events and returns a `ServiceMetrics`. It reads no clock and no file. It uses `statistics.median`, the middle value after sorting; a single slow deployment does not move it. `defaultdict(list)` is a dictionary that creates an empty list the first time you use a missing key.

### Protocols (ports)

```python
class EventSink(Protocol):
    def append(self, events: Iterable[Event]) -> int: ...
class EventStore(EventSink, Protocol): ...
```
A `Protocol` lists the methods an object needs. `PostgresEventStore`, `CsvEventStore` and `CollectorEventSink` all have `append`, so any of them can be an `EventSink`. The use case `record(sink, events)` does not know which one it gets.

### Standard-library servers and clients

| Piece | Where | Why |
|---|---|---|
| `http.server.ThreadingHTTPServer` | `interfaces/collector.py`, `template/app/main.py` | An HTTP server with one thread per request ([http-server.md](http-server.md)). |
| `urllib.request` | `infrastructure/collector_client.py` | An HTTP client with no extra library. |
| `hmac.compare_digest` | `collector.py` | Compares the bearer token in constant time. |
| `subprocess.run` | `local_pipeline.py`, `repositories.py` | Runs `make`, `git`, `docker` as argument lists, never through a shell. |
| `shutil.copy2`, `Path.rglob` | `template_renderer.py` | Copies the template and keeps file modes (scripts stay executable). |
| `json`, `csv`, `yaml` | adapters | Data formats ([json.md](json.md), [csv.md](csv.md), [yaml.md](yaml.md)). |
| `datetime`, `timedelta` | everywhere | UTC time stamps; `fromisoformat` parses them. |

### `match`, signals and threads in the command line

```python
match args.command:
    case "new-service":
        return _new_service(args, settings)
    case "collector":
        return _serve_collector(settings)
```
`match` (Python 3.10 and newer) compares a value against patterns, like a tidy chain of `if ... elif`. `_serve_collector` starts the HTTP server on a **daemon thread** (a thread that does not keep the program alive), registers a handler for `SIGTERM` and `SIGINT` (the signals sent by `kill` and by Ctrl-C), and waits on a `threading.Event`. When a signal arrives, the handler sets the event, the main thread wakes up, and the server is shut down cleanly instead of being cut off.

### Exceptions as the error vocabulary

All domain errors derive from `DomainError`. `NonConformingServiceError(DomainError)` carries a `findings` list. `raise ... from None` hides a confusing earlier exception when the new message says everything.

### `if __name__ == "__main__"`

At the end of `template/app/main.py` and `scripts/lint_workflows.py`: run `main()` only when the file is executed directly, not when it is imported.

## Try it yourself

```bash
make install
.venv/bin/python --version
```

```bash
.venv/bin/python -c "
from datetime import datetime, UTC
from goldenpath.domain.events import Event, EventType
print(Event(datetime(2026,9,1,9,0,tzinfo=UTC), 'orders', EventType.COMMIT, 'a1'))
Event(datetime(2026,9,1,9,0), 'orders', EventType.COMMIT, 'a1')
" 2>&1 | tail -2
```
The first line prints the event. The second ends with `InvalidEventError: ts must carry a time zone (UTC)`.

```bash
.venv/bin/python -c "from goldenpath.domain.simulation import simulate; a = simulate(7); b = simulate(7); print(len(a), a == b)"
```
Prints a count and `True`: the same seed gives the same month.

```bash
.venv/bin/python -c "from goldenpath.domain.events import parse_deploy_ref; print(parse_deploy_ref('d1:a1+a2'), parse_deploy_ref('d9:'))"
```
Expect `DeployRef(deployment='d1', commits=('a1', 'a2')) DeployRef(deployment='d9', commits=())`.

## Mistakes people make

- Naive datetimes (no time zone). `Event` refuses them.
- Mutable shared state. The dataclasses are frozen.
- Building shell strings for `subprocess`. Here every call is a list.
- Comparing secrets with `==`. The collector uses `hmac.compare_digest`.
- A random simulation that nobody can repeat. Here the seed fixes it.

## Check yourself

1. What does `__post_init__` do here? *Validates the fields right after creation, so a bad event cannot exist.*
2. Why do the three stores share `append`? *They all satisfy the `EventSink` protocol, so a use case accepts any of them.*
3. What does `random.Random(seed)` give you? *The same sequence for the same seed.*
4. Why is `frozen=True` useful for events? *They cannot change after being checked.*
5. What does `StrEnum` add over plain strings? *A fixed set of allowed values.*

## Further reading

- Python 3.12 documentation: https://docs.python.org/3.12/
- `enum.StrEnum`: https://docs.python.org/3.12/library/enum.html#enum.StrEnum
- `dataclasses`: https://docs.python.org/3.12/library/dataclasses.html
- `http.server`: https://docs.python.org/3.12/library/http.server.html
- `hmac.compare_digest`: https://docs.python.org/3.12/library/hmac.html#hmac.compare_digest
