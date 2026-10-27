# TOML and `pyproject.toml`

## What it is

A **configuration file** holds settings for a program, separate from the program's code. **TOML** ("Tom's Obvious, Minimal Language") is a text format for such files that is easy for people to read and write. Its building blocks:

- A line `key = value` sets a setting. Values can be **text** (in double quotes: `"py312"`), **whole numbers** (`120`), **true/false** (`true`, `false`), **lists** (square brackets: `["a", "b"]`) or **inline tables** (curly braces: `{ text = "MIT" }`).
- A line in square brackets, `[tool.ruff]`, starts a **table**: a named group of settings. Dots express nesting, so `[tool.ruff.lint]` is a table `lint` inside `ruff` inside `tool`. The settings that follow belong to that table until the next table heading.
- A line in double square brackets, `[[tool.mypy.overrides]]`, starts a new entry in a **list of tables**: you may write the same heading several times, and each time adds one more item to the list.
- A `#` starts a comment.

`pyproject.toml` is the one file in a Python project where tools look for their settings: the build tool, the formatter, the type checker, the test runner. Python 3.11 and newer can also read TOML itself with the standard library module `tomllib`.

## Why this repository uses it

One file holds the project's name and version, its dependencies, and the settings of every tool: ruff, mypy, pytest, coverage and import-linter. A learner who asks "how is this checked?" looks in one place.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` | All of it, 89 lines, covered below. |
| `.editorconfig` | Gives TOML files a two-space indent ([editorconfig.md](editorconfig.md)). |

## How it works underneath

`tomllib.loads(text)` turns the text into ordinary Python dictionaries. `[tool.ruff]` becomes `{"tool": {"ruff": {...}}}`; each `[[tool.importlinter.contracts]]` appends one dictionary to the list at `["tool"]["importlinter"]["contracts"]`. A tool reads only its own table (ruff reads `tool.ruff`, mypy reads `tool.mypy`), and it ignores the rest.

## Walkthrough of this repository's use

Every line of `pyproject.toml`, in order.

### `[build-system]`

```toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"
```

When someone builds the package, the build tool reads this table first. `requires` lists what must be installed to run the build: `setuptools` (version 75 or newer, the library that knows how to assemble a Python package) and `wheel` (the helper that writes the `.whl` file format). `build-backend` names the Python object that does the building.

### `[project]`

```toml
[project]
name = "cicd-golden-path-and-dora"
version = "0.1.0"
description = "A golden-path template that gives a new service a secure pipeline on day one, and the DORA metrics computed from the events that pipeline records."
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
authors = [{ name = "Sumit Srivastava" }]
dependencies = ["psycopg[binary]>=3.2,<4", "pyyaml>=6"]
```

- `name`, `version = "0.1.0"`, `description` (one sentence), `readme = "README.md"` (the file shown as the long description), `requires-python = ">=3.12"` (refuse to install on older Python), `license = { text = "MIT" }` (an inline table), `authors = [{ name = "Sumit Srivastava" }]` (a list holding one inline table).
- `dependencies = ["psycopg[binary]>=3.2,<4", "pyyaml>=6"]`: what the platform needs to run. `psycopg[binary]` is the PostgreSQL driver with its optional precompiled part ([psycopg.md](psycopg.md)); `>=3.2,<4` is a version range; `pyyaml>=6` reads YAML ([yaml.md](yaml.md)).

### `[project.optional-dependencies]`

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8,<10",
    "pytest-cov>=5",
    "ruff>=0.6",
    "mypy>=1.11",
    "import-linter>=2.0",
    "pip-audit>=2.7",
    "types-PyYAML>=6",
]
```

The group `dev` holds what is needed to check the project but not to run it: `pytest` and `pytest-cov` (tests and coverage), `ruff` (lint and format), `mypy` (types), `import-linter` (layer rules), `pip-audit` (vulnerability check) and `types-PyYAML` (type information for the YAML library). The lock files are generated from these ranges ([uv.md](uv.md)). Note what is **absent**: a generated service has no dependencies, so the template has no `pyproject.toml` at all.

### `[project.scripts]` and package discovery

```toml
[project.scripts]
goldenpath = "goldenpath.interfaces.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```

`goldenpath = "goldenpath.interfaces.cli:main"` means: when the package is installed, create a command named `goldenpath` that imports `goldenpath.interfaces.cli` and calls its function `main`. `[tool.setuptools.packages.find] where = ["src"]` tells setuptools to find packages under `src/`.

### `[tool.ruff]` and `[tool.ruff.lint]`

```toml
[tool.ruff]
line-length = 120
target-version = "py312"
src = ["src", "tests"]
extend-exclude = ["template"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "N", "C4", "RUF", "PT", "S", "D100", "D101", "D103", "D104"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D", "S"]
```

Explained key by key in [ruff.md](ruff.md). Note `extend-exclude = ["template"]`: the template's files hold placeholders and are audited by the golden-path rules instead.

### `[tool.mypy]` and its override

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

Explained in [mypy.md](mypy.md). The `[[tool.mypy.overrides]]` heading (double brackets) adds one item to a list: an entry that applies only to modules matching `tests.*`.

### `[tool.pytest.ini_options]`, `[tool.coverage.*]`

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

Explained in [pytest.md](pytest.md): where tests are, the import path, options added to every run, the two markers `integration` and `e2e`, the package measured for coverage (`goldenpath`) with branch coverage, and the report showing uncovered line numbers.

### `[tool.importlinter]` and its contracts

```toml
[tool.importlinter]
root_packages = ["goldenpath"]
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Layers: interfaces -> infrastructure -> application -> domain, never upward"
type = "layers"
layers = [
    "goldenpath.interfaces",
    "goldenpath.infrastructure",
    "goldenpath.application",
    "goldenpath.domain",
]

[[tool.importlinter.contracts]]
name = "Domain and application know nothing about PostgreSQL, YAML, HTTP or subprocesses"
type = "forbidden"
source_modules = ["goldenpath.domain", "goldenpath.application"]
forbidden_modules = ["psycopg", "yaml", "subprocess", "http", "urllib"]
```

Explained in [import-linter.md](import-linter.md): two contracts, the four layers and the ban on `psycopg`, `yaml`, `subprocess`, `http` and `urllib` in the inner layers.

## Try it yourself

```bash
.venv/bin/python -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb')); print(d['project']['name'], d['project']['dependencies'])"
```
Expect `cicd-golden-path-and-dora ['psycopg[binary]>=3.2,<4', 'pyyaml>=6']`. (`tomllib` needs the file opened in binary mode.)

```bash
.venv/bin/python -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb')); print(len(d['tool']['importlinter']['contracts']), d['tool']['pytest']['ini_options']['markers'][0][:11])"
```
Expect `2 integration`.

```bash
.venv/bin/goldenpath --help | head -3
```
The `goldenpath` command exists because of `[project.scripts]`.

## Mistakes people make

- Mixing up `[table]` and `[[array-of-tables]]`.
- Repeating a table heading (an error).
- Forgetting to quote strings.

## Check yourself

1. What does `[[tool.importlinter.contracts]]` do? *Adds one entry to a list of tables.*
2. What does `>=3.2,<4` mean? *Version 3.2 or newer, below 4.*
3. How is the `goldenpath` command created? *From `[project.scripts]` at install time.*
4. Why open the file in binary mode for `tomllib.load`? *The module wants bytes so it can decode UTF-8 itself.*
5. Where do tool settings live? *Under `[tool.<name>]`.*

## Further reading

- TOML 1.0: https://toml.io/en/v1.0.0
- `tomllib`: https://docs.python.org/3.12/library/tomllib.html
- Writing `pyproject.toml`: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
