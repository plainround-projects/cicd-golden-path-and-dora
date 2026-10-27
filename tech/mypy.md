# mypy

## What it is

Python lets you pass anything to anything and finds out at run time, when something fails. A **type hint** is a note on a name, a parameter or a result saying what kind of value belongs there: `limit: int`, `-> list[JobRecord]`. A **type checker** is a program that reads those notes *without running the program* and reports places where they contradict each other: you passed text where a number is expected; you used a value that might be `None` as if it were never `None`; you called a method that the object does not have.

**mypy** is the most widely used type checker for Python. This repository pins mypy 2.4.0. Python itself ignores type hints when the program runs; they are for mypy, for editors and for the reader.

Useful words: `X | None` means "an X, or the special value `None`" (a value that means "nothing"). A **Protocol** is a list of methods that an object must have; mypy accepts any object that has them, without inheritance. **Strict mode** switches on all of mypy's optional checks.

## Why this repository uses it

The platform is built around **ports**: lists of methods that a use case needs (`EventSink`, `EventStore`, `Catalog`, `Repositories`, `Auditor`, `TemplateRenderer`) and **adapters** that provide them (PostgreSQL, CSV, files, Git, HTTP). mypy checks that every adapter really has the methods its port promises, and that "may be absent" values are handled. It runs in **strict mode**.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` lines 44 to 53 | The settings. |
| `Makefile` `lint` | Runs `mypy` with no arguments. |
| `src/goldenpath/application/ports.py` | The `Protocol` classes adapters are checked against. |
| `src/`, `tests/` | Both are checked; `template/` is not (it holds placeholders). |

## How it works underneath

mypy parses every file, builds a model of each function's input and output types, and then checks every call and assignment against it. It follows `if x is not None:` checks to know that inside the `if` the value is not `None`. For a `Protocol` it compares method names and signatures. Libraries without hints need a *stub package* of hints: `types-PyYAML` is the stub package for `pyyaml`.

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

- **Line 44**: `[tool.mypy]`. **Line 45**: `python_version = "3.12"`. **Line 46**: `strict = true` switches on every optional strictness check: all functions must have type hints on every parameter and the result; calling an untyped function from typed code is an error; returning `Any` from a typed function is a warning; an unused `# type: ignore` comment is an error. **Line 47**: `files = ["src", "tests"]`.
- **Lines 49 to 53**: `[[tool.mypy.overrides]]` for `module = ["tests.*"]` turns three strict checks off (`disallow_untyped_defs`, `disallow_incomplete_defs`, `disallow_untyped_calls`) so test functions need no hints, which keeps them short; the code under test stays strictly checked.

### What strictness checks in this code

- `EventSink` and `EventStore` (in `ports.py`) are `Protocol`s: `EventSink` has `append(events: Iterable[Event]) -> int`, and `EventStore` adds `all() -> list[Event]` and `clear() -> None`. `PostgresEventStore` and `CsvEventStore` have all three methods, so they can be used wherever an `EventStore` is needed. `CollectorEventSink` has only `append`, so it can be used where an `EventSink` is needed (a pipeline recording events) but mypy would reject it where an `EventStore` is needed. The use case `record(sink, events)` is typed against the smaller port, so it works with all three.
- `ServiceMetrics.median_lead_time_hours: float | None` says a service may have no lead time yet; every caller must handle `None`, as `render.py` does with `_fmt` (`"n/a" if value is None else ...`) and the tests do with a helper `known(value)` that asserts the value is not `None`.
- `Settings.from_env(cls, environ: Mapping[str, str] | None = None, need_database: bool = True) -> Settings`: `Mapping` is a read-only dictionary-like type, so the function promises not to change what it is given.
- `def collector_server(port: int, sink: EventSink, token: str, clock: Any = None) -> ThreadingHTTPServer`: the `Any` for `clock` means "anything"; it is the one place where a test may pass a function.

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
