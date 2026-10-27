# import-linter

## What it is

Large programs get messy when any part may use any other part. A common discipline is **layering**: the code is arranged in layers, and a layer may use only the layers below it. The innermost layer holds the rules of the problem and knows nothing about databases, files, networks or screens.

**import-linter** checks such rules automatically. It reads the `import` lines of every module ([python.md](python.md)) to build a map of "which module uses which", called the **import graph**, and compares it with rules ("contracts") that you write in `pyproject.toml`. The command is `lint-imports`. This repository pins import-linter 2.15, which uses a library called `grimp` to build the graph. Two kinds of contract are used:

- A **layers** contract lists modules from top to bottom. A module may import from layers below it, never from layers above.
- A **forbidden** contract says that certain *source* modules must never import certain *forbidden* modules, even indirectly through other modules.

## Why this repository uses it

The platform has four layers, `interfaces → infrastructure → application → domain`. The domain holds the delivery maths and the golden-path rules, and must know nothing about databases, YAML, HTTP or programs. That is what lets the metrics and the contract be tested in a fraction of a second with no Docker and no network. One stray `import psycopg` in the domain would break that quietly; the contracts turn the architecture into a check that runs in `make lint`.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` lines 71 to 89 | The settings and two contracts. |
| `Makefile` `lint` | Runs `lint-imports`. |
| `ARCHITECTURE.md` | The same layers in words. |

## How it works underneath

`grimp` reads every module's `import` statements and builds a directed graph (arrows from the importer to the imported). A *layers* contract checks no arrow goes from a lower layer up to a higher one. A *forbidden* contract searches the graph for any path, direct or through other modules, from a source module to a forbidden one. `include_external_packages = true` lets the contracts name modules that are not part of the project, such as the standard library's `subprocess` or the third-party `psycopg`. The tool never runs your code.

## Walkthrough of this repository's use

```toml
[tool.importlinter]
root_packages = ["goldenpath"]
include_external_packages = true
```

- `[tool.importlinter]` is the tool's own table. `root_packages = ["goldenpath"]` names the one package to analyse. `include_external_packages = true` lets contracts name modules that are not part of the project (`psycopg`, `yaml`, `subprocess`, `http`, `urllib`).

```toml
[[tool.importlinter.contracts]]
name = "Layers: interfaces -> infrastructure -> application -> domain, never upward"
type = "layers"
layers = [
    "goldenpath.interfaces",
    "goldenpath.infrastructure",
    "goldenpath.application",
    "goldenpath.domain",
]
```

- **Contract 1**, "Layers: interfaces -> infrastructure -> application -> domain, never upward". `[[tool.importlinter.contracts]]` (double brackets) adds one contract to a list. `name` is shown in the report; `type = "layers"`; `layers` lists the layers from top to bottom. `interfaces` may import from the three below it; `infrastructure` may import from `application` and `domain`; `application` only from `domain`; `domain` from none of them.

```toml
[[tool.importlinter.contracts]]
name = "Domain and application know nothing about PostgreSQL, YAML, HTTP or subprocesses"
type = "forbidden"
source_modules = ["goldenpath.domain", "goldenpath.application"]
forbidden_modules = ["psycopg", "yaml", "subprocess", "http", "urllib"]
```

- **Contract 2**, "Domain and application know nothing about PostgreSQL, YAML, HTTP or subprocesses". `type = "forbidden"`: `source_modules` are `goldenpath.domain` and `goldenpath.application`; `forbidden_modules` are `psycopg`, `yaml`, `subprocess`, `http` and `urllib`. None of them may be imported by the two inner layers, directly or through another module. That is why `application/ports.py` only declares `Protocol`s, `domain/metrics.py` works on `Event` objects, and everything that touches a database, a file format, a web request or a program lives in `infrastructure/` and `interfaces/`.

`make lint` runs `lint-imports`; with two contracts it ends with `Contracts: 2 kept, 0 broken.`

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
