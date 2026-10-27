# pytest and coverage

## What it is

pytest is a Python test runner: you write functions named `test_...`; pytest finds and runs them and reports which passed. A test fails if an `assert` is false or an exception escapes. `pytest-cov` adds **coverage**, a measurement of which lines ran during the tests (done by `coverage`). Pinned: pytest 9.1.1, pytest-cov 7.1.0, coverage 7.17.0.

## Why this repository uses it

The platform has four kinds of test, matched to what they need:

| Folder | Needs | What it proves |
|---|---|---|
| `tests/unit/` | nothing | The domain (events, metrics, rules, simulation, catalog), the use cases with fakes, the adapters that need no network, the CLI. |
| `tests/template/` | `git`, `make` | The template, generated for three teams, passes the audit and its own `make ci`. |
| `tests/integration/` | PostgreSQL (`make up`) | The store, the collector and the SQL queries; SQL and Python give the same numbers. |
| `tests/e2e/` | Docker, cosign, registry (`make up`) | One service from the command to production, and an unsigned image refused. |

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` | `[tool.pytest.ini_options]`, `[tool.coverage.*]`. |
| `Makefile` | `test`, `test-integration`, `test-e2e`, `check`. |
| `tests/integration/conftest.py` | The `settings` and `store` fixtures and the clean-up. |
| `.github/workflows/ci.yml` | `make check` and `make test-integration`. |

## How it works underneath

pytest **collects** `test_*.py` files and `test_*` functions, runs each, and rewrites `assert` statements at import time so a failure shows both sides. A **fixture** (`@pytest.fixture`) is set-up code that a test requests by naming it as a parameter; code after a `yield` is the clean-up. A **marker** (`@pytest.mark.x`) labels tests; `-m x` selects them. Coverage traces the program and records which lines (and with `branch = true`, which branches) ran.

## Walkthrough of this repository's use

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra --strict-markers"
markers = [
    "integration: needs PostgreSQL from docker-compose.yml (make up)",
    "e2e: the golden path end to end with Docker, a local registry and cosign (make up first)",
]
```
`pythonpath = ["."]` puts the repository root on the import path (`from tests...`). `-ra` prints a summary for every test that did not plainly pass (skips included). `--strict-markers` turns a misspelled marker into an error.

```make
test:
	$(PY) -m pytest tests/unit tests/template -p no:cacheprovider --junitxml=reports/unit.xml --cov --cov-report=term
	$(PY) -m coverage report --include='src/goldenpath/domain/*,src/goldenpath/application/*' --fail-under=95
```
`make test` runs the two groups that need no Docker. `--junitxml` writes a report CI can read. The second command fails if the **domain and application** layers are below 95% covered: the pure rules (metrics, contract, catalog, simulation) are the part that must be fully tested. `tests/integration` and `tests/e2e` are separate targets because they need running services.

### An integration fixture that cleans up

```python
@pytest.fixture
def store(settings: Settings) -> Iterator[PostgresEventStore]:
    cleanup(settings)
    yield PostgresEventStore(settings.dsn)
    cleanup(settings)

def cleanup(settings: Settings) -> None:
    with psycopg.connect(settings.dsn) as connection:
        connection.execute("DELETE FROM events WHERE service LIKE 'it-%'")
```
Rows of test services (names starting `it-`) are deleted before and after each test, so tests never see each other's data and never touch the demo services' events. A hook `pytest_collection_modifyitems` marks every test in the folder `integration`.

### The end-to-end test skips itself politely

```python
@pytest.fixture(scope="module", autouse=True)
def prerequisites() -> None:
    if shutil.which("cosign") is None or not (ROOT / ".local" / "keys" / "cosign.key").exists():
        pytest.skip("run `make up` first (needs cosign and Docker)")
```
`autouse=True` runs it for every test in the module; `pytest.skip` reports "skipped" with the reason instead of a confusing failure. The tests then generate a service with `--release`, assert it reached production in under 1800 seconds, list its deployment, and check that an unsigned image is refused.

### Testing the template

`tests/template/test_generated_service.py` is parametrized over three teams (`@pytest.mark.parametrize(("name", "owner"), TEAMS)`): the same test runs for `orders`, `billing` and `search`, rendering the template, auditing it and running `make ci` inside the result.

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
