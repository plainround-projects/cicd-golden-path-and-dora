# `unittest` and `compileall` (the generated service's checks)

## What it is

A **test** is a small program that checks that another program behaves correctly. **`unittest`** is the testing framework that comes with Python (no installation). You write a *class* that extends `unittest.TestCase`; each method whose name starts with `test` is one test; inside it you call checks such as `self.assertEqual(a, b)`. `python3 -m unittest discover -s tests` finds every test file under `tests/` (files whose names start with `test`) and runs them all; it exits with 0 if all passed.

**`compileall`** is a standard-library module that compiles every `.py` file it finds into Python's internal form. Its useful side effect: a file with a **syntax error** (code that is not valid Python) fails to compile. So `python3 -m compileall -q app tests` is the cheapest possible "lint": it proves every file is at least valid Python. `-q` is quiet; the words after it are the folders to check.

## Why this repository uses it

A generated service must pass its own checks with **nothing installed except Python itself**: no pytest, no ruff, no virtual environment, no lock file. The template promises a service that runs on a bare Python image and a plain CI runner. So its checks use only the standard library. The platform's own tests, in contrast, use pytest ([pytest.md](pytest.md)).

## Where it appears

| Path | Use |
|---|---|
| `template/tests/test_app.py` | Three tests of the generated service's `answer()` function. |
| `template/Makefile` | `lint` runs `python3 -m compileall -q app tests`; `test` runs `python3 -m unittest discover -s tests`; `ci: lint test`. |
| `tests/template/test_generated_service.py` | The **platform** generates a service for three teams and runs `make ci` on each result. |

## How it works underneath

`unittest discover -s tests` imports every `test*.py` file under `tests/` (adding the working folder to Python's import path, so `from app.main import answer` works when run from the service's root), collects the `TestCase` classes, creates a fresh object of the class for each `test_` method and runs it. A failed `assert*` raises `AssertionError`; the runner records it and continues. At the end it prints `Ran 3 tests ... OK` or a list of failures, and sets the exit status.

## Walkthrough of this repository's use

### `template/tests/test_app.py`

<!-- fmt:off -->
```python
import json
import unittest

from app.main import answer


class AnswerTest(unittest.TestCase):
    def test_health_is_ok(self):
        self.assertEqual(answer("/healthz"), (200, "ok\n"))

    def test_root_names_the_service_and_its_owner(self):
        status, body = answer("/")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["service"], "__NAME__")
        self.assertEqual(json.loads(body)["owner"], "__OWNER__")

    def test_unknown_path_is_404(self):
        self.assertEqual(answer("/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()
```
<!-- fmt:on -->

- **Lines 1 and 2**: `import json` and `import unittest`. **Line 4**: `from app.main import answer` imports the function under test from the service's own package.
- **Line 7**: `class AnswerTest(unittest.TestCase):` a test class. **Lines 8 and 9**: `test_health_is_ok` checks `self.assertEqual(answer("/healthz"), (200, "ok\n"))`: the health path gives status 200 and the body `ok` plus a newline (`\n`).
- **Lines 11 to 15**: `test_root_names_the_service_and_its_owner` unpacks `status, body = answer("/")`, checks the status is 200, parses the body with `json.loads(body)` and checks `["service"]` equals `"__NAME__"` and `["owner"]` equals `"__OWNER__"`. In the template these are placeholders; the platform replaces them, so in a generated service the test checks that service's real name and owner.
- **Lines 17 and 18**: `test_unknown_path_is_404` checks `answer("/nope")[0]` is 404.
- **Lines 21 and 22**: `if __name__ == "__main__": unittest.main()` lets you also run the file directly.

The tests call the plain function `answer(path)`, not a server, so no network or port is needed ([http-server.md](http-server.md)).

### `template/Makefile`

```make
.PHONY: lint test ci image sign attest verify deploy release

lint:
	python3 -m compileall -q app tests

test:
	python3 -m unittest discover -s tests

ci: lint test
```

- **Line 17**: `.PHONY: lint test ci image sign attest verify deploy release`. **Lines 19 and 20**: `lint` runs `python3 -m compileall -q app tests`. **Lines 22 and 23**: `test` runs `python3 -m unittest discover -s tests`. **Line 25**: `ci: lint test` runs both. The workflow's `lint` and `test` jobs call `make lint` and `make test` ([github-actions.md](github-actions.md)).

### How the platform checks the template

<!-- fmt:off -->
```python
"""The template, generated for three imaginary teams, with real git and real make: the repositories it creates work."""

import subprocess
from pathlib import Path

import pytest

from goldenpath.application.generate_service import ServiceGenerator
from goldenpath.infrastructure.auditor import RepositoryAuditor
from goldenpath.infrastructure.catalog_files import FileCatalog
from goldenpath.infrastructure.repositories import GitRepositories, commits_since
from goldenpath.infrastructure.template_renderer import FileTemplateRenderer

ROOT = Path(__file__).resolve().parents[2]
TEAMS = [("orders", "team-orders"), ("billing", "team-billing"), ("search", "team-search")]


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
```
<!-- fmt:on -->

The platform's own test renders the template into a temporary folder with the real renderer, audits it and runs `make ci` there (real `make`, real `git`). `@pytest.mark.parametrize(("name", "owner"), TEAMS)` runs the same test for `orders`/`team-orders`, `billing`/`team-billing` and `search`/`team-search`. A change to the template that breaks a generated service therefore fails the **platform's** tests ([pytest.md](pytest.md)).

## Try it yourself

```bash
mkdir -p /tmp/gp-demo && rm -rf /tmp/gp-demo/svc
.venv/bin/python - <<'PY'
from pathlib import Path
from goldenpath.infrastructure.template_renderer import FileTemplateRenderer
FileTemplateRenderer(Path("template")).render(Path("/tmp/gp-demo/svc"), {"__NAME__": "demo", "__OWNER__": "team-platform", "__RUNBOOK__": "https://example.test/runbooks/demo", "__PLATFORM_REF__": "0000000"})
PY
cd /tmp/gp-demo/svc && make ci
```
Expect `Ran 3 tests ... OK`.

```bash
cd /tmp/gp-demo/svc && printf 'def broken(:\n' > app/bad.py && make lint; echo "exit: $?"; rm app/bad.py
```
`compileall` reports the syntax error and the exit status is non-zero.

```bash
cd /tmp/gp-demo/svc && python3 -m unittest -v tests.test_app 2>&1 | head -8
```
Verbose output lists each test.

## Mistakes people make

- Test discovery that finds nothing because files are not named `test*.py`.
- Importing the code under test from the wrong directory.
- Heavy test dependencies in a template meant to be small.
- Treating a successful compile as a successful test: it only proves the syntax.

## Check yourself

1. What is `compileall` good for here? *A syntax check with no extra tools.*
2. Why does the template avoid pytest? *The generated service must pass its checks with only the standard library.*
3. How does `unittest discover` find tests? *It imports `test*.py` files and runs `test_*` methods of `TestCase` classes.*
4. Who tests the template itself? *The platform's unit tests generate a service and run `make ci` on it.*
5. Why do the tests call `answer()` and not start a server? *No network is needed, so they are fast and reliable.*

## Further reading

- `unittest`: https://docs.python.org/3.12/library/unittest.html
- Test discovery: https://docs.python.org/3.12/library/unittest.html#test-discovery
- `compileall`: https://docs.python.org/3.12/library/compileall.html
