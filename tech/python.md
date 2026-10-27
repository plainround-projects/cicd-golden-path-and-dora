# Python 3.12

## What it is

A **computer program** is a list of instructions that a computer follows. **Python** is a language you write those instructions in. You write them in a plain text file whose name ends in `.py`. Such a file is called a **source file**.

A computer cannot follow Python text directly. A program called the **interpreter** reads your file and does what it says, one instruction at a time. When you type `python something.py` in a **terminal** (a window where you type commands and read answers), you are starting the interpreter and giving it your file.

A few words you will meet again and again:

- A **module** is one `.py` file. Other files can use what it defines by *importing* it.
- A **package** is a folder of modules. Python knows a folder is a package when it contains a file called `__init__.py` (it may be almost empty).
- A **function** is a named set of instructions you can run whenever you want. A **class** is a recipe for making *objects*: values that bundle data together with the functions that work on it.
- A **library** is code that somebody else wrote and you use. The **standard library** is the large set of libraries that comes with Python itself, so nothing needs to be installed to use it.
- A **type hint** is a note such as `x: int` that says "this should be a whole number". Python does not enforce it when the program runs. Other tools read it and warn you about mistakes ([mypy.md](mypy.md)).

This repository needs Python 3.12 or newer (`requires-python = ">=3.12"` in `pyproject.toml`). The container image uses 3.12.8. The version matters because some lines below use features that older Pythons do not have.

## Why this repository uses it

The whole platform is Python, and so is the example service it generates. The platform (`src/goldenpath/`) does five jobs: it **renders a template** into a new repository, **audits** that repository against the golden-path contract, **receives delivery events** over HTTP and stores them, **computes the four DORA metrics** from those events ([dora-metrics.md](dora-metrics.md)), and **simulates a month** of work for three teams. The generated service (`template/app/main.py`) is a tiny web service written with only the standard library, so a new service has no dependencies to install.

## Where it appears

The platform follows the same layering as the other projects in this track: each folder is a layer that may only use the layers below it ([import-linter.md](import-linter.md) checks this).

| Path | Layer | What lives there |
|---|---|---|
| `src/goldenpath/domain/` | innermost | `events.py` (the `Event`), `metrics.py` (the four measures), `rules.py` (the golden-path contract as checks), `catalog.py` (catalog entries), `simulation.py` (a deterministic month), `errors.py`. It uses only the standard library. |
| `src/goldenpath/application/` | uses the domain | `ports.py` (what the outside world must offer), `generate_service.py`, `measure.py`, `record_events.py`. |
| `src/goldenpath/infrastructure/` | touches the world | `settings.py`, `logging.py`, `postgres_store.py`, `csv_store.py`, `catalog_files.py`, `template_renderer.py`, `repositories.py` (Git), `auditor.py`, `collector_client.py`, `local_pipeline.py`. |
| `src/goldenpath/interfaces/` | outermost | `cli.py` (the `goldenpath` command), `collector.py` (the HTTP server), `render.py` (text tables). |
| `scripts/lint_workflows.py` | | Applies the contract rules to the workflow files. |
| `template/app/main.py` | | The generated service. |
| `tests/` | | `unit`, `template`, `integration`, `e2e` ([pytest.md](pytest.md)). |

## How it works underneath

**What happens when you run a Python file.** The interpreter reads the text, checks that it is valid Python, and turns it into **bytecode**: a compact list of small steps. It keeps a copy of that bytecode in a folder named `__pycache__` so the next run starts faster. Then it carries out the steps one by one.

**What `import` does.** The line `import x` makes the interpreter look for a module called `x`. It searches a list of folders (`sys.path`): the folder of your script, the standard library, and the folders where installed libraries live. When it finds `x` it runs the file *once*, remembers the result, and gives you the name `x`. The second time any file imports `x`, the interpreter reuses the remembered result.

**Where installed libraries live.** A **virtual environment** (the `.venv` folder) is a private copy of Python with its own empty place for libraries. Each project gets its own, so two projects can use different versions of the same library without clashing ([pip-and-hash-locking.md](pip-and-hash-locking.md)).

**Names and values.** In `count = 3`, `count` is a *name* and `3` is a *value*. Writing `count = 3` attaches the name to the value. Values have types: whole numbers (`int`), numbers with a fraction (`float`), text (`str`), true/false (`bool`), lists, dictionaries and many more. A **dictionary** (`dict`) maps keys to values, like `{"a": 1}`.

**A thread** is a second line of execution inside the same running program. Two threads can run at the same time and can see the same data. That is useful and dangerous: if two threads change the same dictionary at once, the result can be garbage. A **lock** lets only one thread into a protected piece of code at a time. You will meet threads in `interfaces/collector.py` (the web server runs each request on its own thread) and in `interfaces/cli.py` (the collector runs on a background thread).

## Walkthrough of this repository's use

Every Python file of the platform, in reading order: the rules first, then the use cases, then the adapters, then the commands. Names and ideas are explained where they first appear.

### `src/goldenpath/domain/errors.py`

```python
"""Named errors of the domain."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every error the domain raises on purpose."""


class InvalidEventError(DomainError, ValueError):
    """An event is missing a field or has one that cannot be right."""


class InvalidCatalogEntryError(DomainError, ValueError):
    """A catalog entry breaks the golden-path contract (for example, its owner is a person, not a team)."""


class UnknownCommitError(DomainError, LookupError):
    """A trace asked for a commit that has no event."""
```

- **Line 1**: a docstring (triple-quoted text first in a file, kept as documentation). **Line 3**: `from __future__ import annotations` makes Python store type hints as text and look nothing up when it reads them; every module here starts with it, so a hint can mention a class defined later in the file.
- **Lines 6 and 7**: a **class** is a recipe for a kind of object. `class DomainError(Exception):` defines a new kind that is a special case of `Exception`, Python's built-in "something went wrong". The indented lines under the class line are its body (Python uses indentation, four spaces per level, to show what belongs together). Here the body is just a docstring: `DomainError` behaves exactly like `Exception` and exists for its *name*. Code reports a problem with `raise SomeError("message")`; that stops what it was doing and travels up through the callers until something catches it with `try`/`except`, or the program ends with a message.
- **Lines 10 to 19**: three more errors. A class can have two parents, so `InvalidEventError(DomainError, ValueError)` is both our error and Python's `ValueError` ("the value is the right type but unusable"); a handler for either one catches it. `UnknownCommitError` also is a `LookupError` ("I looked for something that is not there"). The command line catches `DomainError` to print a calm message for mistakes the *caller* made.

### `src/goldenpath/domain/events.py`: the facts everything is computed from

An **event** is a fact about delivery: a commit entered the pipeline, a deployment reached production, a deployment failed, service was restored. Every number the platform reports is computed from these and nothing else.

```python
"""Delivery events: the facts every DORA metric is computed from. Nothing else is read, not even the Git history."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from goldenpath.domain.errors import InvalidEventError

_SERVICE: Final = re.compile(r"^[a-z][a-z0-9-]{1,38}$")
_REF: Final = re.compile(r"^[A-Za-z0-9._:+-]{1,200}$")


class EventType(StrEnum):
    """What happened: a commit entered the pipeline, a deployment reached production, failed, or was restored."""

    COMMIT = "commit"
    DEPLOY = "deploy"
    FAILED = "failed"
    RECOVERED = "recovered"

```

- **Line 5**: `import re` is the regular-expression module. A **regular expression** is a pattern describing text. **Line 13**, `_SERVICE = re.compile(r"^[a-z][a-z0-9-]{1,38}$")`: `^` the start; `[a-z]` one lowercase letter; `[a-z0-9-]{1,38}` then 1 to 38 characters that are lowercase letters, digits or dashes; `$` the end. So `orders` and `sample-billing` match; `Orders` and `a` do not. The `r` before the quotes makes it a raw string, where a backslash is just a backslash. **Line 14**, `_REF`, allows letters, digits and the characters `. _ : + -` for 1 to 200 characters. `Final` (line 9, used in the hint `Final`) tells the type checker that the name is never reassigned.
- **Line 7**: `from datetime import UTC, datetime`. `datetime` is Python's date-and-time type; `UTC` is the world reference time zone.
- **Line 8**: `from enum import StrEnum`. **Lines 17 to 23**: an **enumeration** is a fixed set of named values. `class EventType(StrEnum):` makes four members, each also a string: `COMMIT = "commit"`, `DEPLOY = "deploy"`, `FAILED = "failed"`, `RECOVERED = "recovered"`. `EventType("deploy")` finds the member or raises `ValueError`; `.value` gives the text back. The code compares members with `is`.

```python
@dataclass(frozen=True, slots=True)
class Event:
    """One delivery event. `ref` is a commit id, or for a deployment `<id>:<commit>+<commit>`, or a deployment id.

    `ts` is UTC and comes from the pipeline's clock for every event type (never from a developer-set field).
    `detail` says why a deployment failed (`rollback`, `incident`, `health-check`, `signature`); empty otherwise.
    """

    ts: datetime
    service: str
    type: EventType
    ref: str
    detail: str = ""

    def __post_init__(self) -> None:
        """Refuse an event that cannot be placed on a timeline."""
        if self.ts.tzinfo is None:
            raise InvalidEventError("ts must carry a time zone (UTC)")
        if not _SERVICE.match(self.service):
            raise InvalidEventError(f"service must be 2-39 characters of a-z, 0-9 and '-', got {self.service!r}")
        if not _REF.match(self.ref):
            raise InvalidEventError(f"ref must be 1-200 characters of letters, digits and . _ : + -, got {self.ref!r}")
        if self.type is EventType.DEPLOY and ":" not in self.ref:
            raise InvalidEventError("a deploy ref looks like 'd1:a1+a2' (deployment id, then its commits)")
        if self.detail and self.type is not EventType.FAILED:
            raise InvalidEventError("only a failed event carries a detail")
```

- **Line 26**: `@dataclass(frozen=True, slots=True)` is a **decorator**: a line starting with `@` that changes the class below it. `@dataclass` writes the boring methods (creating the object from its fields, printing, comparing). `frozen=True` forbids changing a field after creation; `slots=True` stores fields compactly and makes a mistyped field name an error.
- **Lines 34 to 38**: the five **fields**: the time `ts`, the `service` name, the `type`, the `ref` and an optional `detail` (`detail: str = ""` has a **default**: it may be left out). The docstring explains `ref`: a commit id, or for a deployment `<id>:<commit>+<commit>`, or a deployment id. It also states the rule that `ts` comes from the pipeline's clock, never from a developer-set field.
- **Lines 40 to 51**: `__post_init__` is a special method the dataclass calls right after it has set the fields. It **validates**. `self.ts.tzinfo is None` is true for a time without a time zone: refused, because such a time cannot be placed on a timeline. `_SERVICE.match(self.service)` returns `None` when the pattern does not match; the `not` turns that into a refusal with a message naming the bad value (`{self.service!r}` prints it with quotes so a stray space is visible). A `deploy` event must contain a colon (`":" not in self.ref`). A `detail` is allowed only on a `failed` event. Because the check happens when the object is created, **an invalid `Event` cannot exist anywhere in the program**.

```python
def parse_timestamp(text: str) -> datetime:
    """`2026-09-01T09:00` (minutes, UTC) or any ISO 8601 time with an offset."""
    parsed = datetime.fromisoformat(text.strip())
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class DeployRef:
    """The two halves of a deploy ref: the deployment's id and its commits (none: an empty deploy)."""

    deployment: str
    commits: tuple[str, ...]


def parse_deploy_ref(ref: str) -> DeployRef:
    """`d1:a1+a2` becomes ('d1', ('a1', 'a2')); `d9:` is a deployment with no commits."""
    deployment, _, rest = ref.partition(":")
    return DeployRef(deployment, tuple(part for part in rest.split("+") if part))


def format_deploy_ref(deployment: str, commits: tuple[str, ...] | list[str]) -> str:
    """The inverse of `parse_deploy_ref`."""
    return f"{deployment}:{'+'.join(commits)}"
```

- **Lines 54 to 57**, `parse_timestamp`: `datetime.fromisoformat(text.strip())` reads text like `2026-09-01T09:00`. If the result has no zone (`parsed.tzinfo is None`), `parsed.replace(tzinfo=UTC)` declares it UTC; otherwise `parsed.astimezone(UTC)` converts it. The one-line `A if condition else B` chooses between the two.
- **Lines 60 to 65**: `DeployRef` is a small frozen dataclass: a deployment's id and the tuple of commits it contains. A **tuple** is a fixed group of values.
- **Lines 68 to 71**, `parse_deploy_ref`: `ref.partition(":")` splits at the first colon into three parts (before, the colon, after); `deployment, _, rest = ...` keeps the first and last (`_` is the convention for "I don't use this"). `rest.split("+")` splits the commits; `tuple(part for part in ... if part)` is a generator expression that drops empty pieces, so `d9:` gives no commits.
- **Lines 74 to 76**, `format_deploy_ref`: the reverse: `f"{deployment}:{'+'.join(commits)}"`. An **f-string** is a string starting with `f` in which anything in `{braces}` is replaced by its value; `'+'.join(list)` glues the items with `+` between them.

### `src/goldenpath/domain/metrics.py`: the four measures

```python
"""The four DORA metrics, computed per service from events only.

- Deployment frequency: production deployments per week (one with no commit does not count: `empty_deploys`).
- Lead time for changes: from a commit event to the deployment event containing it, per commit; the median.
- Change fail rate: the share of deployments followed by a `failed` event.
- Recovery time: from `failed` to the next `recovered` for the same deployment; reported as the median.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from goldenpath.domain.errors import UnknownCommitError
from goldenpath.domain.events import Event, EventType, parse_deploy_ref

WEEK = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class ServiceMetrics:
    """The four metrics of one service over a window, plus the numbers that keep them honest."""

    service: str
    window_start: datetime
    window_end: datetime
    deploys: int
    empty_deploys: int
    deploys_per_week: float
    median_lead_time_hours: float | None
    change_fail_rate: float | None
    median_recovery_minutes: float | None
    median_batch_size: float | None
    open_failures: int
    refused: int  # deployments refused before anything ran (an unsigned image): failed events with detail "signature"


@dataclass(frozen=True, slots=True)
class LeadTime:
    """One lead time, with the two events it is the difference of (step 5: trace a value to its events)."""

    commit: Event
    deploy: Event
    hours: float

```

- **Lines 11 to 15**: `statistics.median` returns the middle value of a sorted list, and `defaultdict` is a dictionary that creates a default value (here an empty list) the first time a missing key is used. `timedelta` is a length of time. **Line 20**: `WEEK = timedelta(days=7)`.
- **Lines 23 to 38**: `ServiceMetrics`, a frozen dataclass with the results for one service over a window: counts of deployments, `empty_deploys` (deployments with no commit; they do not count), `deploys_per_week`, then four optional measures. `float | None` means "a float, or `None` (nothing)": a service with no failures has no recovery time. `refused` counts deployments blocked before they ran because the image was unsigned.
- **Lines 41 to 47**: `LeadTime` bundles one lead time with the two events it is the difference of, so a number can be traced to its source.

```python
def _in_window(event: Event, start: datetime, end: datetime) -> bool:
    return start <= event.ts < end


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def lead_times(events: Iterable[Event], service: str) -> list[LeadTime]:
    """Every commit of `service` that reached a deployment, with its lead time."""
    commits = {event.ref: event for event in events if event.service == service and event.type is EventType.COMMIT}
    result = []
    for event in events:
        if event.service == service and event.type is EventType.DEPLOY:
            for commit_ref in parse_deploy_ref(event.ref).commits:
                commit = commits.get(commit_ref)
                if commit is not None:
                    result.append(LeadTime(commit, event, (event.ts - commit.ts).total_seconds() / 3600))
    return result


def trace_lead_time(events: Sequence[Event], service: str, commit_ref: str) -> LeadTime:
    """The lead time of one commit and the two events behind it."""
    for lead in lead_times(events, service):
        if lead.commit.ref == commit_ref:
            return lead
    raise UnknownCommitError(f"{service}: no commit {commit_ref!r} with a deployment")
```

- **Lines 50 to 51**, `_in_window`: `start <= event.ts < end` is a chained comparison: at or after the start, strictly before the end.
- **Lines 54 to 55**, `_median`: `statistics.median(values) if values else None`: an empty list has no median.
- **Lines 58 to 68**, `lead_times`: a **dictionary comprehension** builds `{commit ref: its commit event}` for this service. For every `deploy` event of the service, for every commit in its ref, look the commit up (`commits.get(commit_ref)` returns `None` if missing) and, if found, add a `LeadTime` of `(event.ts - commit.ts).total_seconds() / 3600` hours. Subtracting two datetimes gives a `timedelta`; `.total_seconds()` makes it a number.
- **Lines 71 to 76**, `trace_lead_time`: the lead time of one named commit or `UnknownCommitError`.

```python
def compute(events: Sequence[Event], service: str, start: datetime, end: datetime) -> ServiceMetrics:
    """The metrics of one service for deployments inside `[start, end)`."""
    own = [event for event in events if event.service == service]
    deploys = [event for event in own if event.type is EventType.DEPLOY and _in_window(event, start, end)]
    real = [event for event in deploys if parse_deploy_ref(event.ref).commits]
    ids = {parse_deploy_ref(event.ref).deployment: event for event in real}
    failures = [event for event in own if event.type is EventType.FAILED and event.ref in ids]
    recoveries = defaultdict(list)
    for event in own:
        if event.type is EventType.RECOVERED:
            recoveries[event.ref].append(event.ts)
    recovery_minutes: list[float] = []
    open_failures = 0
    for failure in failures:
        later = [ts for ts in recoveries[failure.ref] if ts >= failure.ts]
        if later:
            recovery_minutes.append((min(later) - failure.ts).total_seconds() / 60)
        else:
            open_failures += 1
    window_leads = [lead.hours for lead in lead_times(own, service) if _in_window(lead.deploy, start, end)]
    weeks = (end - start) / WEEK
    return ServiceMetrics(
        service=service,
        window_start=start,
        window_end=end,
        deploys=len(real),
        empty_deploys=len(deploys) - len(real),
        deploys_per_week=len(real) / weeks if weeks else 0.0,
        median_lead_time_hours=_median(window_leads),
        change_fail_rate=len({failure.ref for failure in failures}) / len(real) if real else None,
        median_recovery_minutes=_median(recovery_minutes),
        median_batch_size=_median([float(len(parse_deploy_ref(event.ref).commits)) for event in real]),
        open_failures=open_failures,
        refused=sum(
            1
            for event in own
            if event.type is EventType.FAILED and event.detail == "signature" and start <= event.ts < end
        ),
    )
```

`compute` is the heart.

- **Lines 81 to 84**: keep this service's events; its `deploy` events inside the window; the "real" deployments among them (`parse_deploy_ref(event.ref).commits` is a non-empty tuple, which counts as true); and a dictionary from deployment id to event.
- **Line 85**: `failures` are `failed` events whose `ref` is one of those real deployments. **Lines 86 to 97**: `recoveries` maps a deployment id to the times it was recovered. For each failure, the recoveries at or after the failure time are `later`; if there are any, the recovery time in minutes is `(min(later) - failure.ts).total_seconds() / 60`; if none, the failure is still `open`.
- **Line 98**: the lead times of deployments inside the window, as hours. **Line 99**: `weeks = (end - start) / WEEK` divides one `timedelta` by another and gives a number.
- **Lines 100 to 117** build the result: `deploys_per_week=len(real) / weeks if weeks else 0.0`; the median lead time; the change fail rate as `len({failure.ref for failure in failures}) / len(real)` (a **set comprehension** `{...}` counts each failed deployment once); the median recovery; the median batch size (commits per deployment); open failures; and `refused`, counted with `sum(1 for event in own if ...)` (add 1 for each matching event) for `failed` events whose detail is `signature`.

```python
def services(events: Iterable[Event]) -> list[str]:
    """The services that have any event, sorted."""
    return sorted({event.service for event in events})


def window_of(events: Sequence[Event]) -> tuple[datetime, datetime]:
    """The data's own window: midnight of the first day, in whole weeks, up to the week of the last event."""
    first = min(event.ts for event in events)
    last = max(event.ts for event in events)
    start = first.replace(hour=0, minute=0, second=0, microsecond=0)
    weeks = max(1, -(-(last - start) // WEEK))
    return start, start + weeks * WEEK


def weekly(events: Sequence[Event], start: datetime, end: datetime) -> list[tuple[int, list[ServiceMetrics]]]:
    """Per week (counted from `start`), the metrics of every service."""
    table = []
    index = 1
    cursor = start
    while cursor < end:
        table.append((index, [compute(events, name, cursor, cursor + WEEK) for name in services(events)]))
        cursor += WEEK
        index += 1
    return table
```

- `services` returns the sorted distinct service names (`sorted({...})`).
- `window_of`: the data's own window. `first.replace(hour=0, minute=0, second=0, microsecond=0)` is midnight of the first day. `weeks = max(1, -(-(last - start) // WEEK))`: `//` divides and rounds down; negating twice (`-(-x // y)`) rounds *up*, so partial weeks count as whole ones; `max(1, ...)` ensures at least one week.
- `weekly`: for each week from the start, the metrics of every service, numbering weeks from 1.

### `src/goldenpath/domain/rules.py`: the golden-path contract as code

```python
"""The golden-path contract as checks: what a generated repository must keep, whatever a team changes.

Three things cannot be turned off, each with the reason that gets it a defender when someone finds it annoying:

1. Required checks on `main`: a red `main` stops everyone, so it is a shared problem.
2. Signed artifacts, verified before deploy: we must know that what runs is what CI built.
3. Short-lived deploy credentials from the CI identity (OIDC): a stored key leaks, and a leaked key lasts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

REQUIRED_CHECKS: Final = ("lint", "test", "release")
_PINNED: Final = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
_MOVING: Final = re.compile(r"(:latest\b|@(main|master|latest)\b)")
_CREDENTIAL_PATTERNS: Final = {
    "an AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "an AWS secret access key": re.compile(r"aws_secret_access_key\s*[:=]\s*\S+", re.IGNORECASE),
    "a private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "a GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "a stored cloud or registry secret in the workflow": re.compile(
        r"secrets\.[A-Z0-9_]*(ACCESS_KEY|SECRET_KEY|PRIVATE_KEY|PASSWORD|CLIENT_SECRET|SERVICE_ACCOUNT)[A-Z0-9_]*"
    ),
}


@dataclass(frozen=True, slots=True)
class Finding:
    """One violation of the contract: a stable code, the control it breaks, and what to change."""

    code: str
    control: str
    message: str


def _steps(document: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    return [(job_id, step) for job_id, job in document.get("jobs", {}).items() for step in job.get("steps", [])]


```

- **Lines 1 to 8**: the docstring states the three rules nobody may turn off: required checks on `main`; signed artifacts verified before deploy; short-lived deploy credentials from the CI identity.
- **Line 17**: `REQUIRED_CHECKS = ("lint", "test", "release")`. **Line 18**, `_PINNED`: a GitHub action reference must look like `owner/name@` followed by exactly 40 hexadecimal characters (a full commit id). **Line 19**, `_MOVING`: `:latest` or `@main`, `@master`, `@latest`.
- **Lines 20 to 28**: `_CREDENTIAL_PATTERNS` is a dictionary from a description to a pattern that finds something that looks like a long-lived secret: an AWS access key id (`AKIA` plus 16 capitals/digits), an AWS secret-key assignment, a private-key header (`-----BEGIN ... PRIVATE KEY-----`), a GitHub token (`gh` plus a letter, then 36 or more characters), or a workflow that uses a stored secret with a name like `..._PASSWORD` or `..._ACCESS_KEY`. `re.IGNORECASE` ignores letter case.
- **Lines 31 to 37**: `Finding(code, control, message)`, one violation. **Lines 40 to 41**: `_steps` lists every `(job id, step)` pair of a workflow with a nested comprehension (two `for` parts).

```python
def check_workflow(document: Mapping[str, Any]) -> list[Finding]:
    """Check a parsed workflow against the three non-negotiables and the pinning rule."""
    findings: list[Finding] = []
    steps = _steps(document)
    commands = "\n".join(str(step.get("run", "")) for _, step in steps)
    for job_id, step in steps:
        used = step.get("uses")
        if used and not used.startswith("./") and not _PINNED.match(used):
            findings.append(
                Finding("GP-PIN", "supply chain", f"{used!r} in job {job_id!r} is not pinned to a full commit SHA")
            )
        if _MOVING.search(str(used or "") + str(step.get("run", ""))):
            findings.append(
                Finding("GP-MOVING", "supply chain", f"job {job_id!r} uses a moving name (latest, main or master)")
            )
    if "make sign" not in commands and "cosign sign" not in commands:
        findings.append(Finding("GP-SIGN", "signed artifacts", "no step signs the artifact"))
    if "make verify" not in commands and "cosign verify" not in commands:
        findings.append(Finding("GP-VERIFY", "signed artifacts", "no step verifies the signature before deploy"))
    release_permissions = {}
    for job in document.get("jobs", {}).values():
        if "release" in str(job.get("name", "")) or any(
            "make release" in str(s.get("run", "")) for s in job.get("steps", [])
        ):
            release_permissions = job.get("permissions", {})
    if release_permissions.get("id-token") != "write":
        findings.append(
            Finding(
                "GP-OIDC",
                "short-lived credentials",
                "the release job does not ask for an identity token (id-token: write)",
            )
        )
    top = document.get("permissions")
    if not isinstance(top, dict) or top.get("contents") != "read" or "id-token" in top:
        findings.append(
            Finding(
                "GP-PERMS",
                "short-lived credentials",
                "top-level permissions must be contents: read only; grant id-token per job",
            )
        )
    return findings
```

`check_workflow(document)` returns a list of findings:

- **Lines 49 to 58**: for each step, a `uses:` that is not a local path (`./...`) and does not match `_PINNED` gives **GP-PIN**; any moving name gives **GP-MOVING**.
- **Lines 59 to 62**: **GP-SIGN** if no step contains `make sign` or `cosign sign`; **GP-VERIFY** if none contains `make verify` or `cosign verify`.
- **Lines 63 to 76**: find the release job (its name contains "release", or a step runs `make release`) and read its `permissions`; **GP-OIDC** if `id-token` is not `write`. (The OIDC identity token is explained in [oidc-identity-tokens.md](oidc-identity-tokens.md).)
- **Lines 77 to 85**: **GP-PERMS** if the workflow's top-level permissions are not exactly `contents: read` or if `id-token` appears at the top level: the token must be granted per job, not for everything.

```python
def check_protection(payload: Mapping[str, Any]) -> list[Finding]:
    """The branch-protection payload must require the checks, strictly, for administrators too."""
    findings = []
    checks = payload.get("required_status_checks") or {}
    missing = [name for name in REQUIRED_CHECKS if name not in checks.get("contexts", [])]
    if missing:
        findings.append(Finding("GP-CHECKS", "required checks", f"required checks missing: {', '.join(missing)}"))
    if not checks.get("strict"):
        findings.append(
            Finding("GP-STRICT", "required checks", "the branch must be required to be up to date (strict)")
        )
    if not payload.get("enforce_admins"):
        findings.append(Finding("GP-ADMINS", "required checks", "the rules must apply to administrators too"))
    if not payload.get("required_pull_request_reviews"):
        findings.append(Finding("GP-PR", "required checks", "a pull request must be required before merging"))
    return findings


def scan_for_credentials(files: Mapping[str, str]) -> list[Finding]:
    """Search text files for what a long-lived credential looks like."""
    findings = []
    for path, text in sorted(files.items()):
        for what, pattern in _CREDENTIAL_PATTERNS.items():
            if pattern.search(text):
                findings.append(Finding("GP-SECRET", "short-lived credentials", f"{path} contains {what}"))
    return findings


def unreplaced_placeholders(files: Mapping[str, str]) -> list[Finding]:
    """A generated repository must not still hold a `__NAME__`-style placeholder."""
    return [
        Finding("GP-PLACEHOLDER", "template", f"{path} still contains a placeholder")
        for path, text in sorted(files.items())
        if re.search(r"__[A-Z_]+__", text)
    ]


def summarize(findings: Sequence[Finding]) -> str:
    """One line per finding, or `conforms` when there are none."""
    if not findings:
        return "conforms to the golden path contract"
    return "\n".join(f"{finding.code}  [{finding.control}]  {finding.message}" for finding in findings)
```

- `check_protection(payload)`: the branch-protection JSON must list `lint`, `test`, `release` as required checks (**GP-CHECKS** names the missing ones), must have `strict` (**GP-STRICT**), `enforce_admins` (**GP-ADMINS**) and a required pull-request review (**GP-PR**).
- `scan_for_credentials(files)`: for every text file and every credential pattern, a hit is **GP-SECRET** naming the file and what it looks like.
- `unreplaced_placeholders(files)`: any `__NAME__`-style text (`re.search(r"__[A-Z_]+__", text)`) left in a generated file is **GP-PLACEHOLDER**.
- `summarize(findings)`: `conforms to the golden path contract` when empty, else one line per finding: `CODE  [control]  message`.

### `src/goldenpath/domain/catalog.py`: who owns a service

```python
"""The service catalog entry every generated service gets, and the rule that its owner is a team."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, Final

from goldenpath.domain.errors import InvalidCatalogEntryError

LIFECYCLES: Final = ("experimental", "production", "deprecated")
_NAME: Final = re.compile(r"^[a-z][a-z0-9-]{1,38}$")
_TEAM: Final = re.compile(r"^team-[a-z][a-z0-9-]{1,30}$")


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """`catalog-info.yaml`: who owns the service, where its runbook is and what it promises."""

    name: str
    owner: str
    lifecycle: str
    runbook: str
    slo: str

    def as_mapping(self) -> dict[str, str]:
        """The entry as the mapping written to YAML."""
        return {
            "name": self.name,
            "owner": self.owner,
            "lifecycle": self.lifecycle,
            "runbook": self.runbook,
            "slo": self.slo,
        }
```

- **Line 8**: `Any` is the type hint for "anything". **Line 12**: `LIFECYCLES` is the tuple of allowed lifecycle words. **Lines 13 and 14**: two patterns, a service name and a team name (`team-` plus a lowercase letter and up to 30 more letters, digits or dashes).
- **Lines 17 to 35**: `CatalogEntry` with five fields and a method `as_mapping()` that returns them as a dictionary (to be written as YAML).

```python
def validate(entry: CatalogEntry, teams: Collection[str]) -> CatalogEntry:
    """Return the entry when it keeps the contract; raise `InvalidCatalogEntryError` naming the first broken rule."""
    if not _NAME.match(entry.name):
        raise InvalidCatalogEntryError(f"name must be 2-39 characters of a-z, 0-9 and '-', got {entry.name!r}")
    if not _TEAM.match(entry.owner):
        raise InvalidCatalogEntryError(f"owner must be a team named team-<name>, not a person: {entry.owner!r}")
    if entry.owner not in teams:
        raise InvalidCatalogEntryError(f"owner {entry.owner!r} is not a registered team ({', '.join(sorted(teams))})")
    if entry.lifecycle not in LIFECYCLES:
        raise InvalidCatalogEntryError(f"lifecycle must be one of {', '.join(LIFECYCLES)}, got {entry.lifecycle!r}")
    if not entry.runbook.startswith("https://"):
        raise InvalidCatalogEntryError("runbook must be an https:// link")
    if not entry.slo.strip():
        raise InvalidCatalogEntryError("slo must say what the service promises")
    return entry


def from_mapping(data: Mapping[str, Any]) -> CatalogEntry:
    """Build an entry from parsed YAML; a missing key is an error that names it."""
    try:
        return CatalogEntry(**{key: str(data[key]) for key in ("name", "owner", "lifecycle", "runbook", "slo")})
    except KeyError as missing:
        raise InvalidCatalogEntryError(f"catalog entry has no {missing.args[0]!r}") from None
```

- `validate(entry, teams)` checks in order and raises `InvalidCatalogEntryError` naming the first broken rule: the name's shape; the owner is shaped like `team-...` (a person is refused); the owner is in the list of registered teams (`entry.owner not in teams`); the lifecycle is allowed; the runbook starts with `https://`; the SLO (what the service promises) is not blank. `{', '.join(sorted(teams))}` lists the registered teams in the message.
- `from_mapping(data)`: `CatalogEntry(**{key: str(data[key]) for key in (...)})`. The two stars before a dictionary pass its pairs as keyword arguments. A missing key raises `KeyError`, which is caught (`except KeyError as missing`) and turned into `InvalidCatalogEntryError("catalog entry has no 'owner'")`.

### `src/goldenpath/domain/simulation.py`: a month of work, repeatable

```python
"""A month of simulated work for three teams, as delivery events. Deterministic for a seed.

The simulation is a model with stated assumptions, not a measurement: it encodes that a bigger change fails more
often and takes longer to recover from (`fail_base + fail_per_commit * size`, `recovery_base + recovery_per_commit *
size`). What it shows is what the metrics make visible when teams batch differently, which is step 6 of the lesson.
The events go through the same `record` use case as the pipeline's own.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from goldenpath.domain.events import Event, EventType, format_deploy_ref

START: Final = datetime(2026, 9, 7, tzinfo=UTC)  # a Monday


@dataclass(frozen=True, slots=True)
class TeamProfile:
    """How a team works: how often it commits, when it deploys, and how risky and slow to fix its changes are."""

    service: str
    commits_per_day: tuple[int, int]
    deploy_days: tuple[int, ...] | None  # weekdays (Mon=0) the team deploys on; None means after every merge
    fail_base: float
    fail_per_commit: float
    recovery_base_minutes: float
    recovery_per_commit_minutes: float


SMALL_CHANGES: Final = TeamProfile("orders", (2, 4), None, 0.04, 0.02, 15.0, 4.0)
BI_WEEKLY: Final = TeamProfile("search", (1, 3), (1, 3), 0.04, 0.025, 20.0, 12.0)
WEEKLY_BATCH: Final = TeamProfile("billing", (1, 3), (4,), 0.04, 0.03, 30.0, 30.0)
TEAMS: Final = (SMALL_CHANGES, BI_WEEKLY, WEEKLY_BATCH)


def _at(day: datetime, hour: float) -> datetime:
    return day + timedelta(hours=hour)

```

- **Lines 1 to 7**: the docstring is honest: "a model with stated assumptions, not a measurement". A bigger change fails more often and takes longer to recover.
- **Line 11**: `import random`. A **random number generator** made with `random.Random(seed)` produces the same numbers every time for the same `seed`: that is what makes the simulation repeatable.
- **Line 18**: `START = datetime(2026, 9, 7, tzinfo=UTC)`: a Monday.
- **Lines 21 to 31**: `TeamProfile` describes how a team works: events per day (`tuple[int, int]` a minimum and maximum), the weekdays it deploys on (`None` meaning after every merge; Monday is 0), a base failure chance plus a chance per commit, and a base recovery time plus time per commit.
- **Lines 34 to 37**: three teams: `SMALL_CHANGES` (orders), `BI_WEEKLY` (search: Tuesday and Thursday, weekdays 1 and 3), `WEEKLY_BATCH` (billing: Friday, 4).

```python
def simulate_team(profile: TeamProfile, rng: random.Random, days: int = 28, start: datetime = START) -> list[Event]:
    """Events for one team over `days` days: working days only, commits during the day, deploys by the team's policy."""
    events: list[Event] = []
    pending: list[str] = []
    commit_count = 0
    deploy_count = 0
    for offset in range(days):
        day = start + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        todays: list[tuple[datetime, str]] = []
        for _ in range(rng.randint(*profile.commits_per_day)):
            commit_count += 1
            ref = f"{profile.service}-c{commit_count}"
            moment = _at(day, rng.uniform(9, 16))
            events.append(Event(moment, profile.service, EventType.COMMIT, ref))
            todays.append((moment, ref))
        deploy_times: list[tuple[datetime, list[str]]] = []
        if profile.deploy_days is None:
            for moment, ref in sorted(todays):
                deploy_times.append((moment + timedelta(hours=rng.uniform(0.5, 4)), [*pending, ref]))
                pending = []
        else:
            pending.extend(ref for _, ref in sorted(todays))
            if day.weekday() in profile.deploy_days and pending:
                deploy_times.append((_at(day, 12 + rng.uniform(0, 1)), pending))
                pending = []
        for moment, commits in deploy_times:
            deploy_count += 1
            deployment = f"{profile.service}-d{deploy_count}"
            events.append(Event(moment, profile.service, EventType.DEPLOY, format_deploy_ref(deployment, commits)))
            size = len(commits)
            if rng.random() < min(0.9, profile.fail_base + profile.fail_per_commit * size):
                failed_at = moment + timedelta(minutes=rng.uniform(2, 15))
                events.append(Event(failed_at, profile.service, EventType.FAILED, deployment, "health-check"))
                minutes = (profile.recovery_base_minutes + profile.recovery_per_commit_minutes * size) * rng.uniform(
                    0.7, 1.4
                )
                events.append(
                    Event(failed_at + timedelta(minutes=minutes), profile.service, EventType.RECOVERED, deployment)
                )
    return events


def simulate(seed: int, days: int = 28, teams: tuple[TeamProfile, ...] = TEAMS) -> list[Event]:
    """Every team's events, in time order. The same seed always gives the same month."""
    rng = random.Random(seed)  # noqa: S311 - a simulation, not a secret
    events = [event for team in teams for event in simulate_team(team, rng, days)]
    return sorted(events, key=lambda event: (event.ts, event.service, event.type.value))
```

- **Lines 44 to 85**, `simulate_team`: for each of `days` days from the start, skip weekends (`day.weekday() >= 5`); draw how many commits (`rng.randint(*profile.commits_per_day)`; the star unpacks the pair into two arguments), give each a random time between 09:00 and 16:00 and a ref like `orders-c3`, and record a `commit` event. Then decide deployments by the team's policy: a team that deploys after every merge deploys each commit 0.5 to 4 hours later together with anything pending; a team with deploy days collects commits in `pending` and deploys them all at about noon on its days. Each deployment gets an id like `orders-d2` and a `deploy` event whose ref lists the commits (`format_deploy_ref`).
- **Lines 75 to 84**: with probability `min(0.9, fail_base + fail_per_commit * size)` the deployment fails (`rng.random() < ...`), 2 to 15 minutes later (`failed` event with detail `health-check`), and recovers after `(recovery_base + recovery_per_commit * size) * rng.uniform(0.7, 1.4)` minutes (`recovered` event). Bigger batches therefore fail more and recover slower.
- **Lines 88 to 92**, `simulate(seed, days, teams)`: `rng = random.Random(seed)  # noqa: S311 ...` (the comment silences a lint warning about unsafe randomness, because this is a simulation, not a secret), gathers every team's events and returns them `sorted(events, key=lambda event: (event.ts, event.service, event.type.value))`: sort by time, then service, then type.

### `src/goldenpath/application/`: use cases and the ports they need

```python
"""What the use cases need from the outside world."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Protocol

from goldenpath.domain.catalog import CatalogEntry
from goldenpath.domain.events import Event
from goldenpath.domain.rules import Finding


class EventSink(Protocol):
    """Anything events can be sent to: the store itself, or the collector in front of it."""

    def append(self, events: Iterable[Event]) -> int:
        """Send events; return how many were new. Sending the same event twice must not duplicate it."""


class EventStore(EventSink, Protocol):
    """Where delivery events are kept and read back."""

    def all(self) -> list[Event]:
        """Every event, oldest first."""

    def clear(self) -> None:
        """Delete every event (the simulation starts from an empty store)."""


class TemplateRenderer(Protocol):
    """Turns the template folder into a new repository folder."""

    def render(self, destination: Path, substitutions: Mapping[str, str]) -> list[str]:
        """Copy the template with placeholders replaced; return the relative paths written."""


class Catalog(Protocol):
    """The service catalog and the registered teams."""

    def teams(self) -> frozenset[str]:
        """The teams that may own a service."""

    def register(self, entry: CatalogEntry) -> None:
        """Add or replace an entry."""

    def entries(self) -> list[CatalogEntry]:
        """Every registered entry."""


class Repositories(Protocol):
    """Creates the Git repository of a new service."""

    def create(self, directory: Path, name: str, message: str) -> str:
        """Initialize, commit everything and publish; return the commit id."""


class Auditor(Protocol):
    """Checks a generated repository against the golden-path contract."""

    def audit(self, directory: Path) -> list[Finding]:
        """Findings, empty when the repository conforms."""
```

A **port** is a list of methods a use case needs from the outside world; the code that provides them is an **adapter**. `class EventSink(Protocol)` lists the methods an object must have to count as an event sink; any object with those methods qualifies, without saying so. `EventSink` has `append(events) -> int`: send events and return how many were new. `EventStore(EventSink, Protocol)` adds `all()` and `clear()`. The other ports: `TemplateRenderer.render`, `Catalog` (`teams`, `register`, `entries`), `Repositories.create` (publish a new repository and return the commit id), `Auditor.audit`. The method bodies are only docstrings: a port declares, an adapter implements.

```python
"""Record delivery events and read them back."""

from __future__ import annotations

from collections.abc import Iterable

from goldenpath.application.ports import EventSink, EventStore
from goldenpath.domain.events import Event, EventType, parse_deploy_ref


def record(sink: EventSink, events: Iterable[Event]) -> int:
    """Append events; duplicates are ignored. Returns how many were new."""
    return sink.append(events)


def list_deployments(store: EventStore, service: str) -> list[tuple[str, str, tuple[str, ...]]]:
    """Every production deployment of a service as `(deployed at, deployment id, commits)`, oldest first (step 4)."""
    rows = []
    for event in store.all():
        if event.service == service and event.type is EventType.DEPLOY:
            parsed = parse_deploy_ref(event.ref)
            rows.append((event.ts.strftime("%Y-%m-%d %H:%M"), parsed.deployment, parsed.commits))
    return rows
```

- `record(sink, events)` hands events to any sink and returns how many were new: duplicates are ignored. `list_deployments(store, service)` returns, oldest first, `(time, deployment id, commits)` for every deployment of a service; `event.ts.strftime("%Y-%m-%d %H:%M")` formats a time as text.

```python
"""Compute the metrics and trace a value back to its events."""

from __future__ import annotations

from datetime import datetime

from goldenpath.application.ports import EventStore
from goldenpath.domain import metrics
from goldenpath.domain.errors import DomainError
from goldenpath.domain.events import Event
from goldenpath.domain.metrics import LeadTime, ServiceMetrics


class NoEventsError(DomainError):
    """There is nothing to measure yet."""


SAMPLE_PREFIX = "sample-"


def _events(store: EventStore, include_samples: bool) -> list[Event]:
    """Every event, without the lesson's sample services (`sample-orders`, `sample-billing`) unless asked."""
    return [event for event in store.all() if include_samples or not event.service.startswith(SAMPLE_PREFIX)]


def summary(
    store: EventStore, start: datetime | None = None, end: datetime | None = None, include_samples: bool = False
) -> list[ServiceMetrics]:
    """One row per service over the data's own window, or over `[start, end)` when both are given."""
    events = _events(store, include_samples)
    if not events:
        raise NoEventsError("the event store is empty: run `make simulate` or deploy a service first")
    window = (start, end) if start and end else metrics.window_of(events)
    return [metrics.compute(events, name, window[0], window[1]) for name in metrics.services(events)]


def per_week(store: EventStore, include_samples: bool = False) -> list[tuple[int, list[ServiceMetrics]]]:
    """The metrics of every service for every week of the data."""
    events = _events(store, include_samples)
    if not events:
        raise NoEventsError("the event store is empty: run `make simulate` or deploy a service first")
    start, end = metrics.window_of(events)
    return metrics.weekly(events, start, end)


def trace(store: EventStore, service: str, commit: str) -> LeadTime:
    """The lead time of one commit with the commit event and the deployment event behind it."""
    return metrics.trace_lead_time(store.all(), service, commit)
```

- `NoEventsError` (line 14) is raised when there is nothing to measure. `SAMPLE_PREFIX = "sample-"` names the lesson's sample services; `_events` drops them unless asked. `summary` computes one row per service over the data's own window; `per_week` one table per week; `trace` finds one commit's lead time. Each raises `NoEventsError` with a helpful message if the store is empty.

```python
"""One command: a new service with a pipeline, a catalog entry and an owner, checked against the contract."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from goldenpath.application.ports import Auditor, Catalog, Repositories, TemplateRenderer
from goldenpath.domain import catalog as catalog_rules
from goldenpath.domain.catalog import CatalogEntry
from goldenpath.domain.errors import DomainError
from goldenpath.domain.rules import Finding


class NonConformingServiceError(DomainError):
    """The generated repository does not keep the golden-path contract; nothing was published."""

    def __init__(self, findings: list[Finding]) -> None:
        """Keep the findings so the caller can print them."""
        super().__init__("the generated repository breaks the contract")
        self.findings = findings


@dataclass(frozen=True, slots=True)
class GeneratedService:
    """What the command produced and where the minutes went."""

    entry: CatalogEntry
    directory: Path
    commit: str
    files: tuple[str, ...]
    timings: dict[str, float] = field(default_factory=dict)


class ServiceGenerator:
```

- **Lines 17 to 23**: `NonConformingServiceError` carries the list of findings (`self.findings = findings`) so the command can print them. **Lines 26 to 34**: `GeneratedService` is the result: the catalog entry, the folder, the commit, the file names and the timings.

```python
class ServiceGenerator:
    """Validates the owner, renders the template, audits it, registers the catalog entry, publishes the repository."""

    def __init__(
        self,
        renderer: TemplateRenderer,
        catalog: Catalog,
        repositories: Repositories,
        auditor: Auditor,
        platform_ref: str,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """`platform_ref` is the platform commit the service is generated from; it is written into the repository."""
        self._renderer = renderer
        self._catalog = catalog
        self._repositories = repositories
        self._auditor = auditor
        self._platform_ref = platform_ref
        self._clock = clock

    def generate(self, name: str, owner: str, destination: Path, runbook_base: str) -> GeneratedService:
        """Create the service. A person as owner, or a repository that fails the audit, is refused before publishing."""
        timings: dict[str, float] = {}
        started = self._clock()
        entry = catalog_rules.validate(
            CatalogEntry(name, owner, "production", f"{runbook_base}/{name}", "availability 99.9% over 30 days"),
            self._catalog.teams(),
        )
        files = self._renderer.render(
            destination,
            {
                "__NAME__": name,
                "__OWNER__": owner,
                "__RUNBOOK__": entry.runbook,
                "__PLATFORM_REF__": self._platform_ref,
            },
        )
        timings["render"] = self._clock() - started
        findings = self._auditor.audit(destination)
        if findings:
            raise NonConformingServiceError(findings)
        timings["audit"] = self._clock() - started - timings["render"]
        self._catalog.register(entry)
        commit = self._repositories.create(
            destination, name, f"Create {name} from golden path {self._platform_ref[:7]}"
        )
        timings["publish"] = self._clock() - started - timings["render"] - timings["audit"]
        return GeneratedService(entry, destination, commit, tuple(files), timings)
```

`ServiceGenerator.generate` is the one command "a new service with a pipeline, a catalog entry and an owner".

- **Lines 40 to 55**: `__init__` receives every collaborator (a renderer, a catalog, a repositories adapter, an auditor, the platform commit id and a clock) and stores them: **dependency injection**, so tests pass fakes.
- **Lines 61 to 64**: build the entry (`production`, the runbook link, the SLO text) and `catalog_rules.validate` it **before anything is created**: a person as owner is refused here.
- **Lines 65 to 74**: render the template into the destination with four substitutions: `__NAME__`, `__OWNER__`, `__RUNBOOK__`, `__PLATFORM_REF__`.
- **Lines 75 to 78**: audit the result. If there are findings raise `NonConformingServiceError` and **nothing is published**.
- **Lines 79 to 84**: register the catalog entry; create the Git repository and push; record how long each phase took; return the result.

### `src/goldenpath/infrastructure/`: the adapters

```python
"""Configuration from the environment, validated once at startup (twelve-factor)."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
_HOST = re.compile(r"^[\w.\-]+$")


class ConfigurationError(ValueError):
    """An environment variable is missing or has an unusable value."""


def _text(environ: Mapping[str, str], name: str, default: str | None = None) -> str:
    value = environ.get(name, default if default is not None else "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be set and not empty")
    return value


def _port(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = environ.get(name, str(default)).strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ConfigurationError(f"{name} must be a port number, got {raw!r}")
    return int(raw)


@dataclass(frozen=True, slots=True)
class Settings:
```

Configuration comes from the environment ([dotenv.md](dotenv.md)). `_text` reads a variable, strips spaces and raises `ConfigurationError` naming the variable if the result is empty. `_port` accepts only digits and a value from 1 to 65535. (`raw.isdigit()` is true for text made only of digits.)

```python
    """Everything the programs read from the environment. See .env.example for each variable."""

    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    log_level: str
    collector_port: int
    collector_url: str
    collector_token: str
    workdir: Path
    runbook_base: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None, need_database: bool = True) -> Settings:
        """Read and validate. Passwords and tokens have no default: they must come from the environment."""
        env = os.environ if environ is None else environ
        host = _text(env, "POSTGRES_HOST", "localhost")
        if not _HOST.match(host):
            raise ConfigurationError(f"POSTGRES_HOST must be a host name or address, got {host!r}")
        level = _text(env, "LOG_LEVEL", "INFO").upper()
        if level not in _LEVELS:
            raise ConfigurationError(f"LOG_LEVEL must be one of {sorted(_LEVELS)}, got {level!r}")
        collector_port = _port(env, "COLLECTOR_PORT", 55442)
        return cls(
            postgres_host=host,
            postgres_port=_port(env, "POSTGRES_PORT", 5432),
            postgres_db=_text(env, "POSTGRES_DB", "events"),
            postgres_user=_text(env, "POSTGRES_USER", "platform"),
            postgres_password=_text(env, "POSTGRES_PASSWORD") if need_database else env.get("POSTGRES_PASSWORD", ""),
            log_level=level,
            collector_port=collector_port,
            collector_url=_text(env, "COLLECTOR_URL", f"http://127.0.0.1:{collector_port}"),
            collector_token=env.get("COLLECTOR_TOKEN", "").strip(),
            workdir=Path(_text(env, "GOLDENPATH_WORKDIR", ".local")),
            runbook_base=_text(env, "RUNBOOK_BASE", "https://wiki.example.com/runbooks"),
        )

    @property
    def dsn(self) -> str:
        """A libpq connection URI. Never log this: it holds the password."""
        return (
            f"postgresql://{quote(self.postgres_user, safe='')}:{quote(self.postgres_password, safe='')}"
            f"@{self.postgres_host}:{self.postgres_port}/{quote(self.postgres_db, safe='')}"
        )
```

- `Settings` is a frozen dataclass with eleven fields: the database's host, port, name, user and password; the log level; the collector's port, URL and token; the working folder; the runbook base URL.
- `from_env(cls, environ=None, need_database=True)` reads them. The database password is required only when `need_database` is true, so commands like `new-service` and `audit` run with no database. The collector token has no default (`env.get("COLLECTOR_TOKEN", "").strip()` is empty if unset), and the collector refuses to start without one. The `dsn` property builds `postgresql://user:password@host:port/db` with each part percent-encoded by `quote(x, safe='')` so special characters cannot break the URL.

```python
"""Structured logging: one logfmt line per event (`ts=... level=... logger=... msg=... key=value`)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, TextIO


def _quote(value: object) -> str:
    text = str(value)
    return json.dumps(text) if not text or any(char in text for char in ' ="\n') else text


class LogfmtFormatter(logging.Formatter):
    """Format a log record as one logfmt line, with the record's extra fields as key=value pairs."""

    def format(self, record: logging.LogRecord) -> str:
        """Render `record`; the exception, when there is one, goes on the same line."""
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds")
        parts = [
            f"ts={timestamp}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f"msg={_quote(record.getMessage())}",
        ]
        parts.extend(f"{key}={_quote(value)}" for key, value in getattr(record, "fields", {}).items())
        if record.exc_info:
            parts.append(f"exc={_quote(self.formatException(record.exc_info))}")
        return " ".join(parts)


def fields(**values: Any) -> dict[str, Any]:
    """Use as `logger.info("message", extra=fields(service=...))` to attach key=value pairs."""
    return {"fields": values}


def configure_logging(level: str, stream: TextIO | None = None) -> None:
    """Send every log record to `stream` (stderr by default) as logfmt. Safe to call twice."""
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(LogfmtFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
```

Logging is one `key=value` line per event ("logfmt"). `LogfmtFormatter.format` builds a list of pieces (`ts`, `level`, `logger`, `msg`, any extra fields, and the exception if there is one) and joins them with spaces; `_quote` wraps a value in quotes (using `json.dumps`) when it is empty or contains a space, `=`, a quote or a newline. `fields(**values)` collects keyword arguments into a dictionary for `extra=`. `configure_logging(level, stream)` installs one handler on the root logger, replacing existing ones so it is safe to call twice. (`configure_logging` is called once from `main`, see below.)

```python
"""The `EventStore` port on PostgreSQL (sql/001_schema.sql creates the table)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import psycopg

from goldenpath.domain.events import Event, EventType

_CONNECT_TIMEOUT_SECONDS = 60


class PostgresEventStore:
    """Opens a short-lived connection per call. A duplicate event (same service, type, ref and time) is ignored."""

    def __init__(self, dsn: str) -> None:
        """`dsn` is a libpq connection URI."""
        self._dsn = dsn

    def _connect(self) -> psycopg.Connection[tuple[Any, ...]]:
        return psycopg.connect(self._dsn, connect_timeout=_CONNECT_TIMEOUT_SECONDS)

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

- **Line 12**: a generous 60-second connect timeout, because a loaded laptop can take many seconds to accept a connection. **Lines 25 to 36**, `append`: `with self._connect() as connection, connection.cursor() as cursor:` opens a connection and a **cursor** (an object that runs statements) in one `with` and commits at the end. For each event, `cursor.execute("INSERT INTO events (...) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", (values))` inserts it with **placeholders** (the values travel separately, so they cannot be read as SQL); `ON CONFLICT DO NOTHING` ignores an event that is already there; `cursor.rowcount` is 1 if a row was added and 0 if ignored, so `inserted` counts only new events ([psycopg.md](psycopg.md)). **Lines 38 to 42**, `all`: select all events in time order and rebuild `Event` objects (`EventType(kind)` converts the text back to the enumeration). **Lines 44 to 47**, `clear`: `TRUNCATE events` deletes every row.

```python
"""Events in a CSV file: `ts,service,type,ref[,detail]`, the format of the lesson's sample."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from goldenpath.domain.events import Event, EventType, parse_timestamp


class CsvEventStore:
    """An `EventStore` on one CSV file. Reads are whole-file; fine for a sample and for tests."""

    def __init__(self, path: Path) -> None:
        """`path` is created on the first append."""
        self._path = path

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

    def clear(self) -> None:
        """Delete the file."""
        self._path.unlink(missing_ok=True)
```

- The same `EventStore` over a CSV file ([csv.md](csv.md)). `append` (19 to 32) reads the existing events into a **set** (`set(self.all())`; events are frozen so they can be members), keeps only the new ones (`event not in existing`), writes the header if the file is new, and writes one row per new event, formatting the time with `strftime("%Y-%m-%dT%H:%M:%S")`. `all` (34 to 49) reads rows with `csv.DictReader`, builds validated `Event`s (the sample file has no `detail` column, hence `row.get("detail") or ""`) and sorts them by time. `clear` (51 to 53) deletes the file; `unlink(missing_ok=True)` does not complain if it is already gone.

```python
"""The catalog as files: `catalog/teams.yaml` (committed) and one YAML file per registered service (generated state)."""

from __future__ import annotations

from pathlib import Path

import yaml

from goldenpath.domain.catalog import CatalogEntry, from_mapping


class FileCatalog:
    """Registered teams come from a committed file; registered services are written under `entities/`."""

    def __init__(self, teams_file: Path, entities_dir: Path) -> None:
        """Both paths may be missing until first use."""
        self._teams_file = teams_file
        self._entities_dir = entities_dir

    def teams(self) -> frozenset[str]:
        """The teams that may own a service."""
        data = yaml.safe_load(self._teams_file.read_text()) or {}
        return frozenset(str(team) for team in data.get("teams", []))

    def register(self, entry: CatalogEntry) -> None:
        """Write (or replace) the entry's file."""
        self._entities_dir.mkdir(parents=True, exist_ok=True)
        (self._entities_dir / f"{entry.name}.yaml").write_text(yaml.safe_dump(entry.as_mapping(), sort_keys=False))

    def entries(self) -> list[CatalogEntry]:
        """Every registered entry, by name."""
        if not self._entities_dir.exists():
            return []
        return [from_mapping(yaml.safe_load(path.read_text())) for path in sorted(self._entities_dir.glob("*.yaml"))]
```

- `FileCatalog` keeps the catalog as files ([yaml.md](yaml.md)). `teams()` (20 to 23) reads `catalog/teams.yaml` with `yaml.safe_load(...) or {}` (an empty file gives `None`, so `or {}` replaces it) and returns a `frozenset` of team names. `register(entry)` (25 to 28) creates the folder and writes `<name>.yaml` with `yaml.safe_dump(entry.as_mapping(), sort_keys=False)`; `sort_keys=False` keeps the keys in the order given. `entries()` (30 to 34) reads every `*.yaml` in the folder, sorted by file name.

```python
"""Render the template folder into a new repository folder, replacing placeholders in text files."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path

_SKIP = {"__pycache__", ".DS_Store"}


class FileTemplateRenderer:
    """Copies `template/` and replaces `__NAME__`-style placeholders. File modes are kept (scripts stay executable)."""

    def __init__(self, template: Path) -> None:
        """`template` is the folder holding the golden path."""
        self._template = template

    def render(self, destination: Path, substitutions: Mapping[str, str]) -> list[str]:
        """Write the template to `destination` (which must not exist); return the relative paths written."""
        if destination.exists():
            raise FileExistsError(f"{destination} already exists")
        written = []
        for source in sorted(self._template.rglob("*")):
            relative = source.relative_to(self._template)
            if source.is_dir() or _SKIP & set(relative.parts):
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            text = target.read_text()
            for placeholder, value in substitutions.items():
                text = text.replace(placeholder, value)
            target.write_text(text)
            written.append(relative.as_posix())
        return written
```

- **Lines 9 to 36**: `FileTemplateRenderer.render(destination, substitutions)` refuses to overwrite (`FileExistsError`) and walks `template/` with `rglob("*")` (every file and folder under it, sorted). It skips folders and `__pycache__`/`.DS_Store`, creates the target's folder, copies the file with `shutil.copy2` (which keeps the file's permissions, so scripts stay executable), reads it as text, replaces each placeholder with `text.replace(placeholder, value)` in a loop, writes it back, and collects the relative paths (`relative.as_posix()` uses forward slashes on every system).

```python
"""Create a new service's Git repository and publish it to a local bare remote (standing in for `gh repo create`)."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

AUTHOR = ("platform-bot", "platform-bot@example.test")


def _git(directory: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603
        ["git", "-c", f"user.name={AUTHOR[0]}", "-c", f"user.email={AUTHOR[1]}", *args],  # noqa: S607
        cwd=directory,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


class GitRepositories:
    """`create` runs `git init`, commits everything, creates `<remotes>/<name>.git` and pushes `main` to it."""

    def __init__(self, remotes: Path) -> None:
        """`remotes` is the folder that holds the bare repositories."""
        self._remotes = remotes

    def create(self, directory: Path, name: str, message: str) -> str:
        """Publish the repository; return the commit id."""
        remote = self._remotes / f"{name}.git"
        remote.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)  # noqa: S603, S607
        _git(directory, "init", "-q", "-b", "main")
        _git(directory, "add", "-A")
        _git(directory, "commit", "-q", "-m", message)
        _git(directory, "remote", "add", "origin", str(remote))
        _git(directory, "push", "-q", "origin", "main")
        return _git(directory, "rev-parse", "HEAD")


def commits_since(directory: Path, base: str | None) -> Sequence[str]:
    """Short ids of the commits after `base` (all of them when `base` is None), oldest first."""
    spec = f"{base}..HEAD" if base else "HEAD"
    return _git(directory, "rev-list", "--reverse", "--abbrev-commit", spec).split()
```

- `GitRepositories` publishes a new service's repository ([git.md](git.md)). `_git(directory, *args)` runs `git -c user.name=... -c user.email=... ARGS` in a folder with a fixed bot identity, so a commit works on a machine with no Git settings; `*args` collects any number of extra words, `*args` in the call spreads them. `create` makes a **bare** repository (`git init -q --bare -b main`), initialises the service's folder, `add -A`, `commit -q -m`, `remote add origin`, `push -q origin main`, and returns `rev-parse HEAD`. `commits_since(directory, base)` returns the short ids of the commits after `base` (`base..HEAD`), oldest first (`rev-list --reverse --abbrev-commit`); with `base` as `None` it is all of them.

```python
"""Audit a generated repository against the golden-path contract: reads its files, applies the domain's rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from goldenpath.application.ports import Catalog
from goldenpath.domain import catalog as catalog_rules
from goldenpath.domain import rules
from goldenpath.domain.errors import InvalidCatalogEntryError
from goldenpath.domain.rules import Finding

_SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}


def read_text_files(directory: Path) -> dict[str, str]:
    """Every text file under `directory` as `{relative path: text}`; binary files and VCS folders are skipped."""
    files: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if path.is_dir() or _SKIP_DIRS & set(relative.parts):
            continue
        try:
            files[relative.as_posix()] = path.read_text()
        except UnicodeDecodeError:
            continue
    return files


def load_workflow(text: str) -> dict[str, Any]:
    """Parse a workflow. PyYAML reads the key `on` as the boolean True; put it back under "on"."""
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise ValueError("a workflow must be a mapping")
    if True in document:
        document["on"] = document.pop(True)
    return document


class RepositoryAuditor:
    """Implements the `Auditor` port for a repository on disk."""

    def __init__(self, catalog: Catalog) -> None:
        """The catalog supplies the list of registered teams for the owner check."""
        self._catalog = catalog

    def audit(self, directory: Path) -> list[Finding]:
        """Findings, empty when the repository conforms."""
        files = read_text_files(directory)
        findings: list[Finding] = []
        workflows = sorted(
            path for path in files if path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))
        )
        if not workflows:
            findings.append(Finding("GP-NOWORKFLOW", "required checks", "the repository has no workflow"))
        for path in workflows:
            findings.extend(rules.check_workflow(load_workflow(files[path])))
        if "protection.json" in files:
            findings.extend(rules.check_protection(json.loads(files["protection.json"])))
        else:
            findings.append(Finding("GP-CHECKS", "required checks", "protection.json is missing"))
        findings.extend(self._catalog_findings(files))
        findings.extend(rules.scan_for_credentials(files))
        findings.extend(rules.unreplaced_placeholders(files))
        return findings

    def _catalog_findings(self, files: dict[str, str]) -> list[Finding]:
        if "catalog-info.yaml" not in files:
            return [Finding("GP-CATALOG", "catalog", "catalog-info.yaml is missing")]
        try:
            catalog_rules.validate(
                catalog_rules.from_mapping(yaml.safe_load(files["catalog-info.yaml"])), self._catalog.teams()
            )
        except InvalidCatalogEntryError as error:
            return [Finding("GP-CATALOG", "catalog", str(error))]
        return []
```

- **Lines 20 to 31**, `read_text_files`: every text file under a folder as `{relative path: text}`; folders such as `.git` and `.venv` are skipped; a file that is not text (`UnicodeDecodeError`) is skipped with `continue`.
- **Lines 34 to 41**, `load_workflow`: parses a workflow with `yaml.safe_load` and repairs YAML's reading of the key `on` as `True` ([yaml.md](yaml.md)).
- **Lines 44 to 80**, `RepositoryAuditor.audit(directory)`: read the files; find the workflows under `.github/workflows/`; if there are none, **GP-NOWORKFLOW**; check each workflow with `rules.check_workflow`; check `protection.json` if it exists (parsed with `json.loads`), else **GP-CHECKS**; check the catalog entry (`_catalog_findings`: missing file is **GP-CATALOG**; otherwise parse and `validate` it, turning an `InvalidCatalogEntryError` into a finding); scan for credentials; find leftover placeholders. It returns all findings.

```python
"""The pipeline's side of event recording: POST events to the collector with a bearer token."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterable

from goldenpath.domain.events import Event


class CollectorError(RuntimeError):
    """The collector refused or could not be reached."""


class CollectorEventSink:
    """An `EventSink` over HTTP. The token comes from the environment (`COLLECTOR_TOKEN`), never from code."""

    def __init__(self, url: str, token: str, timeout_seconds: float = 120.0) -> None:
        """`url` is the collector's base URL (http or https only)."""
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"url must start with http:// or https://, got {url!r}")
        self._url = url.rstrip("/")
        self._token = token
        self._timeout_seconds = timeout_seconds

    def append(self, events: Iterable[Event]) -> int:
        """Send events; return how many the collector accepted as new."""
        body = json.dumps(
            [
                {
                    "ts": event.ts.isoformat(),
                    "service": event.service,
                    "type": event.type.value,
                    "ref": event.ref,
                    "detail": event.detail,
                }
                for event in events
            ]
        ).encode()
        request = urllib.request.Request(  # noqa: S310 - scheme checked in __init__
            f"{self._url}/events",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                return int(json.loads(response.read())["accepted"])
        except urllib.error.HTTPError as error:
            raise CollectorError(
                f"the collector answered {error.code}: {error.read().decode(errors='replace').strip()}"
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise CollectorError(f"the collector could not be reached at {self._url}: {error}") from None
```

- **Lines 20 to 26**: the client takes a base URL and a token; the URL must start with `http://` or `https://` (`url.startswith((...))` accepts a tuple of options), `rstrip("/")` removes a trailing slash. **Lines 28 to 56**, `append`: `json.dumps([...])` turns a list of event dictionaries into JSON text (`event.ts.isoformat()` writes the time as text) and `.encode()` turns text into bytes; `urllib.request.Request(url, data=body, headers={...}, method="POST")` builds the request with the `Content-Type` and `Authorization: Bearer <token>` headers; `urllib.request.urlopen(request, timeout=...)` sends it. The reply is JSON: `int(json.loads(response.read())["accepted"])` is how many events were new. An `HTTPError` (the server answered an error status) becomes `CollectorError("the collector answered 401: ...")`; a network failure (`URLError`, `TimeoutError`, `OSError`) becomes `CollectorError("... could not be reached ...")`. The `# noqa: S310` comments silence a warning about opening URLs, justified by the scheme check in `__init__` ([http-server.md](http-server.md)).

```python
"""Run a generated service's own pipeline on this machine: the same make targets its workflow runs, each one timed.

The workflow in a generated repository calls `make lint`, `make test`, `make image`, `make sign`, `make attest`,
`make verify` and `make deploy`; this runs them in that order against a local registry, a local key and local compose.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class StepFailedError(RuntimeError):
    """A pipeline step exited non-zero; the message carries what it printed."""

    def __init__(self, step: str, output: str) -> None:
        """Keep the step's name and its output."""
        super().__init__(f"{step} failed:\n{output.strip()[-1500:]}")
        self.step = step
        self.output = output


@dataclass(frozen=True, slots=True)
class StepResult:
    """One timed step."""

    name: str
    seconds: float
    output: str


STEP_TIMEOUT_SECONDS = 3600  # a step normally takes seconds; a machine under heavy load can take many minutes


def _run(argv: Sequence[str], cwd: Path, env: Mapping[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603
            list(argv),
            cwd=cwd,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            timeout=STEP_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise StepFailedError(" ".join(argv), f"timed out after {STEP_TIMEOUT_SECONDS} seconds") from None


def run_steps(
    directory: Path, steps: Sequence[str], env: Mapping[str, str], variables: Mapping[str, Sequence[str]] | None = None
) -> list[StepResult]:
    """Run `make <step>` for each step in order; stop at the first failure with `StepFailedError`.

    `variables` maps a step to `NAME=value` arguments for that step only."""
    results = []
    for step in steps:
        started = time.monotonic()
        done = _run(["make", "--no-print-directory", step, *(variables or {}).get(step, ())], directory, env)
        output = done.stdout + done.stderr
        if done.returncode != 0:
            raise StepFailedError(step, output)
        results.append(StepResult(step, time.monotonic() - started, output))
    return results


def try_deploy(directory: Path, name: str, image: str, deployment: str, env: Mapping[str, str]) -> tuple[int, str]:
    """Call the template's deploy script directly. Returns its exit status and output (the script verifies first)."""
    done = _run(["scripts/deploy.sh", name, image, deployment, ""], directory, env)
    return done.returncode, done.stdout + done.stderr


def build_unsigned_image(directory: Path, registry: str, name: str, tag: str, env: Mapping[str, str]) -> str:
    """Build and push an image by hand, the way someone bypassing the pipeline would. Returns `registry/name@digest`."""
    reference = f"{registry}/{name}:{tag}"
    built = _run(["docker", "build", "-q", "-t", reference, "."], directory, env)
    if built.returncode != 0:
        raise StepFailedError("docker build", built.stdout + built.stderr)
    pushed = _run(["docker", "push", reference], directory, env)
    if pushed.returncode != 0:
        raise StepFailedError("docker push", pushed.stdout + pushed.stderr)
    digest = next(part for line in pushed.stdout.splitlines() for part in line.split() if part.startswith("sha256:"))
    return f"{registry}/{name}@{digest}"
```

- **Lines 17 to 24**: `StepFailedError` keeps the step name and the last 1,500 characters of its output (`output.strip()[-1500:]`: a negative index counts from the end). **Lines 27 to 33**: `StepResult`.
- **Lines 36 to 51**: `STEP_TIMEOUT_SECONDS = 3600` and `_run`: `subprocess.run(list(argv), cwd=cwd, env={**os.environ, **env}, capture_output=True, text=True, timeout=..., check=False)` starts a program as a separate **process**, in a folder, with the current environment plus extras (`{**a, **b}` merges two dictionaries, the second winning), capturing its output as text. A timeout raises `subprocess.TimeoutExpired`, turned into `StepFailedError`. It is always called with a *list* of words, never a shell string, so quoting bugs and injection cannot happen.
- **Lines 54 to 68**, `run_steps`: for each step runs `make --no-print-directory STEP [NAME=value ...]`, times it with `time.monotonic()` (a clock that only moves forward), and stops at the first non-zero exit status with `StepFailedError`. `variables` supplies per-step `NAME=value` arguments (for example the deployment id).
- **Lines 71 to 74**, `try_deploy`: calls `scripts/deploy.sh` directly and returns its exit status and output. **Lines 77 to 87**, `build_unsigned_image`: builds and pushes an image by hand with `docker build -q` and `docker push`, the way someone bypassing the pipeline would, and finds the digest in the push output with a generator expression: `next(part for line in pushed.stdout.splitlines() for part in line.split() if part.startswith("sha256:"))` (the first word that starts with `sha256:`).

### `src/goldenpath/interfaces/`: the commands and the HTTP server

```python
"""The event collector: `POST /events` from pipelines and `GET /healthz`, in front of the event store."""

from __future__ import annotations

import hmac
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from goldenpath.application.ports import EventSink
from goldenpath.application.record_events import record
from goldenpath.domain.errors import InvalidEventError
from goldenpath.domain.events import Event, EventType, parse_timestamp

MAX_BODY_BYTES = 64 * 1024


def event_from_json(item: Mapping[str, Any], now: datetime) -> Event:
    """Build an event from a JSON object. A missing `ts` means "now" on the collector's clock."""
    try:
        kind = EventType(str(item["type"]))
        service = str(item["service"])
        ref = str(item["ref"])
    except (KeyError, ValueError):
        raise InvalidEventError("an event needs type (commit, deploy, failed or recovered), service and ref") from None
    ts = parse_timestamp(str(item["ts"])) if item.get("ts") else now
    return Event(ts, service, kind, ref, str(item.get("detail") or ""))


def collector_server(port: int, sink: EventSink, token: str, clock: Any = None) -> ThreadingHTTPServer:
    """A threaded server. Without the bearer token every write is refused; an empty `token` refuses everything."""
    now = clock or (lambda: datetime.now(UTC))
```

- **Line 5**: `import hmac`; **line 9**: `BaseHTTPRequestHandler, ThreadingHTTPServer` from `http.server` ([http-server.md](http-server.md)). **Line 17**: `MAX_BODY_BYTES = 64 * 1024`.
- **Lines 20 to 29**, `event_from_json(item, now)`: read `type`, `service` and `ref` from a JSON object; a missing key (`KeyError`) or an unknown type (`ValueError` from `EventType(...)`) becomes `InvalidEventError`. A missing `ts` means "now" on the collector's clock: the pipeline cannot choose its own timestamp.

```python
def collector_server(port: int, sink: EventSink, token: str, clock: Any = None) -> ThreadingHTTPServer:
    """A threaded server. Without the bearer token every write is refused; an empty `token` refuses everything."""
    now = clock or (lambda: datetime.now(UTC))

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, payload: dict[str, object]) -> None:
            body = (json.dumps(payload) + "\n").encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            given = self.headers.get("Authorization", "")
            return bool(token) and hmac.compare_digest(given.encode(), f"Bearer {token}".encode())

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._reply(200, {"status": "ok"})
            else:
                self._reply(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/events":
                self._reply(404, {"error": "not found"})
            elif not self._authorized():
                self._reply(401, {"error": "a bearer token is required"})
            else:
                self._accept()

        def _accept(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY_BYTES:
                self._reply(413 if length else 400, {"error": f"body must be 1 to {MAX_BODY_BYTES} bytes"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
                items = payload if isinstance(payload, list) else [payload]
                events = [event_from_json(item, now()) for item in items]
            except (json.JSONDecodeError, InvalidEventError, TypeError, AttributeError) as error:
                self._reply(400, {"error": str(error)})
                return
            try:
                accepted = record(sink, events)
            except (
                Exception
            ):  # the store is down or slow: say so, so the pipeline step can retry; never crash the handler
                self._reply(503, {"error": "the event store is unavailable, try again"})
                return
            self._reply(202, {"accepted": accepted, "received": len(events)})

        def log_message(self, format: str, *args: Any) -> None:
            """Silence the default access log."""

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
```

- **Lines 32 to 35**: `collector_server(port, sink, token, clock)` builds a **threaded HTTP server**. A *handler class* is defined inside the function so it can use `sink` and `token`.
- **Lines 37 to 43**, `_reply`: sends a status, JSON headers (`Content-Type`, `Content-Length` = the number of *bytes*, so the text is encoded first) and the body.
- **Lines 45 to 47**, `_authorized`: reads the `Authorization` header and compares it with `Bearer <token>` using `hmac.compare_digest`, which takes the same time however many characters match, so an attacker cannot learn the token by timing. An empty configured token refuses everything.
- **Lines 49 to 53**, `do_GET`: `/healthz` answers 200 `{"status": "ok"}`; anything else 404. **Lines 55 to 61**, `do_POST`: only `/events`; 401 without the token.
- **Lines 63 to 82**, `_accept`: read the body size from `Content-Length`; refuse a body that is empty (400) or over 64 KiB (413); `json.loads(self.rfile.read(length))` parses it; a single object is wrapped into a list; each item becomes a validated `Event`; a parse or validation error is a 400 with the message. Then `record(sink, events)`; if the store fails for any reason, answer **503** so the pipeline step can retry (`except Exception` is deliberate; the handler must never crash). Success is **202 Accepted** with `{"accepted": n, "received": m}`.
- **Lines 84 to 87**: `log_message` is overridden to print nothing (the default writes a line per request); the server listens on `127.0.0.1` only.

```python
"""Text tables for the command line: plain, aligned, no dependencies."""

from __future__ import annotations

from collections.abc import Sequence

from goldenpath.domain.metrics import ServiceMetrics


def _fmt(value: float | None, unit: str, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}{unit}"


def metrics_table(rows: Sequence[ServiceMetrics], weekly: bool = False) -> str:
    """The lesson's table: deploys per week, median lead time, change fail rate, recovery time, per service."""
    header = [
        "service",
        "deploys/week",
        "median lead time",
        "change fail rate",
        "recovery time",
        "batch",
        "empty",
        "open",
        "refused",
    ]
    body = []
    for row in rows:
        body.append(
            [
                row.service,
                f"{row.deploys_per_week:.1f}" if weekly else f"{row.deploys_per_week:g}",
                _fmt(row.median_lead_time_hours, " h"),
                "n/a" if row.change_fail_rate is None else f"{row.change_fail_rate:.0%}",
                _fmt(row.median_recovery_minutes, " min", 0),
                _fmt(row.median_batch_size, "", 1),
                str(row.empty_deploys),
                str(row.open_failures),
                str(row.refused),
            ]
        )
    widths = [max(len(line[index]) for line in [header, *body]) for index in range(len(header))]
    lines = [
        "  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip()
        for line in [header, *body]
    ]
    return "\n".join(lines)
```

- `_fmt(value, unit, digits)` (10 to 11): `"n/a"` for `None`, else the number with that many decimals and a unit; `{value:.{digits}f}` is a nested format: the inner braces give the number of digits. `metrics_table` (14 to 47) builds the table of the lesson. `f"{row.deploys_per_week:g}"` prints `4` for 4.0; `f"{row.change_fail_rate:.0%}"` prints a fraction as a percentage. `widths = [max(len(line[index]) for line in [header, *body]) for index in range(len(header))]` finds each column's widest cell; `cell.ljust(width)` pads on the right; `zip(line, widths, strict=True)` pairs cells with widths and raises if the lengths differ; `.rstrip()` trims the end of each line.

```python
"""`goldenpath`: generate a service, audit it, record events, compute the DORA metrics, trace a value."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from goldenpath.application import measure
from goldenpath.application.generate_service import NonConformingServiceError, ServiceGenerator
from goldenpath.application.ports import EventStore
from goldenpath.application.record_events import list_deployments, record
from goldenpath.domain import simulation
from goldenpath.domain.errors import DomainError
from goldenpath.domain.events import Event, EventType, parse_timestamp
from goldenpath.domain.rules import summarize
from goldenpath.infrastructure import local_pipeline
from goldenpath.infrastructure.auditor import RepositoryAuditor
from goldenpath.infrastructure.catalog_files import FileCatalog
from goldenpath.infrastructure.collector_client import CollectorError, CollectorEventSink
from goldenpath.infrastructure.csv_store import CsvEventStore
from goldenpath.infrastructure.logging import configure_logging, fields
from goldenpath.infrastructure.postgres_store import PostgresEventStore
from goldenpath.infrastructure.repositories import GitRepositories, commits_since
from goldenpath.infrastructure.settings import ConfigurationError, Settings
from goldenpath.infrastructure.template_renderer import FileTemplateRenderer
from goldenpath.interfaces.collector import collector_server
from goldenpath.interfaces.render import metrics_table

_log = logging.getLogger("goldenpath")
ROOT = Path(__file__).resolve().parents[3]

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


```

- **Lines 1 to 45**: imports, the constants `ROOT` (`Path(__file__).resolve().parents[3]`: this file's folder, three levels up, the repository root) and three **exit codes** (0 success, 1 failure, 2 bad usage; the number a program hands back when it ends).

```python
def build_parser() -> argparse.ArgumentParser:
    """The argument parser; exposed so tests can drive it."""
    parser = argparse.ArgumentParser(prog="goldenpath", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new-service", help="create a service from the golden path")
    new.add_argument("name")
    new.add_argument("owner", help="the owning team, for example team-orders")
    new.add_argument(
        "--release", action="store_true", help="also run its pipeline: image, sign, attest, verify, deploy"
    )
    audit = commands.add_parser("audit", help="check a repository against the golden-path contract")
    audit.add_argument("path", type=Path)
    emit = commands.add_parser("emit", help="send one delivery event to the collector")
    emit.add_argument("type", choices=[kind.value for kind in EventType])
    emit.add_argument("service")
    emit.add_argument("ref")
    emit.add_argument("--detail", default="")
    emit.add_argument("--ts", help="event time (ISO 8601); the collector's clock when omitted")
    emit.add_argument("--direct", action="store_true", help="write to the database instead of through the collector")
    commands.add_parser("collector", help="run the event collector (POST /events)")
    sim = commands.add_parser("simulate", help="replace the stored events with a simulated month for three teams")
    sim.add_argument("--seed", type=int, default=7)
    sim.add_argument("--days", type=int, default=28)
    metrics = commands.add_parser("metrics", help="the four DORA metrics per service")
    metrics.add_argument("--csv", type=Path, help="read events from a CSV file instead of the database")
    metrics.add_argument("--weekly", action="store_true", help="one table per week")
    metrics.add_argument(
        "--include-samples", action="store_true", help="also measure the sample-* services of sql/002_seed.sql"
    )
    trace = commands.add_parser("trace", help="trace one lead time back to its commit and deployment events")
    trace.add_argument("service")
    trace.add_argument("commit")
    trace.add_argument("--csv", type=Path)
    deployments = commands.add_parser("deployments", help="every production deployment of a service with its commits")
    deployments.add_argument("service")
    deployments.add_argument("--csv", type=Path)
    commands.add_parser("catalog", help="list the registered services")
    unsigned = commands.add_parser("demo-unsigned", help="push an unsigned image of a service and try to deploy it")
    unsigned.add_argument("name")
    return parser


def _store(settings: Settings, csv_path: Path | None = None) -> EventStore:
    return CsvEventStore(csv_path) if csv_path else PostgresEventStore(settings.dsn)


def _catalog(settings: Settings) -> FileCatalog:
    return FileCatalog(ROOT / "catalog" / "teams.yaml", settings.workdir / "catalog" / "entities")


def _platform_ref() -> str:
    done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S607
    return done.stdout.strip() or "0" * 40
```

- `build_parser` describes the command with `argparse`: sub-commands `new-service NAME OWNER [--release]`, `audit PATH`, `emit TYPE SERVICE REF [--detail] [--ts] [--direct]`, `collector`, `simulate [--seed 7] [--days 28]`, `metrics [--csv FILE] [--weekly] [--include-samples]`, `trace SERVICE COMMIT [--csv]`, `deployments SERVICE [--csv]`, `catalog`, `demo-unsigned NAME`. `choices=[kind.value for kind in EventType]` accepts only the four event types; `type=Path` converts text to a path; `action="store_true"` makes a flag.
- `_store` picks a CSV store when `--csv` is given and PostgreSQL otherwise; `_catalog` builds the file catalog; `_platform_ref` asks Git for the platform's own commit (`git rev-parse HEAD`), using zeros if Git says nothing.

```python

def _pipeline_env(settings: Settings) -> dict[str, str]:
    keys = (settings.workdir / "keys").resolve()
    return {
        "REGISTRY": os.environ.get("REGISTRY", "localhost:55061"),
        "COSIGN_KEY": str(keys / "cosign.key"),
        "COSIGN_PUBLIC_KEY": str(keys / "cosign.pub"),
        "COSIGN_PASSWORD": os.environ.get("COSIGN_PASSWORD", ""),
        "EVENTS_URL": settings.collector_url,
        "EVENTS_TOKEN": settings.collector_token,
    }


def _new_service(args: argparse.Namespace, settings: Settings) -> int:
    started = time.monotonic()
    destination = (settings.workdir / "services" / args.name).resolve()
    catalog = _catalog(settings)
    generator = ServiceGenerator(
        FileTemplateRenderer(ROOT / "template"),
        catalog,
        GitRepositories((settings.workdir / "remotes").resolve()),
        RepositoryAuditor(catalog),
        _platform_ref(),
    )
    try:
        service = generator.generate(args.name, args.owner, destination, settings.runbook_base)
    except NonConformingServiceError as error:
        print(summarize(error.findings), file=sys.stderr)
        return EXIT_FAILED
    entry = service.entry
    print(f"created {entry.name} (owner {entry.owner}) at {service.directory}, commit {service.commit[:7]}")
    print(f"  catalog entry registered; generated {len(service.files)} files; audit: {summarize([])}")
    if not args.release:
        return EXIT_OK
    return _release(args.name, destination, settings, started)


def _release(name: str, directory: Path, settings: Settings, started: float) -> int:
    env = _pipeline_env(settings)
    sink = CollectorEventSink(settings.collector_url, settings.collector_token)
    commits = list(commits_since(directory, None))
    record(sink, [Event(datetime.now(tz=simulation.START.tzinfo), name, EventType.COMMIT, ref) for ref in commits])
    deployment = f"{name}-d1"
    env |= {"SERVICE_NAME": name}
    steps = ("lint", "test", "image", "sign", "attest", "verify", "deploy")
    variables = {"deploy": [f"COMMITS={'+'.join(commits)}", f"DEPLOYMENT={deployment}"]}
    try:
        results = local_pipeline.run_steps(directory, steps, env, variables)
    except local_pipeline.StepFailedError as error:
        print(error, file=sys.stderr)
        return EXIT_FAILED
    for result in results:
        print(f"  {result.name:<7}{result.seconds:6.1f}s")
    total = time.monotonic() - started
    print(f"{name}: from the command to the first production deployment in {total:.0f}s (limit: 1800s)")
    return EXIT_OK


```

- **Lines 100 to 109**, `_pipeline_env`: the environment a generated service's pipeline needs locally: the registry, the signing key paths, the key password, the collector's address and token.
- **Lines 112 to 129**, `_new_service`: builds the `ServiceGenerator` with real adapters and calls `generate`; a `NonConformingServiceError` prints the findings to standard error and returns 1. Without `--release` it stops after printing `created ... audit: conforms to the golden path contract`.
- **Lines 132 to 151**, `_release`: the full path to production. It records one `commit` event per commit (`record(sink, [Event(...)])`), then runs `make lint`, `test`, `image`, `sign`, `attest`, `verify`, `deploy` in the generated folder with timings (`local_pipeline.run_steps`), prints each step's seconds and the total ("from the command to the first production deployment in Ns (limit: 1800s)"). A failing step prints its output and returns 1.

```python
    print(f"{name}: from the command to the first production deployment in {total:.0f}s (limit: 1800s)")
    return EXIT_OK


def _demo_unsigned(name: str, settings: Settings) -> int:
    directory = (settings.workdir / "services" / name).resolve()
    env = _pipeline_env(settings) | {"SERVICE_NAME": name}
    image = local_pipeline.build_unsigned_image(directory, env["REGISTRY"], name, "unsigned", env)
    print(f"pushed by hand, never signed: {image}")
    status, output = local_pipeline.try_deploy(directory, name, image, f"{name}-d-unsigned", env)
    for line in output.splitlines():
        if "no signatures found" in line or "deploy refused" in line:
            print(line.strip())
    print(f"deploy exit status: {status} ({'refused' if status else 'ACCEPTED: the contract is broken'})")
    return EXIT_OK if status != 0 else EXIT_FAILED


def _serve_collector(settings: Settings) -> int:
    if not settings.collector_token:
        print("configuration error: COLLECTOR_TOKEN must be set", file=sys.stderr)
        return EXIT_USAGE
    server = collector_server(settings.collector_port, PostgresEventStore(settings.dsn), settings.collector_token)
    stop = threading.Event()

    def request_stop(signum: int, frame: object) -> None:
        _log.info("shutdown requested", extra=fields(signal=signal.Signals(signum).name))
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _log.info("collecting", extra=fields(port=settings.collector_port))
    stop.wait()
    server.shutdown()
    server.server_close()
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the exit code instead of exiting, so tests can call it."""
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env(
            need_database=args.command in {"collector", "simulate", "metrics", "trace", "deployments"}
            and not getattr(args, "csv", None)
        )
    except ConfigurationError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return EXIT_USAGE
    configure_logging(settings.log_level)
    try:
        return _dispatch(args, settings)
    except (DomainError, CollectorError, measure.NoEventsError, local_pipeline.StepFailedError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE if isinstance(error, DomainError) else EXIT_FAILED
    except Exception:
        _log.exception("command failed", extra=fields(command=args.command))
```

- **Lines 154 to 168**, `_demo_unsigned`: pushes an image nobody signed, tries to deploy it, prints the refusal lines (`no signatures found`, `deploy refused`) and `deploy exit status: 1 (refused)`; it returns success only if the deployment was refused.
- **Lines 171 to 188**, `_serve_collector`: refuses to start without `COLLECTOR_TOKEN`; builds the server; defines `request_stop` as a **signal handler**: a *signal* is a message the operating system sends a program (`SIGTERM` from `kill`, `SIGINT` from Ctrl-C). The handler sets a `threading.Event`; the server runs on a **daemon thread** (a background thread that does not keep the program alive); the main thread waits on the event, and when a signal arrives it shuts the server down cleanly instead of being cut off.
- **Lines 191 to 210**, `main`: parses arguments; builds settings (the database is required only for the commands listed); sets up logging; runs `_dispatch` and sorts failures: domain, collector, "no events" and step failures print `error: ...` (exit 2 for a `DomainError`, else 1); anything unexpected is logged with its traceback (`_log.exception`) and returns 1.

```python

def _dispatch(args: argparse.Namespace, settings: Settings) -> int:
    match args.command:
        case "new-service":
            return _new_service(args, settings)
        case "audit":
            from goldenpath.infrastructure.auditor import RepositoryAuditor as Auditor

            findings = Auditor(_catalog(settings)).audit(args.path)
            print(summarize(findings))
            return EXIT_FAILED if findings else EXIT_OK
        case "emit":
            when = parse_timestamp(args.ts) if args.ts else datetime.now(tz=simulation.START.tzinfo)
            event = Event(when, args.service, EventType(args.type), args.ref, args.detail)
            sink = (
                PostgresEventStore(settings.dsn)
                if args.direct
                else CollectorEventSink(settings.collector_url, settings.collector_token)
            )
            print(f"recorded {event.type.value} {event.ref}: {record(sink, [event])} new")
            return EXIT_OK
        case "collector":
            return _serve_collector(settings)
        case "simulate":
            store = PostgresEventStore(settings.dsn)
            events = simulation.simulate(args.seed, args.days)
            store.clear()
            teams = len({event.service for event in events})
            recorded = record(store, events)
            summary = f"{len(events)} events for {teams} teams over {args.days} days (seed {args.seed})"
            print(f"simulated {summary}: {recorded} recorded")
            return EXIT_OK
        case "metrics":
            reader = _store(settings, args.csv)
            if args.weekly:
                for index, rows in measure.per_week(reader, args.include_samples):
                    print(f"\nweek {index}\n{metrics_table(rows, weekly=True)}")
            else:
                print(metrics_table(measure.summary(reader, include_samples=args.include_samples)))
            return EXIT_OK
        case "trace":
            lead = measure.trace(_store(settings, args.csv), args.service, args.commit)
            print(f"commit event:  {lead.commit.ts:%Y-%m-%d %H:%M}  {lead.commit.service}  commit  {lead.commit.ref}")
            print(f"deploy event:  {lead.deploy.ts:%Y-%m-%d %H:%M}  {lead.deploy.service}  deploy  {lead.deploy.ref}")
            print(f"lead time:     {lead.hours:.1f} h")
            return EXIT_OK
        case "deployments":
            for stamp, deployment, commits in list_deployments(_store(settings, args.csv), args.service):
                print(f"{stamp}  {deployment}  commits: {', '.join(commits) or '(none)'}")
            return EXIT_OK
        case "catalog":
            for entry in _catalog(settings).entries():
                print(f"{entry.name:<20}{entry.owner:<16}{entry.lifecycle:<12}{entry.runbook}")
            return EXIT_OK
        case "demo-unsigned":
            return _demo_unsigned(args.name, settings)
    return EXIT_OK
```

`_dispatch` uses a `match args.command:` statement (Python 3.10 and newer), which compares a value with several `case` patterns like a tidy chain of `if`/`elif`. `new-service`, `audit` (prints `summarize(findings)`; exit 1 if any), `emit` (builds one event, sends it through the collector or, with `--direct`, straight to the database; prints `recorded commit try-1: 1 new`), `collector`, `simulate` (clears the store, simulates, records, prints the counts), `metrics` (a table, or one per week with `--weekly`), `trace` (prints the two events and the lead time), `deployments`, `catalog` (a four-column listing with `{entry.name:<20}` meaning "left-aligned in 20 characters"), `demo-unsigned`.

### `scripts/lint_workflows.py`

```python
"""Lint the platform's own workflow and the template's against the golden-path rules (`make lint` runs this)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from goldenpath.domain import rules
from goldenpath.infrastructure.auditor import load_workflow

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Print every finding; exit 1 when there is one."""
    findings = []
    template_workflow = ROOT / "template" / ".github" / "workflows" / "ci.yml"
    findings += [
        (template_workflow, finding) for finding in rules.check_workflow(load_workflow(template_workflow.read_text()))
    ]
    protection = ROOT / "template" / "protection.json"
    findings += [(protection, finding) for finding in rules.check_protection(json.loads(protection.read_text()))]
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        document = load_workflow(path.read_text())
        findings += [
            (path, finding)
            for finding in rules.check_workflow(document)
            if finding.code in {"GP-PIN", "GP-MOVING", "GP-PERMS"}
        ]
    for path, finding in findings:
        print(f"{path.relative_to(ROOT)}: {finding.code} {finding.message}")
    print("workflows ok" if not findings else f"{len(findings)} problem(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
```

- Applies the contract rules to the platform's files in `make lint`. **Line 12**: `ROOT` is two levels up from the script. **Lines 18 to 23**: check the *template's* workflow and `protection.json` fully. **Lines 24 to 30**: for the platform's own workflows only the pinning, moving-name and permissions rules (**GP-PIN**, **GP-MOVING**, **GP-PERMS**) apply. **Lines 31 to 34**: print `path: CODE message` for each finding, then `workflows ok` or the count; the `main()` function returns 1 if there is any finding, and `sys.exit(main())` at the end (line 38) turns that into the program's exit code. `if __name__ == "__main__":` means "run this only when the file is started directly, not when another file imports it".

### `template/app/main.py`: the generated service

```python
"""__NAME__: a small HTTP service. Replace it with your own; keep /healthz."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = os.environ.get("APP_VERSION", "dev")


def answer(path: str) -> tuple[int, str]:
    """The status and body for a path."""
    if path == "/healthz":
        return 200, "ok\n"
    if path == "/":
        return 200, json.dumps({"service": "__NAME__", "owner": "__OWNER__", "version": VERSION}) + "\n"
    return 404, "not found\n"


class Handler(BaseHTTPRequestHandler):
    """Serves `answer`."""

    def do_GET(self) -> None:
        status, body = answer(self.path)
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        """No access log."""


def main() -> None:
    """Serve on $PORT (default 8080)."""
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()


if __name__ == "__main__":
    main()
```

- **Lines 3 to 5**: imports. **Line 7**: `VERSION = os.environ.get("APP_VERSION", "dev")` reads the build's version from the environment ([dotenv.md](dotenv.md)). **Lines 10 to 16**, `answer(path)`: pure logic returning `(status, body)`: `/healthz` gives `(200, "ok\n")`; `/` gives a JSON text naming the service, owner and version (built with `json.dumps`); anything else `(404, "not found\n")`. The words `__NAME__` and `__OWNER__` are placeholders that the platform replaces when it generates a service.
- **Lines 19 to 31**: `Handler(BaseHTTPRequestHandler)` with `do_GET`: calls `answer`, encodes the body to bytes, sends the status, a `Content-Length` header (the byte count), ends the headers and writes the body. `log_message` is silenced. **Lines 34 to 36**, `main`: `ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()` listens on every network interface inside the container (so Docker can reach it) on port 8080 unless `PORT` says otherwise, serving each request on its own thread. **Lines 39 and 40**: run `main()` only when the file is started directly.

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
