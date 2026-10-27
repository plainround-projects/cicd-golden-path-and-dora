# mypy

## What it is

mypy is a **static type checker** for Python: it reads your code without running it and uses the type hints (`def f(x: int) -> str`) to find mistakes such as passing text where a number is expected, or forgetting that a value can be `None`. Pinned: 2.4.0.

## Why this repository uses it

Part of the platform is a set of **contracts** between layers: ports (`EventSink`, `EventStore`, `Catalog`, `Repositories`, `Auditor`, `TemplateRenderer`) and the adapters that implement them. mypy checks that every adapter really has the methods its port promises, and that `Optional` values are handled. The run is in **strict mode**.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` `[tool.mypy]` | `strict = true`, `files = ["src", "tests"]`. |
| `Makefile`, target `lint` | `$(VENV)/bin/mypy` with no arguments. |
| `src/goldenpath/application/ports.py` | The `Protocol` classes mypy checks adapters against. |

## How it works underneath

mypy builds a model of every function's input and output types and checks each call and assignment. It knows that `str | None` may be `None`, so using it as a `str` is an error until you check. For a `Protocol`, an object matches if it has the right methods; no inheritance is needed. Libraries without hints need a stub package (`types-PyYAML` here).

## Walkthrough of this repository's use

```toml
[tool.mypy]
python_version = "3.12"
strict = true
files = ["src", "tests"]

[[tool.mypy.overrides]]
module = ["tests.*"]
disallow_untyped_defs = false
disallow_incomplete_defs = false
disallow_untyped_calls = false
```
`strict = true` turns on all the optional checks: every function annotated, no silent `Any`, warnings for unused `# type: ignore`. The override relaxes only the test modules so test functions stay short. `[[...]]` is a TOML list of tables ([toml.md](toml.md)). `template/` is not listed in `files`, so mypy never sees placeholder files.

### What it checks here

```python
class EventSink(Protocol):
    def append(self, events: Iterable[Event]) -> int: ...
class EventStore(EventSink, Protocol):
    def all(self) -> list[Event]: ...
    def clear(self) -> None: ...
```
`PostgresEventStore` and `CsvEventStore` implement `append`, `all` and `clear`; `CollectorEventSink` implements only `append`. The CLI can pass the collector sink where an `EventSink` is needed, but mypy would reject passing it where an `EventStore` is needed (it lacks `all`). The use case `record(sink, events)` is typed against the small port.

```python
median_lead_time_hours: float | None
```
`ServiceMetrics` says plainly that a service may have no lead time yet. A caller that formats the value must handle `None`; `interfaces/render.py` does.

```python
def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None
```
The `if values else None` handles the empty list, which `statistics.median` would reject.

## Try it yourself

```bash
.venv/bin/mypy --version
.venv/bin/mypy
```
Expect `mypy 2.4.0` and `Success: no issues found in N source files`.

Make a deliberate mistake (the file must live inside `src/` so mypy resolves the project's modules):
```bash
printf 'from goldenpath.infrastructure.collector_client import CollectorEventSink\nfrom goldenpath.application.ports import EventStore\nstore: EventStore = CollectorEventSink("http://x", "t")\n' > src/typo_demo.py
.venv/bin/mypy src/typo_demo.py 2>&1 | tail -5
rm src/typo_demo.py
```
Expect `Incompatible types in assignment` and a note that `CollectorEventSink` is missing the protocol members `all, clear`.

## Mistakes people make

- `# type: ignore` to silence an error instead of fixing it. Strict mode flags unused ones.
- Using `Any` to make errors disappear.
- Believing hints change how the program runs. They do not.

## Check yourself

1. Does mypy run your code? *No.*
2. Why can `CollectorEventSink` be an `EventSink` but not an `EventStore`? *It has `append` but not `all` and `clear`.*
3. What does `float | None` force you to do? *Handle the `None` case.*
4. Why relax rules for `tests.*`? *Test functions stay short without annotations.*
5. What does `strict = true` do? *Turns on all optional strictness checks.*

## Further reading

- mypy documentation: https://mypy.readthedocs.io/en/stable/ (2.4.0)
- Protocols: https://mypy.readthedocs.io/en/stable/protocols.html
- Strict mode: https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-strict
