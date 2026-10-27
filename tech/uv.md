# uv

## What it is

`uv` is a fast Python packaging tool written in Rust by Astral (the makers of [ruff](ruff.md)). It can create virtual environments, install packages and, the part used here, **resolve** a list of loose requirements into one exact, hashed lock file. Version used by the author: 0.11.2.

## Why this repository uses it

To make `requirements.lock` and `requirements-dev.lock`. `uv pip compile` works out which exact version of every package, including packages your packages need, satisfies the ranges in `pyproject.toml`, and writes each file's SHA-256 hash ([pip-and-hash-locking.md](pip-and-hash-locking.md)). Nothing in `make install`, `make test` or CI needs `uv`; they use plain `pip` with the finished lock. The platform has two runtime dependencies: `psycopg[binary]` and `pyyaml` (see `pyproject.toml`).

## Where it appears

| Path | Use |
|---|---|
| `requirements.lock`, `requirements-dev.lock` | Their header comments record the exact `uv pip compile` command. |

## How it works underneath

A **resolver** reads the ranges (`psycopg[binary]>=3.2,<4`), asks the package index which versions exist and what each one requires, and finds a set of versions where every requirement holds. `uv` does this much faster than pip. With `--universal` it produces one answer that is valid on all operating systems, using markers (`; sys_platform == 'win32'`) where packages differ.

## Walkthrough of this repository's use

```bash
uv pip compile pyproject.toml --extra dev --generate-hashes --universal --python-version 3.12 -o requirements-dev.lock
```
- `pip compile` is the "pip-compatible" interface: input in, requirements file out.
- `pyproject.toml` is the input; `--extra dev` adds the `dev` group.
- `--generate-hashes` records every distribution file's SHA-256.
- `--universal` makes a cross-platform result.
- `--python-version 3.12` resolves as if running 3.12, the oldest supported.
- `-o` names the output.

The runtime lock is the same command without `--extra dev`, writing `requirements.lock`.

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
