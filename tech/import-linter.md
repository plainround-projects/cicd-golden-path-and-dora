# import-linter

## What it is

import-linter checks the **import graph** of a Python project against rules ("contracts") you write. The import graph says which module imports which. `lint-imports` reads the contracts from `pyproject.toml` and fails when an import breaks one. Pinned: 2.15 (it uses `grimp` to build the graph).

## Why this repository uses it

The platform is built in four layers: `interfaces → infrastructure → application → domain`. The domain holds the delivery rules and the DORA maths, and must not know about databases, files, HTTP or subprocesses. That is easy to break with one stray import, so the architecture is a check, not just a diagram.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` `[tool.importlinter]` | Two contracts. |
| `Makefile`, target `lint` | `$(VENV)/bin/lint-imports`. |
| `ARCHITECTURE.md` | The same layers in words. |

## How it works underneath

`grimp` reads every module's `import` statements and builds a directed graph. A **layers** contract lists modules top to bottom: a higher layer may import a lower one, never the reverse. A **forbidden** contract says some source modules must never reach some forbidden modules, even indirectly through other modules.

## Walkthrough of this repository's use

```toml
[tool.importlinter]
root_packages = ["goldenpath"]
include_external_packages = true
```
One package is analysed. `include_external_packages` lets a contract name third-party and standard-library modules.

```toml
[[tool.importlinter.contracts]]
name = "Layers: interfaces -> infrastructure -> application -> domain, never upward"
type = "layers"
layers = ["goldenpath.interfaces", "goldenpath.infrastructure", "goldenpath.application", "goldenpath.domain"]
```
`domain` imports nothing from the other three; `application` imports only `domain`.

```toml
name = "Domain and application know nothing about PostgreSQL, YAML, HTTP or subprocesses"
type = "forbidden"
source_modules = ["goldenpath.domain", "goldenpath.application"]
forbidden_modules = ["psycopg", "yaml", "subprocess", "http", "urllib"]
```
The two inner layers use only the standard library's pure parts. `domain/metrics.py` computes from `Event` objects; `application/ports.py` only declares `Protocol` classes. The code that talks to PostgreSQL, YAML, HTTP and `git` lives in `infrastructure/` and `interfaces/`.

This is why the tests of the metrics (`tests/unit/domain`) need no database, no network and no Docker, and run in a fraction of a second.

## Try it yourself

```bash
.venv/bin/lint-imports
```
Expect each contract followed by `KEPT` and `Contracts: 2 kept, 0 broken.`

Break one on purpose:
```bash
printf 'import yaml\n' >> src/goldenpath/domain/errors.py
.venv/bin/lint-imports | tail -10
git checkout src/goldenpath/domain/errors.py
```
Expect `BROKEN` for the forbidden-modules contract.

## Mistakes people make

- Architecture that exists only in a document.
- Layers listed in the wrong order.
- Forgetting `include_external_packages`, so `psycopg` cannot be forbidden.
- Forgetting indirect imports; this tool checks them.

## Check yourself

1. What does a `layers` contract guarantee? *No lower layer imports a higher one.*
2. What does a `forbidden` contract guarantee? *The source modules never reach the forbidden ones, even indirectly.*
3. Why is `yaml` forbidden in the domain? *The domain must stay pure; file formats belong to adapters.*
4. Does import-linter run the code? *No.*
5. Which make target runs it? *`lint`.*

## Further reading

- import-linter: https://import-linter.readthedocs.io/en/stable/ (2.15)
- Contract types: https://import-linter.readthedocs.io/en/stable/contract_types.html
