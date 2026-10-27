# pytest and coverage

## What it is

A **test** is a small program that checks that another program does what it should. You give the code some input, run it, and **assert** (state) what the result must be. If the statement is false the test **fails**, and you learn about the mistake before a user does.

**pytest** is the tool that finds, runs and reports tests in Python. It looks for files whose names start with `test_` and, in them, functions whose names start with `test_`. It runs each one. A test **passes** if the function ends without an error and **fails** if an `assert` is false or any other error escapes. This repository pins pytest 9.1.1, pytest-cov 7.1.0 and coverage 7.17.0.

**Coverage** is a measurement of how much of the program's code the tests actually ran. If a line never ran during the tests, nothing proves it works. The `coverage` library records which lines ran; `pytest-cov` connects it to pytest.

The vocabulary used below:

- **`assert condition`** fails the test when the condition is false. pytest rewrites asserts so that a failure shows both sides of a comparison.
- **`pytest.raises(SomeError)`** is a `with` block that passes only if the code inside raises that error.
- **A fixture** is a function marked `@pytest.fixture` that prepares something a test needs (a temporary folder, a fake store). A test asks for it simply by naming it as a parameter. Code after a `yield` in a fixture runs after the test as clean-up.
- **`@pytest.mark.parametrize("x", [a, b, c])`** runs the same test once for each value.
- **A marker** (`@pytest.mark.name`) labels a test so you can select or skip groups: `-m integration`.
- **`tmp_path`** is a built-in fixture: a fresh empty temporary folder for each test.
- **`monkeypatch`** is a built-in fixture that temporarily replaces a variable, an attribute or an environment variable and puts it back afterwards.
- **`capsys`** and **`capfd`** capture what the code prints to the screen so the test can read it.
- **A fake** is a simple stand-in object used instead of the real thing (a clock the test moves by hand, a store kept in a list). Fakes make tests fast and exact.
- **A unit test** checks one small piece alone. An **integration test** checks pieces working together with something real (here a real database). An **end-to-end (e2e) test** runs a whole scenario.

## Why this repository uses it

The platform has four kinds of test, matched to what each needs, so the quick ones run everywhere and the slow ones only where Docker is available:

| Folder | Needs | What it proves |
|---|---|---|
| `tests/unit/` | nothing | The domain (events, metrics, rules, catalog, simulation), the use cases with fake collaborators, the adapters that need no outside service (CSV, settings, logging, rendering, the auditor, the collector over a real local socket) and the command line. |
| `tests/template/` | `git`, `make` | The template, generated for three teams with real Git and real `make`, passes the audit and its own `make ci`. |
| `tests/integration/` | PostgreSQL (`make up`) | The store, the schema's rules and the SQL queries; SQL and Python give the same numbers. |
| `tests/e2e/` | Docker, cosign, the registry (`make up`) | One service from the command to production, and an unsigned image refused. |

A coverage floor of 95 percent on the domain and application layers keeps the delivery maths and rules tested.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` lines 55 to 69 | `[tool.pytest.ini_options]` and `[tool.coverage.*]`. |
| `Makefile` | `test`, `test-integration`, `test-e2e`, `check`. |
| `tests/` | 9 test files and one `conftest.py`, about 120 tests. |
| `.github/workflows/ci.yml` | `make check` (jobs `check`) and `make test-integration` (job `integration`). |

## How it works underneath

pytest **collects**: it walks the folders you name, imports each `test_*.py` file, and gathers `test_*` functions. It then runs each, one after another, in its own call, catching any error. For asserts it rewrites the code at import time so a failed `assert a == b` shows the values of `a` and `b`. Fixtures are resolved by name: when a test function has a parameter named `store`, pytest finds a fixture called `store`, runs it, and passes its result in. A fixture's **scope** controls how long its value lives (`scope="session"` means once for the whole run; the default is once per test).

pytest can write a **JUnit XML** report (`--junitxml=reports/unit.xml`), a standard format other tools understand; this project reads it to find which test failed ([junit-xml.md](junit-xml.md)).

Coverage works by tracing the running program and noting every line (and, with `branch = true`, every outcome of every `if`). `coverage report --fail-under=95` exits non-zero if the share is below 95 percent.

## Walkthrough of this repository's use

### The configuration

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra --strict-markers"
markers = [
    "integration: needs PostgreSQL from docker-compose.yml (make up)",
    "e2e: the golden path end to end with Docker, a local registry and cosign (make up first)",
]

[tool.coverage.run]
source = ["goldenpath"]
branch = true

[tool.coverage.report]
show_missing = true
```

- **Line 56**: `testpaths = ["tests"]`. **Line 57**: `pythonpath = ["."]` adds the repository root to Python's module search list so `from goldenpath...` and `from tests...` work. **Line 58**: `addopts = "-ra --strict-markers"`: `-ra` prints a short summary of everything that did not simply pass (skips included); `--strict-markers` makes a misspelled marker an error.
- **Lines 59 to 62**: `markers` declares `integration` (needs PostgreSQL) and `e2e` (the golden path end to end with Docker, a local registry and cosign).
- **Lines 64 to 66**: coverage measures the package `goldenpath`, with branch coverage. **Lines 68 and 69**: `show_missing = true` lists the uncovered line numbers.

### The Make targets

`make test` runs `pytest tests/unit tests/template -p no:cacheprovider --junitxml=reports/unit.xml --cov --cov-report=term` and then `coverage report --include='src/goldenpath/domain/*,src/goldenpath/application/*' --fail-under=95`. `make test-integration` runs `pytest tests/integration -m integration`; `make test-e2e` runs `pytest tests/e2e -m e2e`. `make check` is `lint` and `test` (no database, no Docker) ([make.md](make.md)).

### `tests/unit/domain/test_events_and_metrics.py`: the lesson's table, as tests

```python
from datetime import UTC, datetime, timedelta

import pytest

from goldenpath.domain import metrics
from goldenpath.domain.errors import InvalidEventError, UnknownCommitError
from goldenpath.domain.events import Event, EventType, format_deploy_ref, parse_deploy_ref, parse_timestamp

SAMPLE = """
2026-09-01T09:00,orders,commit,a1
2026-09-01T10:30,orders,commit,a2
2026-09-01T14:00,orders,deploy,d1:a1+a2
2026-09-02T11:00,orders,commit,a3
2026-09-02T15:00,orders,deploy,d2:a3
2026-09-02T15:10,orders,failed,d2
2026-09-02T15:40,orders,recovered,d2
2026-09-03T09:30,orders,commit,a4
2026-09-03T10:00,orders,deploy,d3:a4
2026-09-04T16:00,orders,commit,a5
2026-09-07T10:00,orders,deploy,d4:a5
2026-09-01T10:00,billing,commit,b1
2026-09-02T10:00,billing,commit,b2
2026-09-03T10:00,billing,commit,b3
2026-09-04T10:00,billing,commit,b4
2026-09-05T12:00,billing,deploy,e1:b1+b2+b3+b4
2026-09-05T12:20,billing,failed,e1
2026-09-05T16:20,billing,recovered,e1
"""


def sample_events() -> list[Event]:
    rows = [line.split(",") for line in SAMPLE.strip().splitlines()]
    return [Event(parse_timestamp(ts), service, EventType(kind), ref) for ts, service, kind, ref in rows]


def by_service() -> dict[str, metrics.ServiceMetrics]:
    events = sample_events()
    start, end = metrics.window_of(events)
    return {name: metrics.compute(events, name, start, end) for name in metrics.services(events)}

```

- **Lines 9 to 28**: `SAMPLE` is the lesson's 18 events as a block of text. **Lines 31 to 33**, `sample_events()`: `SAMPLE.strip().splitlines()` gives lines; `line.split(",")` splits each into four cells; each becomes a validated `Event` (`parse_timestamp(ts)`, `EventType(kind)`). **Lines 36 to 39**, `by_service()`: computes the metrics of each service over the data's own window and returns a dictionary by name.

```python
def test_the_window_of_the_sample_is_one_week_from_midnight_of_the_first_day():
    start, end = metrics.window_of(sample_events())
    assert start == datetime(2026, 9, 1, tzinfo=UTC)
    assert end - start == timedelta(days=7)


def test_orders_matches_the_lessons_table():
    orders = by_service()["orders"]
    assert orders.deploys_per_week == 4
    assert orders.median_lead_time_hours == 4.0
    assert orders.change_fail_rate == 0.25
    assert orders.median_recovery_minutes == 30


def test_billing_matches_the_lessons_table():
    billing = by_service()["billing"]
    assert billing.deploys_per_week == 1
    assert billing.median_lead_time_hours == 62.0
    assert billing.change_fail_rate == 1.0
    assert billing.median_recovery_minutes == 240


def test_lead_time_is_per_commit_so_a_batch_has_one_value_per_commit():
    leads = metrics.lead_times(sample_events(), "billing")
    assert sorted(lead.hours for lead in leads) == [26, 50, 74, 98]


def test_the_orders_lead_times_are_the_five_the_lesson_lists():
    leads = metrics.lead_times(sample_events(), "orders")
    assert sorted(lead.hours for lead in leads) == [0.5, 3.5, 4.0, 5.0, 66.0]


def test_a_lead_time_is_traced_to_its_commit_event_and_its_deployment_event():
    lead = metrics.trace_lead_time(sample_events(), "orders", "a5")
    assert (lead.commit.ref, lead.commit.type) == ("a5", EventType.COMMIT)
    assert (lead.deploy.ref, lead.deploy.type) == ("d4:a5", EventType.DEPLOY)
    assert lead.hours == 66.0


def test_tracing_a_commit_that_never_deployed_is_an_error():
    with pytest.raises(UnknownCommitError):
        metrics.trace_lead_time(sample_events(), "orders", "zzz")


def test_a_deployment_with_no_commits_does_not_count_towards_frequency_but_is_reported():
    events = [*sample_events(), Event(parse_timestamp("2026-09-06T12:00"), "orders", EventType.DEPLOY, "d9:")]
    start, end = metrics.window_of(events)
    orders = metrics.compute(events, "orders", start, end)
    assert orders.deploys == 4
    assert orders.empty_deploys == 1


def test_a_failure_with_no_recovery_is_counted_as_open_not_as_a_zero_recovery_time():
    events = [e for e in sample_events() if not (e.service == "billing" and e.type is EventType.RECOVERED)]
    start, end = metrics.window_of(events)
    billing = metrics.compute(events, "billing", start, end)
    assert billing.open_failures == 1
    assert billing.median_recovery_minutes is None


def test_a_service_with_no_deployments_has_no_rates():
    events = [Event(parse_timestamp("2026-09-01T09:00"), "quiet", EventType.COMMIT, "q1")]
    start, end = metrics.window_of(events)
    quiet = metrics.compute(events, "quiet", start, end)
    assert (quiet.deploys, quiet.change_fail_rate, quiet.median_lead_time_hours) == (0, None, None)


def test_the_weekly_breakdown_has_one_row_per_service_for_every_week_of_the_data():
    events = [*sample_events(), Event(parse_timestamp("2026-09-10T10:00"), "orders", EventType.COMMIT, "a6")]
    start, end = metrics.window_of(events)
    weeks = metrics.weekly(events, start, end)
    assert [index for index, _ in weeks] == [1, 2]
    assert {row.service for row in weeks[0][1]} == {"orders", "billing"}


def test_the_median_batch_size_tells_a_weekly_batch_from_small_changes():
    table = by_service()
    assert table["orders"].median_batch_size == 1.0
    assert table["billing"].median_batch_size == 4.0

```

- **Lines 42 to 45**: the window of the sample starts at midnight of 1 September and lasts exactly 7 days. **Lines 48 to 53**: `orders` has 4 deployments per week, median lead time 4.0 hours, change fail rate 0.25, recovery 30 minutes. **Lines 56 to 61**: `billing` has 1, 62.0 hours, 1.0 and 240 minutes: the lesson's table.
- **Lines 64 to 66**: lead time is per commit: billing's four commits have 26, 50, 74 and 98 hours. **Lines 69 to 71**: orders' five are 0.5, 3.5, 4.0, 5.0 and 66.0.
- **Lines 74 to 78**: `trace_lead_time(..., "orders", "a5")` returns the commit event, the deployment event `d4:a5` and 66.0 hours. **Lines 81 to 83**: an unknown commit raises `UnknownCommitError`.
- **Lines 86 to 91**: add a deployment `d9:` with no commits: `deploys == 4` still and `empty_deploys == 1`. **Lines 94 to 99**: remove billing's recovery event: `open_failures == 1` and the median recovery is `None`, not zero. **Lines 102 to 106**: a service with only a commit has no deployments and every rate `None`.
- **Lines 109 to 114**: with one more event in the second week, `weekly` returns weeks numbered `[1, 2]`, and week 1 has both services. **Lines 117 to 120**: median batch sizes are 1.0 and 4.0.
- **Lines 123 to 126**: `parse_deploy_ref` and `format_deploy_ref` round-trip, and `d9:` has no commits. **Lines 129 to 131**: a time without a zone is taken as UTC and `+02:00` is converted (11:00 at +02:00 is 09:00 UTC).

```python
@pytest.mark.parametrize(
    ("service", "kind", "ref", "detail"),
    [
        ("X", EventType.COMMIT, "a1", ""),
        ("orders", EventType.COMMIT, "bad ref!", ""),
        ("orders", EventType.DEPLOY, "no-colon", ""),
        ("orders", EventType.COMMIT, "a1", "why"),
    ],
)
def test_an_event_that_cannot_be_placed_on_a_timeline_is_refused(service, kind, ref, detail):
    with pytest.raises(InvalidEventError):
        Event(datetime(2026, 9, 1, tzinfo=UTC), service, kind, ref, detail)


def test_an_event_without_a_time_zone_is_refused():
    with pytest.raises(InvalidEventError, match="time zone"):
        Event(datetime(2026, 9, 1), "orders", EventType.COMMIT, "a1")


def test_a_refused_deployment_is_counted_as_refused_not_as_a_failed_deployment():
    events = [
        *sample_events(),
        Event(parse_timestamp("2026-09-03T12:00"), "orders", EventType.FAILED, "d-unsigned", "signature"),
    ]
    start, end = metrics.window_of(events)
    orders = metrics.compute(events, "orders", start, end)
    assert orders.refused == 1
    assert orders.change_fail_rate == 0.25
```

- **Lines 134 to 145**: `@pytest.mark.parametrize` runs the same test for four bad events: an upper-case service name, a ref with a space and `!`, a `deploy` with no colon, and a `detail` on a `commit`. Each must raise `InvalidEventError`. **Lines 148 to 150**: an event with no time zone is refused (`match="time zone"` checks the message).
- **Lines 153 to 161**: a `failed` event with the detail `signature` for a deployment that never ran counts in `refused` (1), and the change fail rate stays 0.25: a refusal is not a failed deployment.

### `tests/unit/domain/test_catalog_rules_simulation.py`: the contract and the simulation

```python
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from goldenpath.domain import metrics, rules, simulation
from goldenpath.domain.catalog import CatalogEntry, from_mapping, validate
from goldenpath.domain.errors import InvalidCatalogEntryError
from goldenpath.infrastructure.auditor import load_workflow

ROOT = Path(__file__).resolve().parents[3]
TEAMS = frozenset({"team-orders", "team-platform"})


def entry(**changes: str) -> CatalogEntry:
    base = {
        "name": "orders",
        "owner": "team-orders",
        "lifecycle": "production",
        "runbook": "https://wiki.example.com/r/orders",
        "slo": "99.9%",
    }
    return CatalogEntry(**{**base, **changes})


def test_a_valid_entry_is_returned_unchanged():
    assert validate(entry(), TEAMS) == entry()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"owner": "alice"}, "not a person"),
        ({"owner": "team-ghost"}, "not a registered team"),
        ({"name": "Orders!"}, "name must be"),
        ({"lifecycle": "forever"}, "lifecycle"),
        ({"runbook": "http://insecure"}, "https"),
        ({"slo": " "}, "slo"),
    ],
)
def test_an_entry_that_breaks_the_contract_names_the_broken_rule(changes, message):
    with pytest.raises(InvalidCatalogEntryError, match=message):
        validate(entry(**changes), TEAMS)


def test_a_mapping_with_a_missing_key_names_it():
    with pytest.raises(InvalidCatalogEntryError, match="'slo'"):
        from_mapping({"name": "a1", "owner": "team-orders", "lifecycle": "production", "runbook": "https://x"})

```

- **Lines 17 to 25**, `entry(**changes)`: builds a valid `CatalogEntry` and lets a test change some fields (`{**base, **changes}` merges two dictionaries, the second winning). **Lines 28 to 29**: a valid entry is returned unchanged.
- **Lines 32 to 45**: six broken entries, one per rule: an owner `alice` ("not a person"), `team-ghost` ("not a registered team"), a bad name, a lifecycle `forever`, a runbook `http://insecure`, a blank SLO. `pytest.raises(InvalidCatalogEntryError, match=message)` checks both the error type and that the message contains the text.
- **Lines 48 to 50**: a mapping without `slo` raises an error that names `'slo'`.

```python
def template_workflow() -> dict[str, Any]:
    return load_workflow((ROOT / "template" / ".github" / "workflows" / "ci.yml").read_text())


def codes(findings: list[rules.Finding]) -> set[str]:
    return {finding.code for finding in findings}


def test_the_templates_workflow_keeps_every_rule():
    assert rules.check_workflow(template_workflow()) == []


def test_removing_the_signing_step_is_found():
    document = template_workflow()
    document["jobs"]["release"]["steps"] = [
        s for s in document["jobs"]["release"]["steps"] if s.get("run") != "make sign"
    ]
    assert "GP-SIGN" in codes(rules.check_workflow(document))


def test_removing_verification_is_found():
    document = template_workflow()
    document["jobs"]["release"]["steps"] = [
        s for s in document["jobs"]["release"]["steps"] if s.get("run") != "make verify"
    ]
    assert "GP-VERIFY" in codes(rules.check_workflow(document))


def test_dropping_the_identity_token_permission_is_found():
    document = template_workflow()
    del document["jobs"]["release"]["permissions"]["id-token"]
    assert "GP-OIDC" in codes(rules.check_workflow(document))


def test_granting_the_identity_token_to_the_whole_workflow_is_found():
    document = template_workflow()
    document["permissions"]["id-token"] = "write"
    assert "GP-PERMS" in codes(rules.check_workflow(document))


@pytest.mark.parametrize("reference", ["actions/checkout@v4", "actions/checkout@main", "actions/checkout@" + "a" * 39])
def test_an_action_not_pinned_to_a_full_commit_is_found(reference):
    document = template_workflow()
    document["jobs"]["lint"]["steps"][0]["uses"] = reference
    assert "GP-PIN" in codes(rules.check_workflow(document))


def test_a_moving_image_tag_is_found():
    document = template_workflow()
    document["jobs"]["lint"]["steps"].append({"run": "docker run python:latest"})
    assert "GP-MOVING" in codes(rules.check_workflow(document))


def protection() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((ROOT / "template" / "protection.json").read_text())
    return payload


def test_the_templates_protection_keeps_every_rule():
    assert rules.check_protection(protection()) == []


def test_protection_that_weakens_a_rule_is_found():
    weak = protection()
    weak["required_status_checks"]["contexts"] = ["lint"]
    weak["required_status_checks"]["strict"] = False
    weak["enforce_admins"] = False
    weak["required_pull_request_reviews"] = None
    assert codes(rules.check_protection(weak)) == {"GP-CHECKS", "GP-STRICT", "GP-ADMINS", "GP-PR"}

```

- **Lines 53 to 58**: `template_workflow()` loads the real template workflow; `codes(findings)` makes a set of codes. **Lines 61 to 62**: the real template workflow has no findings.
- **Lines 65 to 97**: each test removes or changes one thing in the loaded workflow and expects one code: delete the `make sign` step: `GP-SIGN`; delete `make verify`: `GP-VERIFY`; delete the release job's `id-token`: `GP-OIDC`; add `id-token: write` at the top: `GP-PERMS`; three bad references (`@v4`, `@main`, a 39-character commit): `GP-PIN`; add a step `docker run python:latest`: `GP-MOVING`.
- **Lines 106 to 112**: `protection()` loads the real `protection.json`; it has no findings. **Lines 115 to 121**: weakening four things (only `lint` required, `strict` off, admins not enforced, no pull-request reviews) gives exactly `{"GP-CHECKS", "GP-STRICT", "GP-ADMINS", "GP-PR"}`.

```python
@pytest.mark.parametrize(
    "text",
    [
        "key = AKIAABCDEFGHIJKLMNOP",
        "aws_secret_access_key = abc123",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY-----",
        "token: ghp_" + "a" * 36,
        "password: ${{ secrets.DEPLOY_PASSWORD }}",
        "aws: ${{ secrets.AWS_ACCESS_KEY_ID }}",
    ],
)
def test_what_a_long_lived_credential_looks_like_is_found(text):
    assert codes(rules.scan_for_credentials({"deploy.yml": text})) == {"GP-SECRET"}


def test_a_clean_file_has_no_credential_finding():
    assert rules.scan_for_credentials({"a.py": "print('hello')", "ci.yml": "id-token: write"}) == []


def test_a_leftover_placeholder_is_found():
    assert codes(rules.unreplaced_placeholders({"README.md": "# __NAME__"})) == {"GP-PLACEHOLDER"}
    assert rules.unreplaced_placeholders({"a.py": "__init__ and __main__"}) == []


def test_the_summary_says_conforms_or_lists_codes():
    assert rules.summarize([]) == "conforms to the golden path contract"
    assert "GP-SIGN" in rules.summarize([rules.Finding("GP-SIGN", "signed artifacts", "no step signs")])


def test_the_catalog_file_of_teams_lists_a_team_for_each_demo_service():
    teams = set(yaml.safe_load((ROOT / "catalog" / "teams.yaml").read_text())["teams"])
    assert {"team-orders", "team-billing", "team-search"} <= teams


def test_the_same_seed_gives_the_same_month():
    assert simulation.simulate(7) == simulation.simulate(7)
    assert simulation.simulate(7) != simulation.simulate(8)


def test_the_simulation_covers_the_four_event_types_for_three_teams():
    events = simulation.simulate(7)
    assert {event.service for event in events} == {"orders", "search", "billing"}
    assert {event.type.value for event in events} == {"commit", "deploy", "failed", "recovered"}


def monthly(seed: int) -> dict[str, metrics.ServiceMetrics]:
    events = simulation.simulate(seed)
    start, end = metrics.window_of(events)
    return {name: metrics.compute(events, name, start, end) for name in metrics.services(events)}


def known(value: float | None) -> float:
    assert value is not None
    return value


def test_small_changes_beat_the_weekly_batch_on_all_four_metrics_for_the_default_seed():
    table = monthly(7)
    small, batch = table["orders"], table["billing"]
    assert small.deploys_per_week > batch.deploys_per_week * 3
    assert known(small.median_lead_time_hours) < known(batch.median_lead_time_hours) / 5
    assert known(small.change_fail_rate) < known(batch.change_fail_rate)
    assert known(small.median_recovery_minutes) < known(batch.median_recovery_minutes) / 2


def test_the_pattern_holds_across_seeds_not_just_for_one():
    compared = 0
    for seed in range(20):
        small, batch = monthly(seed)["orders"], monthly(seed)["billing"]
        assert known(small.median_lead_time_hours) < known(batch.median_lead_time_hours)
        assert small.deploys_per_week > batch.deploys_per_week
        # a team that deploys once a week may see no failure in a month: then there is no recovery time to compare
        if small.median_recovery_minutes is not None and batch.median_recovery_minutes is not None:
            compared += 1
            assert small.median_recovery_minutes < batch.median_recovery_minutes
    assert compared >= 10


def test_the_weekly_batch_team_deploys_only_on_fridays():
    events = simulation.simulate(7)
    assert {e.ts.weekday() for e in events if e.service == "billing" and e.type.value == "deploy"} == {4}
```

- **Lines 124 to 141**: seven strings that look like long-lived credentials (an AWS key id, an AWS secret assignment, two private-key headers, a GitHub token, two stored workflow secrets) each give exactly `{"GP-SECRET"}`; a clean file gives nothing. **Lines 144 to 146**: `__NAME__` is a leftover placeholder (`GP-PLACEHOLDER`); `__init__ and __main__` are not (the pattern needs capital letters). **Lines 149 to 151**: `summarize` says "conforms" or lists codes.
- **Line 154 to 156**: `catalog/teams.yaml` lists a team for each demo service.
- **Lines 159 to 161**: the same seed gives the same month; a different seed a different one. **Lines 164 to 167**: the simulation covers the three teams and all four event types.
- **Lines 170 to 187**: `monthly(seed)` computes each team's metrics; `known(value)` asserts a value is not `None` so the comparison type-checks. With the default seed, small changes beat the weekly batch on all four measures: more than three times the deployment frequency, under a fifth of the lead time, a lower fail rate, under half the recovery time. **Lines 190 to 200**: the same holds for 20 seeds (recovery time compared only when both teams had a failure; at least 10 seeds must allow the comparison). **Lines 203 to 205**: the batch team deploys only on Fridays (`weekday() == 4`).

### `tests/unit/application/test_use_cases.py`: the use cases with fakes

```python
class MemoryStore:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, events: Iterable[Event]) -> int:
        new = [event for event in events if event not in self.events]
        self.events.extend(new)
        return len(new)

    def all(self) -> list[Event]:
        return sorted(self.events, key=lambda event: event.ts)

    def clear(self) -> None:
        self.events.clear()


class Renderer:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, Mapping[str, str]]] = []

    def render(self, destination: Path, substitutions: Mapping[str, str]) -> list[str]:
        self.calls.append((destination, substitutions))
        return ["README.md", "Makefile"]


class MemoryCatalog:
    def __init__(self) -> None:
        self.registered: list[CatalogEntry] = []

    def teams(self) -> frozenset[str]:
        return frozenset({"team-orders"})

    def register(self, entry: CatalogEntry) -> None:
        self.registered.append(entry)

    def entries(self) -> list[CatalogEntry]:
        return self.registered


class Repositories:
    def __init__(self) -> None:
        self.created: list[str] = []

    def create(self, directory: Path, name: str, message: str) -> str:
        self.created.append(name)
        return "c0ffee" * 6


class Auditor:
    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings

    def audit(self, directory: Path) -> list[Finding]:
        return self.findings


def generator(findings: list[Finding] | None = None) -> tuple[ServiceGenerator, Renderer, MemoryCatalog, Repositories]:
    renderer, catalog, repositories = Renderer(), MemoryCatalog(), Repositories()
    clock = iter(range(100))
    return (
        ServiceGenerator(
            renderer, catalog, repositories, Auditor(findings or []), "f" * 40, clock=lambda: float(next(clock))
        ),
        renderer,
        catalog,
        repositories,
    )
```

- **Lines 16 to 70**: small fake classes that satisfy the ports without inheriting from anything: `MemoryStore` (events in a list), `Renderer` (records its calls and returns two file names), `MemoryCatalog` (one team, `team-orders`), `Repositories` (records the names created and returns a fake commit id), `Auditor` (returns the findings it was given).
- **Lines 72 to 82**, `generator(findings)`: wires a `ServiceGenerator` from the fakes; `clock = iter(range(100))` and `clock=lambda: float(next(clock))` make a fake clock that returns 0.0, 1.0, 2.0, ... each time it is called.

```python
def test_a_service_is_rendered_audited_registered_and_published_in_that_order():
    service_generator, renderer, catalog, repositories = generator()
    service = service_generator.generate(
        "orders", "team-orders", Path("/tmp/orders"), "https://wiki.example.com/runbooks"
    )
    assert renderer.calls[0][1]["__NAME__"] == "orders"
    assert renderer.calls[0][1]["__PLATFORM_REF__"] == "f" * 40
    assert [entry.name for entry in catalog.registered] == ["orders"]
    assert repositories.created == ["orders"]
    assert service.entry.runbook == "https://wiki.example.com/runbooks/orders"
    assert set(service.timings) == {"render", "audit", "publish"}


def test_a_person_as_owner_is_refused_before_anything_is_rendered():
    service_generator, renderer, _, repositories = generator()
    with pytest.raises(InvalidCatalogEntryError, match="not a person"):
        service_generator.generate("orders", "alice", Path("/tmp/x"), "https://wiki.example.com/runbooks")
    assert renderer.calls == []
    assert repositories.created == []


def test_a_repository_that_fails_the_audit_is_never_registered_or_published():
    finding = Finding("GP-SIGN", "signed artifacts", "no step signs the artifact")
    service_generator, _, catalog, repositories = generator([finding])
    with pytest.raises(NonConformingServiceError) as error:
        service_generator.generate("orders", "team-orders", Path("/tmp/x"), "https://wiki.example.com/runbooks")
    assert error.value.findings == [finding]
    assert catalog.registered == []
    assert repositories.created == []


def test_events_are_recorded_once_even_when_sent_twice():
    store = MemoryStore()
    event = Event(datetime(2026, 9, 1, tzinfo=UTC), "orders", EventType.COMMIT, "a1")
    assert record(store, [event]) == 1
    assert record(store, [event]) == 0


def test_every_deployment_of_a_service_is_listed_with_its_commits():
    store = MemoryStore()
    when = datetime(2026, 9, 1, 14, tzinfo=UTC)
    record(
        store, [Event(when, "orders", EventType.DEPLOY, "d1:a1+a2"), Event(when, "billing", EventType.DEPLOY, "e1:b1")]
    )
    assert list_deployments(store, "orders") == [("2026-09-01 14:00", "d1", ("a1", "a2"))]


def test_measuring_an_empty_store_says_what_to_do():
    with pytest.raises(measure.NoEventsError, match="empty"):
        measure.summary(MemoryStore())
    with pytest.raises(measure.NoEventsError):
        measure.per_week(MemoryStore())


def test_the_summary_and_the_trace_read_the_store():
    store = MemoryStore()
    record(
        store,
        [
            Event(datetime(2026, 9, 1, 9, tzinfo=UTC), "orders", EventType.COMMIT, "a1"),
            Event(datetime(2026, 9, 1, 14, tzinfo=UTC), "orders", EventType.DEPLOY, "d1:a1"),
        ],
    )
    (row,) = measure.summary(store)
    assert row.median_lead_time_hours == 5.0
    assert measure.trace(store, "orders", "a1").hours == 5.0
    assert [index for index, _ in measure.per_week(store)] == [1]


def test_the_lessons_sample_services_are_left_out_of_a_summary_unless_asked_for():
    store = MemoryStore()
    when = datetime(2026, 9, 1, 9, tzinfo=UTC)
    record(store, [Event(when, "sample-orders", EventType.COMMIT, "a1"), Event(when, "orders", EventType.COMMIT, "o1")])
    assert [row.service for row in measure.summary(store)] == ["orders"]
    assert [row.service for row in measure.summary(store, include_samples=True)] == ["orders", "sample-orders"]
    assert [row.service for _, rows in measure.per_week(store) for row in rows] == ["orders"]
```

- **Lines 85 to 95**: a service is rendered with the right substitutions, registered, published, and has the runbook `.../runbooks/orders` and the three timings. **Lines 98 to 103**: a person as owner raises `InvalidCatalogEntryError` and **nothing was rendered or published**. **Lines 106 to 113**: a failed audit raises `NonConformingServiceError` carrying the findings; nothing is registered or published.
- **Lines 116 to 120**: `record(store, [event])` returns 1 and then 0 for the same event. **Lines 123 to 129**: `list_deployments` lists only the named service's deployments with their commits. **Lines 132 to 136**: measuring an empty store raises `NoEventsError`. **Lines 139 to 151**: a commit at 09:00 and its deployment at 14:00 give a 5.0-hour lead time; the trace gives the same; one week. **Lines 154 to 160**: `sample-` services are left out of a summary unless `include_samples=True`.

### `tests/unit/infrastructure/test_adapters.py`: the adapters

```python
def test_the_csv_store_round_trips_events_and_ignores_a_duplicate(tmp_path):
    store = CsvEventStore(tmp_path / "events.csv")
    events = [Event(NOW, "orders", EventType.COMMIT, "a1"), Event(NOW, "orders", EventType.FAILED, "d1", "rollback")]
    assert store.append(events) == 2
    assert store.append(events) == 0
    assert store.all() == events
    store.clear()
    assert store.all() == []


def test_the_csv_store_reads_the_lessons_four_column_sample():
    events = CsvEventStore(ROOT / "data" / "events-sample.csv").all()
    assert len(events) == 18
    assert events[0] == Event(datetime(2026, 9, 1, 9, 0, tzinfo=UTC), "orders", EventType.COMMIT, "a1")


def test_settings_have_defaults_and_the_password_has_none():
    settings = Settings.from_env({"POSTGRES_PASSWORD": "pw"})
    assert (settings.postgres_port, settings.collector_port, settings.workdir) == (5432, 55442, Path(".local"))
    with pytest.raises(ConfigurationError, match="POSTGRES_PASSWORD"):
        Settings.from_env({})
    assert Settings.from_env({}, need_database=False).postgres_password == ""


@pytest.mark.parametrize(
    ("name", "value"),
    [("POSTGRES_PORT", "0"), ("COLLECTOR_PORT", "abc"), ("POSTGRES_HOST", "a b"), ("LOG_LEVEL", "LOUD")],
)
def test_an_unusable_setting_names_its_variable(name, value):
    with pytest.raises(ConfigurationError, match=name):
        Settings.from_env({"POSTGRES_PASSWORD": "pw", name: value})


def test_the_connection_uri_escapes_the_password():
    assert (
        Settings.from_env({"POSTGRES_PASSWORD": "p@ss/w"}).dsn
        == "postgresql://platform:p%40ss%2Fw@localhost:5432/events"
    )


def test_a_log_record_is_one_logfmt_line_and_the_stream_gets_it():
    record = logging.LogRecord("goldenpath", logging.INFO, __file__, 1, "two words", None, None)
    record.fields = {"service": "orders"}
    assert LogfmtFormatter().format(record).endswith('msg="two words" service=orders')
    stream = io.StringIO()
    configure_logging("INFO", stream)
    logging.getLogger("x").info("hi", extra=fields(a=1))
    assert "msg=hi a=1" in stream.getvalue()

```

- **Lines 29 to 36**: the CSV store round-trips two events, ignores a duplicate (`append` returns 2 then 0) and `clear` empties it. **Lines 39 to 42**: it reads the lesson's four-column sample: 18 events, the first being commit `a1`. **Lines 45 to 50**: settings have defaults (port 5432, collector port 55442, workdir `.local`), the password has none, and `need_database=False` allows an empty password. **Lines 53 to 59**: four unusable values each name their variable in the error. **Lines 62 to 66**: the connection string escapes `p@ss/w` as `p%40ss%2Fw`. **Lines 69 to 76**: a log record is one logfmt line ending `msg="two words" service=orders`, and `configure_logging` writes to a given stream (`io.StringIO` is an in-memory text stream).

```python
def test_rendering_replaces_every_placeholder_and_keeps_scripts_executable(tmp_path):
    destination = tmp_path / "orders"
    written = FileTemplateRenderer(ROOT / "template").render(
        destination,
        {"__NAME__": "orders", "__OWNER__": "team-orders", "__RUNBOOK__": "https://x/r", "__PLATFORM_REF__": "f" * 40},
    )
    assert "Makefile" in written
    assert "orders" in (destination / "catalog-info.yaml").read_text()
    assert not any("__NAME__" in text for text in read_text_files(destination).values())
    assert (destination / "scripts" / "deploy.sh").stat().st_mode & 0o111


def test_rendering_into_an_existing_folder_is_refused(tmp_path):
    with pytest.raises(FileExistsError):
        FileTemplateRenderer(ROOT / "template").render(tmp_path, {})


def render(tmp_path: Path, name: str = "orders", owner: str = "team-orders") -> Path:
    destination = tmp_path / name
    FileTemplateRenderer(ROOT / "template").render(
        destination,
        {
            "__NAME__": name,
            "__OWNER__": owner,
            "__RUNBOOK__": "https://wiki.example.com/r",
            "__PLATFORM_REF__": "f" * 40,
        },
    )
    return destination


def auditor() -> RepositoryAuditor:
    return RepositoryAuditor(FileCatalog(ROOT / "catalog" / "teams.yaml", Path("/nonexistent")))


def test_a_freshly_generated_repository_conforms(tmp_path):
    assert auditor().audit(render(tmp_path)) == []


def test_a_repository_whose_signing_step_was_deleted_fails_the_audit(tmp_path):
    repo = render(tmp_path)
    workflow = repo / ".github" / "workflows" / "ci.yml"
    workflow.write_text(workflow.read_text().replace("      - run: make sign\n", ""))
    assert "GP-SIGN" in {finding.code for finding in auditor().audit(repo)}


def test_a_stored_cloud_key_in_the_repository_fails_the_audit(tmp_path):
    repo = render(tmp_path)
    (repo / "deploy" / "creds.env").write_text("AWS_KEY=AKIAABCDEFGHIJKLMNOP\n")
    assert "GP-SECRET" in {finding.code for finding in auditor().audit(repo)}


def test_a_person_as_owner_fails_the_audit_through_the_catalog_entry(tmp_path):
    repo = render(tmp_path, owner="alice")
    assert "GP-CATALOG" in {finding.code for finding in auditor().audit(repo)}


def test_missing_protection_and_catalog_files_are_findings(tmp_path):
    repo = render(tmp_path)
    (repo / "protection.json").unlink()
    (repo / "catalog-info.yaml").unlink()
    codes = {finding.code for finding in auditor().audit(repo)}
    assert {"GP-CHECKS", "GP-CATALOG"} <= codes


def test_a_repository_with_no_workflow_is_a_finding(tmp_path):
    repo = render(tmp_path)
    (repo / ".github" / "workflows" / "ci.yml").unlink()
    assert "GP-NOWORKFLOW" in {finding.code for finding in auditor().audit(repo)}


def test_the_workflow_loader_puts_the_on_key_back():
    assert "push" in load_workflow("on:\n  push:\njobs: {}\n")["on"]
    with pytest.raises(ValueError, match="mapping"):
        load_workflow("- a\n")


def test_the_catalog_registers_replaces_and_lists_entries(tmp_path):
    catalog = FileCatalog(ROOT / "catalog" / "teams.yaml", tmp_path / "entities")
    assert catalog.entries() == []
    entry = CatalogEntry("orders", "team-orders", "production", "https://x/r", "99.9%")
    catalog.register(entry)
    catalog.register(CatalogEntry("orders", "team-orders", "deprecated", "https://x/r", "99.9%"))
    assert [item.lifecycle for item in catalog.entries()] == ["deprecated"]
    assert "team-platform" in catalog.teams()

```

- **Lines 79 to 88**: rendering replaces every placeholder (no file text still contains `__NAME__`) and keeps scripts executable (`stat().st_mode & 0o111` tests the execute permission bits). **Lines 91 to 93**: rendering into an existing folder raises `FileExistsError`. **Lines 96 to 111**: helpers `render(...)` and `auditor()`.
- **Lines 114 to 147**: audit tests on a freshly rendered repository: it conforms; deleting the `make sign` line gives `GP-SIGN`; a file `deploy/creds.env` containing an AWS key gives `GP-SECRET`; an owner `alice` gives `GP-CATALOG`; deleting `protection.json` and `catalog-info.yaml` gives `GP-CHECKS` and `GP-CATALOG`; deleting the workflow gives `GP-NOWORKFLOW`. **Lines 150 to 153**: the workflow loader restores the `on` key and rejects a list. **Lines 156 to 163**: the catalog registers, replaces and lists entries (registering the same name again replaces the file) and knows `team-platform`. **Lines 166 to 173**: a service with only a commit prints `n/a` four times in the metrics table. **Lines 176 to 180**: `event_from_json` defaults to the collector's clock and refuses an unknown type.

```python
@pytest.fixture
def collector(tmp_path: Path) -> Iterator[tuple[str, CsvEventStore]]:
    store = CsvEventStore(tmp_path / "events.csv")
    server = collector_server(0, store, "secret-token", clock=lambda: NOW)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", store
    server.shutdown()
    server.server_close()


def post(url: str, body: bytes, token: str | None = "secret-token") -> tuple[int, dict[str, object]]:
    headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url + "/events", data=body, headers=headers, method="POST")
        ) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_the_collector_accepts_an_authorized_event_and_stores_it_once(collector):
    url, store = collector
    body = json.dumps({"service": "orders", "type": "commit", "ref": "a1"}).encode()
    assert post(url, body) == (202, {"accepted": 1, "received": 1})
    assert post(url, body) == (202, {"accepted": 0, "received": 1})
    assert store.all() == [Event(NOW, "orders", EventType.COMMIT, "a1")]


def test_the_collector_refuses_a_missing_or_wrong_token(collector):
    url, store = collector
    body = json.dumps({"service": "orders", "type": "commit", "ref": "a1"}).encode()
    assert post(url, body, token=None)[0] == 401
    assert post(url, body, token="wrong")[0] == 401
    assert store.all() == []


@pytest.mark.parametrize(
    "body", [b"not json", b"[]{", json.dumps({"service": "X", "type": "commit", "ref": "a1"}).encode(), b"{}"]
)
def test_the_collector_refuses_a_malformed_or_invalid_event(collector, body):
    assert post(collector[0], body)[0] == 400


def test_the_collector_refuses_an_empty_or_oversized_body_and_unknown_paths(collector):
    url, _ = collector
    assert post(url, b"")[0] == 400
    assert post(url, b"x" * (64 * 1024 + 1))[0] == 413
    assert urllib.request.urlopen(url + "/healthz").status == 200
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(url + "/nope")


def test_the_client_sends_a_batch_and_reads_how_many_were_new(collector):
    url, store = collector
    sink = CollectorEventSink(url, "secret-token")
    assert (
        sink.append([Event(NOW, "orders", EventType.COMMIT, "a1"), Event(NOW, "orders", EventType.DEPLOY, "d1:a1")])
        == 2
    )
    assert len(store.all()) == 2


def test_the_client_reports_a_refusal_and_an_unreachable_collector(collector):
    url, _ = collector
    with pytest.raises(CollectorError, match="401"):
        CollectorEventSink(url, "wrong").append([Event(NOW, "orders", EventType.COMMIT, "a1")])
    with pytest.raises(CollectorError, match="could not be reached"):
        CollectorEventSink("http://127.0.0.1:1", "t", timeout_seconds=0.5).append(
            [Event(NOW, "orders", EventType.COMMIT, "a1")]
        )
    with pytest.raises(ValueError, match="http"):
        CollectorEventSink("file:///x", "t")


def test_a_collector_with_no_token_configured_refuses_everything(tmp_path):
    server = collector_server(0, CsvEventStore(tmp_path / "e.csv"), "")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert post(f"http://127.0.0.1:{server.server_address[1]}", b"{}", token="")[0] == 401
    finally:
        server.shutdown()
        server.server_close()


class BrokenStore:
    def append(self, events):
        raise ConnectionError("database is down")


def test_a_collector_whose_store_is_down_answers_503_instead_of_hanging():
    server = collector_server(0, BrokenStore(), "t", clock=lambda: NOW)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        body = json.dumps({"service": "orders", "type": "commit", "ref": "a1"}).encode()
        assert post(f"http://127.0.0.1:{server.server_address[1]}", body, token="t")[0] == 503
    finally:
        server.shutdown()
        server.server_close()
```

- **Lines 183 to 190**: the fixture `collector` starts a real collector on port 0 (the operating system picks a free port) on a daemon thread, with a CSV store and a fake clock, `yield`s its address and the store, and afterwards shuts it down. **Lines 193 to 201**: `post(url, body, token)` sends a real HTTP request with `urllib` and returns the status and the JSON.
- **Lines 204 to 209**: an authorized event is accepted (202) and stored once; the same body again gives `accepted: 0`. **Lines 212 to 217**: no token and a wrong token are both 401 and nothing is stored. **Lines 220 to 224**: four bad bodies (not JSON, broken JSON, an invalid event, an empty object) are 400. **Lines 227 to 233**: an empty body is 400, one byte over 64 KiB is 413, `/healthz` is 200 and `/nope` raises a 404 `HTTPError`.
- **Lines 236 to 255**: the client sends a batch and reads that 2 were new; reports a 401 refusal and an unreachable collector (`127.0.0.1:1`) as `CollectorError`; and refuses a `file:///x` address. **Lines 258 to 265**: a collector with an empty token refuses everything. **Lines 268 to 281**: `BrokenStore.append` raises `ConnectionError`; the collector answers **503**, not a hang or a crash.

### `tests/unit/interfaces/test_cli.py`: the command line

```python
@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GOLDENPATH_WORKDIR", str(tmp_path / "local"))
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)


def test_the_metrics_table_for_the_sample_has_the_lessons_numbers(capsys):
    assert cli.main(["metrics", "--csv", SAMPLE]) == cli.EXIT_OK
    rows = {line.split()[0]: line.split() for line in capsys.readouterr().out.splitlines()[1:]}
    assert rows["orders"][1:7] == ["4", "4.0", "h", "25%", "30", "min"]
    assert rows["billing"][1:7] == ["1", "62.0", "h", "100%", "240", "min"]


def test_the_weekly_table_prints_one_block_per_week(capsys):
    assert cli.main(["metrics", "--csv", SAMPLE, "--weekly"]) == cli.EXIT_OK
    assert "week 1" in capsys.readouterr().out


def test_a_lead_time_is_traced_to_its_two_events(capsys):
    assert cli.main(["trace", "orders", "a5", "--csv", SAMPLE]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "commit event:  2026-09-04 16:00  orders  commit  a5" in out
    assert "deploy event:  2026-09-07 10:00  orders  deploy  d4:a5" in out
    assert "lead time:     66.0 h" in out


def test_tracing_an_unknown_commit_exits_with_the_usage_code(capsys):
    assert cli.main(["trace", "orders", "zzz", "--csv", SAMPLE]) == cli.EXIT_USAGE
    assert "no commit" in capsys.readouterr().err


def test_every_deployment_is_listed_with_its_commits(capsys):
    assert cli.main(["deployments", "billing", "--csv", SAMPLE]) == cli.EXIT_OK
    assert "e1  commits: b1, b2, b3, b4" in capsys.readouterr().out


def test_a_person_as_owner_is_refused_with_the_usage_code(capsys):
    assert cli.main(["new-service", "orders", "alice"]) == cli.EXIT_USAGE
    assert "not a person" in capsys.readouterr().err


def test_a_service_is_generated_audited_and_listed(capsys):
    assert cli.main(["new-service", "orders", "team-orders"]) == cli.EXIT_OK
    assert "conforms to the golden path contract" in capsys.readouterr().out
    assert cli.main(["catalog"]) == cli.EXIT_OK
    assert "orders" in capsys.readouterr().out

```

- **Lines 13 to 16**: `@pytest.fixture(autouse=True)` runs before every test in the file: `monkeypatch.setenv("GOLDENPATH_WORKDIR", ...)` points the working folder at a temporary one and `delenv("POSTGRES_PASSWORD")` removes the password.
- **Lines 19 to 23**: `metrics --csv SAMPLE` prints the lesson's numbers for both services. **Lines 26 to 28**: `--weekly` prints `week 1`. **Lines 31 to 36**: `trace orders a5` prints the commit event, the deploy event and `lead time:     66.0 h`. **Lines 39 to 41**: an unknown commit exits with the usage code and "no commit" on standard error. **Lines 44 to 46**: `deployments billing` lists `e1  commits: b1, b2, b3, b4`. **Lines 49 to 51**: owner `alice` is refused with the usage code ("not a person"). **Lines 54 to 58**: `new-service orders team-orders` succeeds and prints "conforms to the golden path contract", and `catalog` then lists it.

```python
def test_the_audit_command_passes_a_generated_repository_and_fails_a_tampered_one(tmp_path, capsys):
    repo = tmp_path / "repo"
    FileTemplateRenderer(ROOT / "template").render(
        repo,
        {"__NAME__": "orders", "__OWNER__": "team-orders", "__RUNBOOK__": "https://x/r", "__PLATFORM_REF__": "f" * 40},
    )
    assert cli.main(["audit", str(repo)]) == cli.EXIT_OK
    workflow = repo / ".github" / "workflows" / "ci.yml"
    workflow.write_text(workflow.read_text().replace("      - run: make verify\n", ""))
    assert cli.main(["audit", str(repo)]) == cli.EXIT_FAILED
    assert "GP-VERIFY" in capsys.readouterr().out


def test_emitting_to_a_collector_that_is_not_running_exits_with_the_failure_code(monkeypatch, capsys):
    monkeypatch.setenv("COLLECTOR_URL", "http://127.0.0.1:1")
    assert cli.main(["emit", "commit", "orders", "a1"]) == cli.EXIT_FAILED
    assert "could not be reached" in capsys.readouterr().err


def test_a_bad_environment_value_exits_with_the_usage_code(monkeypatch, capsys):
    monkeypatch.setenv("COLLECTOR_PORT", "abc")
    assert cli.main(["catalog"]) == cli.EXIT_USAGE
    assert "COLLECTOR_PORT" in capsys.readouterr().err


def test_the_collector_refuses_to_start_without_a_token(monkeypatch, capsys):
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw")
    monkeypatch.delenv("COLLECTOR_TOKEN", raising=False)
    assert cli.main(["collector"]) == cli.EXIT_USAGE
    assert "COLLECTOR_TOKEN" in capsys.readouterr().err


def test_the_parser_requires_a_command():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_the_file_catalog_is_empty_before_any_service_exists(tmp_path):
    assert FileCatalog(ROOT / "catalog" / "teams.yaml", tmp_path / "none").entries() == []
```

- **Lines 61 to 71**: `audit` passes a freshly rendered repository and fails after the `make verify` line is removed (exit 1, `GP-VERIFY` printed). **Lines 74 to 77**: `emit` to a collector that is not running exits with the failure code and "could not be reached". **Lines 80 to 83**: `COLLECTOR_PORT=abc` exits with the usage code. **Lines 86 to 90**: the collector refuses to start without a token. **Lines 93 to 95**: the parser requires a command (`SystemExit`). **Lines 98 to 99**: the file catalog is empty before any service exists.

### `tests/template/test_generated_service.py`

```python
def make_generator(workdir: Path) -> tuple[ServiceGenerator, FileCatalog]:
    catalog = FileCatalog(ROOT / "catalog" / "teams.yaml", workdir / "catalog")
    generator = ServiceGenerator(
        FileTemplateRenderer(ROOT / "template"),
        catalog,
        GitRepositories(workdir / "remotes"),
        RepositoryAuditor(catalog),
        "a" * 40,
    )
    return generator, catalog


@pytest.mark.parametrize(("name", "owner"), TEAMS)
def test_a_service_for_each_team_is_generated_and_its_own_ci_passes(tmp_path, name, owner):
    generator, catalog = make_generator(tmp_path)
    service = generator.generate(name, owner, tmp_path / "services" / name, "https://wiki.example.com/runbooks")
    done = subprocess.run(["make", "--no-print-directory", "ci"], cwd=service.directory, capture_output=True, text=True, check=False)  # noqa: S603, S607
    assert done.returncode == 0, done.stdout + done.stderr
    assert "OK" in done.stderr
    assert [entry.name for entry in catalog.entries()] == [name]


def test_the_generated_repository_is_published_and_its_commit_is_on_the_remote(tmp_path):
    generator, _ = make_generator(tmp_path)
    service = generator.generate("orders", "team-orders", tmp_path / "services" / "orders", "https://wiki.example.com/runbooks")
    remote = tmp_path / "remotes" / "orders.git"
    head = subprocess.run(["git", "rev-parse", "main"], cwd=remote, capture_output=True, text=True, check=True).stdout.strip()  # noqa: S603, S607
    assert head == service.commit
    assert len(commits_since(service.directory, None)) == 1


def test_no_generated_file_holds_a_long_lived_credential_or_a_placeholder(tmp_path):
    generator, catalog = make_generator(tmp_path)
    service = generator.generate("search", "team-search", tmp_path / "services" / "search", "https://wiki.example.com/runbooks")
    assert RepositoryAuditor(catalog).audit(service.directory) == []
    assert "team-search" in (service.directory / "README.md").read_text()
```

- **Lines 18 to 27**: `make_generator(workdir)` builds a `ServiceGenerator` with the **real** renderer, file catalog, Git repositories and auditor.
- **Lines 30 to 37**: `@pytest.mark.parametrize(("name", "owner"), TEAMS)` runs once per team. It generates the service, runs the real `make ci` inside it (`subprocess.run(["make", "--no-print-directory", "ci"], cwd=service.directory, ...)`), asserts exit status 0 and `"OK"` in the output (`unittest` prints `OK` on standard error), and that the catalog lists the service.
- **Lines 40 to 46**: the published remote's `main` equals the returned commit, and the service has exactly one commit. **Lines 49 to 53**: a freshly generated service has no audit findings and its README names the team.

### `tests/integration/`: against the real database

```python
"""Integration tests need PostgreSQL from docker-compose.yml: `make up` first."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from goldenpath.infrastructure.postgres_store import PostgresEventStore
from goldenpath.infrastructure.settings import Settings


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings.from_env()


@pytest.fixture
def store(settings: Settings) -> Iterator[PostgresEventStore]:
    """A store whose rows for the test services are removed before and after, so tests never see each other's data."""
    cleanup(settings)
    yield PostgresEventStore(settings.dsn)
    cleanup(settings)


def cleanup(settings: Settings) -> None:
    with psycopg.connect(settings.dsn) as connection:
        connection.execute("DELETE FROM events WHERE service LIKE 'it-%'")
```

- **Lines 16 to 18**: a pytest **hook** (pytest calls it by name) adds the `integration` marker to every test in the folder. **Lines 21 to 23**: `settings` is built once from the real environment (`scope="session"`). **Lines 26 to 31**: `store` cleans up, `yield`s a `PostgresEventStore` and cleans up again. **Lines 34 to 36**: `cleanup` deletes every row whose service starts with `it-` ([psycopg.md](psycopg.md)).

```python
def sample_with_prefix() -> list[Event]:
    return [
        Event(event.ts, f"it-{event.service}", event.type, event.ref, event.detail)
        for event in CsvEventStore(ROOT / "data" / "events-sample.csv").all()
    ]


def test_events_round_trip_and_a_duplicate_is_ignored(store):
    events = [
        Event(NOW, "it-orders", EventType.COMMIT, "a1"),
        Event(NOW, "it-orders", EventType.FAILED, "d1", "rollback"),
    ]
    assert store.append(events) == 2
    assert store.append(events) == 0
    assert [event for event in store.all() if event.service == "it-orders"] == events


def test_the_schema_refuses_what_the_domain_refuses(store, settings):
    with psycopg.connect(settings.dsn) as connection, pytest.raises(psycopg.errors.CheckViolation):
        connection.execute("INSERT INTO events (ts, service, type, ref) VALUES (now(), 'it-x', 'teleport', 'a1')")
    with psycopg.connect(settings.dsn) as connection, pytest.raises(psycopg.errors.CheckViolation):
        connection.execute("INSERT INTO events (ts, service, type, ref) VALUES (now(), 'it-x', 'deploy', 'no-colon')")
    with psycopg.connect(settings.dsn) as connection, pytest.raises(psycopg.errors.CheckViolation):
        connection.execute(
            "INSERT INTO events (ts, service, type, ref, detail) VALUES (now(), 'it-x', 'commit', 'a1', 'why')"
        )


def test_sql_and_python_give_the_lessons_numbers_for_the_sample(store, settings):
    store.append(sample_with_prefix())
    events = [event for event in store.all() if event.service.startswith("it-")]
    start, end = metrics.window_of(events)
    python = {
        row.service: row for row in (metrics.compute(events, name, start, end) for name in metrics.services(events))
    }
    with psycopg.connect(settings.dsn) as connection:
        rows = connection.execute(
            """
            WITH real AS (
              SELECT DISTINCT service, deploy_id, deployed_at FROM deploy_commits
              WHERE commit_ref IS NOT NULL AND service LIKE 'it-%'
            )
            SELECT r.service,
                   count(*),
                   (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY l.hours)
                    FROM lead_times l WHERE l.service = r.service),
                   (SELECT count(DISTINCT f.ref) FROM events f WHERE f.service = r.service AND f.type = 'failed')
            FROM real r GROUP BY r.service ORDER BY r.service
            """
        ).fetchall()
    sql = {service: (deploys, lead, failed) for service, deploys, lead, failed in rows}
    assert sql["it-orders"] == (4, 4.0, 1)
    assert sql["it-billing"] == (1, 62.0, 1)
    assert python["it-orders"].median_lead_time_hours == sql["it-orders"][1]
    assert python["it-billing"].median_lead_time_hours == sql["it-billing"][1]
    assert python["it-orders"].change_fail_rate == sql["it-orders"][2] / sql["it-orders"][0]
```

- **Lines 20 to 24**: `sample_with_prefix()` reads the lesson's CSV and renames each service `it-orders`/`it-billing`, so test rows never mix with real ones. **Lines 27 to 34**: events round-trip and a duplicate is ignored. **Lines 37 to 45**: three bad `INSERT`s straight into the table (an unknown type, a deploy without a colon, a detail on a commit) each raise `psycopg.errors.CheckViolation`: the database defends itself ([postgresql.md](postgresql.md)).
- **Lines 48 to 75**: the heart: load the sample, compute the metrics in Python, run an SQL query over `deploy_commits`, `lead_times` and `events`, and assert the SQL gives `(4, 4.0, 1)` for `it-orders` and `(1, 62.0, 1)` for `it-billing` and that Python agrees (`python["it-orders"].change_fail_rate == 1 / 4`).

```python
def test_the_queries_file_runs_against_the_seed_and_prints_the_lessons_table(settings):
    seed = (ROOT / "sql" / "002_seed.sql").read_text()
    queries = (ROOT / "sql" / "003_queries.sql").read_text()
    with psycopg.connect(settings.dsn) as connection:
        connection.execute(seed)
        results = []
        for statement in [part for part in queries.split(";\n") if part.strip() and "SELECT" in part]:
            results.append(connection.execute(statement).fetchall())
    deployments, trace, table = results
    assert [row[1] for row in deployments] == ["d1", "d2", "d3", "d4"]
    assert trace[0][0] == "a5"
    assert float(trace[0][4]) == 66.0
    assert [tuple(float(value) for value in row[1:]) for row in table] == [
        (1.0, 62.0, 100.0, 240.0),
        (4.0, 4.0, 25.0, 30.0),
    ]


def test_the_deployments_view_lists_every_deployment_with_its_commits_and_an_empty_one(store, settings):
    store.append(
        [
            Event(NOW, "it-orders", EventType.DEPLOY, "d1:a1+a2"),
            Event(NOW, "it-orders", EventType.DEPLOY, "d2:"),
        ]
    )
    with psycopg.connect(settings.dsn) as connection:
        rows = connection.execute(
            "SELECT deploy_id, commit_ref FROM deploy_commits WHERE service = 'it-orders' "
            "ORDER BY deploy_id, commit_ref"
        ).fetchall()
    assert rows == [("d1", "a1"), ("d1", "a2"), ("d2", None)]


def test_the_cli_prints_the_sample_table_from_the_csv_without_a_database():
    done = subprocess.run(
        [str(ROOT / ".venv" / "bin" / "goldenpath"), "metrics", "--csv", str(ROOT / "data" / "events-sample.csv")],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = {line.split()[0]: line.split() for line in done.stdout.splitlines()[1:]}
    assert lines["orders"][1:7] == ["4", "4.0", "h", "25%", "30", "min"]
    assert lines["billing"][1:7] == ["1", "62.0", "h", "100%", "240", "min"]
```

- **Lines 78 to 93**: apply `sql/002_seed.sql`, split `sql/003_queries.sql` at `";\n"` into statements, run each `SELECT`, and assert the three results: deployments `d1` to `d4`; the trace of `a5` with 66.0 hours; and the metrics table rows `(1.0, 62.0, 100.0, 240.0)` and `(4.0, 4.0, 25.0, 30.0)`. **Lines 96 to 108**: the view lists `d1` with `a1` and `a2` and an empty deployment `d2` with `None`. **Lines 111 to 120**: the installed `goldenpath metrics --csv` command prints the lesson's numbers with no database.

### `tests/e2e/test_golden_path.py`

```python
"""One service from the command to its first production deployment, with a real registry, key and compose, and an
unsigned image refused. Needs Docker, cosign and `make up` first. Takes a few minutes."""

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.e2e


def goldenpath(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / ".venv" / "bin" / "goldenpath"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=check,
        timeout=1800,
    )


@pytest.fixture(scope="module", autouse=True)
def prerequisites() -> None:
    if shutil.which("cosign") is None or not (ROOT / ".local" / "keys" / "cosign.key").exists():
        pytest.skip("run `make up` first (needs cosign and Docker)")


@pytest.fixture(scope="module")
def first_deployment() -> Iterator[subprocess.CompletedProcess[str]]:
    shutil.rmtree(ROOT / ".local" / "services" / "it-e2e", ignore_errors=True)
    shutil.rmtree(ROOT / ".local" / "remotes" / "it-e2e.git", ignore_errors=True)
    yield goldenpath("new-service", "it-e2e", "team-orders", "--release")
    compose = ROOT / ".local" / "services" / "it-e2e" / "deploy" / "compose.yaml"
    subprocess.run(
        ["docker", "compose", "-p", "it-e2e-production", "-f", str(compose), "down", "-v"],
        env={**os.environ, "IMAGE_REF": "unused"},
        capture_output=True,
        check=False,
    )


def test_a_new_service_reaches_production_in_under_thirty_minutes(first_deployment):
    seconds = int(first_deployment.stdout.split("first production deployment in ")[1].split("s")[0])
    assert seconds < 1800


def test_the_first_deployment_is_listed_with_its_commit(first_deployment):
    done = goldenpath("deployments", "it-e2e")
    assert "it-e2e-d1" in done.stdout


def test_an_unsigned_image_is_refused_at_deployment(first_deployment):
    done = goldenpath("demo-unsigned", "it-e2e", check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "refused" in done.stdout
```

- **Lines 11 to 25**: `pytestmark = pytest.mark.e2e`; `goldenpath(*args, check=True)` runs the installed command with a 30-minute timeout. **Lines 27 to 30**: the autouse fixture `prerequisites` skips the module with a clear message unless cosign and the demo key exist. **Lines 33 to 44**: `first_deployment` (`scope="module"`: once for the file) removes earlier copies, runs `new-service it-e2e team-orders --release`, `yield`s the finished process, and then removes the service's containers with `docker compose ... down -v`.
- **Lines 47 to 49**: the time printed ("first production deployment in Ns") is under 1800 seconds. **Lines 52 to 54**: the deployment is listed (`it-e2e-d1`). **Lines 57 to 60**: `demo-unsigned` exits 0 and prints "refused". These need `make up` first and a few minutes.

## Try it yourself

```bash
make test
```
Expect a coverage table and a summary with no `FAIL Required test coverage`.

```bash
.venv/bin/python -m pytest tests/unit/domain -q
```
The pure tests, quick and with no setup.

```bash
.venv/bin/python -m pytest --collect-only -q tests | tail -3
```
Counts every test (the integration and e2e ones too) without running them.

```bash
.venv/bin/python -m pytest tests/e2e -q -rs
```
Without `make up` expect `skipped` with the reason `run \`make up\` first`.

## Mistakes people make

- Tests that call the real network or clock. Here the domain takes its inputs as arguments.
- Shared test data. The `it-` prefix isolates the database tests.
- A misspelled marker that selects zero tests; `--strict-markers` stops that.
- Treating a skipped test as a pass without reading the reason.
- Chasing 100% coverage with empty tests. The floor measures only the pure layers.

## Check yourself

1. Why does `make test` not include the integration tests? *They need a running database, so they are a separate target.*
2. What does `--fail-under=95` do? *Fails the build when domain and application coverage is below 95%.*
3. What does `yield` do in a fixture? *Gives the test its value; the code after it is the clean-up.*
4. What does `pytest.skip` do? *Reports the test as skipped with a reason.*
5. What does `parametrize` do? *Runs the same test with several inputs.*

## Further reading

- pytest: https://docs.pytest.org/en/stable/ (9.1.1)
- Fixtures: https://docs.pytest.org/en/stable/how-to/fixtures.html
- Parametrize: https://docs.pytest.org/en/stable/how-to/parametrize.html
- coverage.py: https://coverage.readthedocs.io/ (7.17.0), pytest-cov: https://pytest-cov.readthedocs.io/
