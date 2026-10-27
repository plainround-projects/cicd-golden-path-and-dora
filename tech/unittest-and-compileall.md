# `unittest` and `compileall` (the generated service's checks)

## What it is

`unittest` is the test framework that ships with Python. A test is a method whose name starts with `test` inside a class that extends `unittest.TestCase`; `self.assertEqual(a, b)` and similar methods check results. `python3 -m unittest discover -s tests` finds and runs every test file. `compileall` is a standard-library module that compiles every `.py` file to bytecode; it fails on a **syntax error**, so it works as the cheapest possible lint.

## Why this repository uses it

A generated service must pass `lint` and `test` with **no installed dependencies**: no pytest, no ruff, no virtual environment. The template promises a service that runs on a bare `python:3.12-slim` and on a plain CI runner. So its checks use only the standard library. The platform's own tests, in contrast, use pytest ([pytest.md](pytest.md)).

## Where it appears

| Path | Use |
|---|---|
| `template/tests/test_app.py` | Three `unittest` tests of the service's `answer()` function. |
| `template/Makefile` | `lint` runs `python3 -m compileall -q app tests`; `test` runs `python3 -m unittest discover -s tests`. |
| `tests/template/test_generated_service.py` | The **platform** generates a service and runs these same checks on it. |

## How it works underneath

`unittest discover` imports every `test*.py` file under the start directory, collects `TestCase` subclasses, and runs each `test_*` method on a fresh instance. A failed `assert*` raises `AssertionError`; the runner records it and goes on. The exit status is 0 when all pass. `compileall -q` walks the folders, compiles each file and prints errors only (`-q`).

## Walkthrough of this repository's use

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
```
`__NAME__` and `__OWNER__` are placeholders the template renderer replaces when the service is created. The tests call the plain function `answer(path)` and need no server or network ([http-server.md](http-server.md)). `from app.main import answer` works because `unittest discover` runs from the service's root, so `app` is importable.

```make
lint:
	python3 -m compileall -q app tests

test:
	python3 -m unittest discover -s tests

ci: lint test
```
`make ci` is exactly what the `lint` and `test` jobs in the workflow run ([make.md](make.md)).

### How the platform checks the template

`tests/template/test_generated_service.py` renders the template into a temporary folder, runs the audit, and executes `make ci` on the result. A change to the template that breaks the generated service therefore fails the **platform's** unit tests.

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
