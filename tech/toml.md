# TOML and `pyproject.toml`

## What it is

TOML is a text format for configuration: `key = value` lines, `[table]` headings that group keys, and `[[array-of-tables]]` headings that start a new entry in a list. `pyproject.toml` is the single file Python tools read for project settings. Python 3.11 and newer can read TOML with the standard module `tomllib`.

## Why this repository uses it

One file holds the project's identity and the settings of every tool: ruff, mypy, pytest, coverage and import-linter. The command to find a setting is always "look in `pyproject.toml`".

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` | Everything below. |
| `.editorconfig` | Gives TOML files a 2-space indent. |

## How it works underneath

`[tool.ruff]` creates a table `ruff` inside a table `tool`; in Python that becomes `{"tool": {"ruff": {...}}}`. Every `[[tool.importlinter.contracts]]` adds one more dictionary to a list. TOML has real types: strings, integers, floats, booleans, dates, lists, tables. Comments start with `#`.

## Walkthrough of this repository's use

```toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"
```
Which tool builds the package.

```toml
[project]
name = "cicd-golden-path-and-dora"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["psycopg[binary]>=3.2,<4", "pyyaml>=6"]

[project.optional-dependencies]
dev = ["pytest>=8,<10", "pytest-cov>=5", "ruff>=0.6", "mypy>=1.11", "import-linter>=2.0", "pip-audit>=2.7", "types-PyYAML>=6"]

[project.scripts]
goldenpath = "goldenpath.interfaces.cli:main"
```
Two runtime dependencies. `psycopg[binary]` means "psycopg with its `binary` extra" (the precompiled driver). `>=3.2,<4` is a version range. `[project.scripts]` makes the installer create a `goldenpath` command that calls `main()` in `goldenpath/interfaces/cli.py`.

```toml
[tool.setuptools.packages.find]
where = ["src"]
```
Look for packages under `src/` (the `src` layout).

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
```
See [pytest.md](pytest.md). `[tool.ruff]`, `[tool.mypy]` and `[tool.importlinter]` have their own notes ([ruff.md](ruff.md), [mypy.md](mypy.md), [import-linter.md](import-linter.md)).

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
