# uv

## What it is

`uv` is a fast tool for managing Python packages, written in Rust by Astral (the makers of ruff, [ruff.md](ruff.md)). It can create virtual environments, install packages and, the job it has here, **resolve** requirements into a lock file. Version used by the author: 0.11.2.

**Resolution** means: you give a list of wishes with ranges ("psycopg 3.2 or newer but below 4"). Each package in turn depends on other packages with their own ranges. The resolver asks the package index which versions exist and what each requires, and finds one exact version of every package such that every requirement holds. That answer, written down with the files' checksums, is the lock ([pip-and-hash-locking.md](pip-and-hash-locking.md)).

## Why this repository uses it

To produce `requirements.lock` and `requirements-dev.lock` with hashes. Nothing else needs `uv`: `make install`, `make test` and CI use plain `pip` with the finished lock. A learner can run every command in the README without it; it is needed only to refresh the locks.

## Where it appears

| Path | Use |
|---|---|
| `requirements.lock`, `requirements-dev.lock` | Their first two comment lines record the exact command. |

## How it works underneath

`uv pip compile` is the "pip-compatible" interface: input a project file or a requirements file, output a requirements file. It downloads package metadata (not the packages themselves unless needed) from the index, solves the version puzzle, and writes `name==version` lines. With `--generate-hashes` it also records the SHA-256 of each downloadable file. `--universal` makes a single result that works on all operating systems and Python implementations by attaching *markers* (conditions after a semicolon) to lines that differ.

## Walkthrough of this repository's use

```bash
uv pip compile pyproject.toml --extra dev --generate-hashes --universal --python-version 3.12 -o requirements-dev.lock
```

- `uv pip compile`: resolve and write a requirements file. `pyproject.toml`: the input; its `dependencies` (`psycopg[binary]`, `pyyaml`) and its `dev` group are read ([toml.md](toml.md)).
- `--extra dev`: include the `dev` group (pytest, ruff, mypy, import-linter, pip-audit and their own dependencies: 49 packages in all).
- `--generate-hashes`: add `--hash=sha256:...` lines. `--universal`: one result valid on every platform, with markers where packages differ. `--python-version 3.12`: resolve for the oldest supported Python. `-o FILE`: where to write.

The runtime lock is the same command without `--extra dev`, writing `requirements.lock` (5 packages: `psycopg`, `psycopg-binary`, `pyyaml`, `typing-extensions` (for Python older than 3.13) and `tzdata` (time-zone data, only on Windows)). After refreshing: `make install` (the stamp file notices the new lock), `make check`, `make audit-deps` ([pip-audit.md](pip-audit.md)).

## Try it yourself

```bash
uv --version
```

```bash
uv pip compile pyproject.toml --generate-hashes --universal --python-version 3.12 | head -12
```
Prints a lock to the screen instead of a file. Needs network access to the package index.

```bash
head -3 requirements.lock
```
The recorded command.

## Mistakes people make

- Editing the lock by hand.
- Regenerating the lock with a different Python version, producing different pins.
- Forgetting `--generate-hashes`, then `--require-hashes` fails.
- Expecting `make` to need `uv`. It does not.

## Check yourself

1. What does a resolver do? *Finds exact versions that satisfy every requirement.*
2. What does `--universal` give? *One lock that works on all platforms.*
3. Where is the command recorded? *In the header comment of each lock file.*
4. Is `uv` needed to run the tests? *No.*
5. What does `-o` do? *Names the output file.*

## Further reading

- uv documentation: https://docs.astral.sh/uv/ (0.11.2)
- `uv pip compile`: https://docs.astral.sh/uv/pip/compile/
