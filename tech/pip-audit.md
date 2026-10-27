# pip-audit

## What it is

pip-audit checks the packages you depend on against databases of **known vulnerabilities** (published security problems). It compares each pinned name and version with the Python Packaging Advisory Database and reports any that have an advisory. Pinned: 2.10.1 (see `requirements-dev.lock`).

## Why this repository uses it

A hash-locked environment ([pip-and-hash-locking.md](pip-and-hash-locking.md)) is repeatable, but a repeatable environment can repeatedly contain a vulnerable package. The platform ships an `audit` job so a new advisory against `psycopg`, `pyyaml` or a development tool is noticed. The golden path the platform hands out is about secure pipelines, so its own dependencies are held to the same standard.

## Where it appears

| Path | Use |
|---|---|
| `Makefile`, target `audit-deps` | `pip-audit --no-deps --disable-pip -r requirements-dev.lock` |
| `.github/workflows/ci.yml`, job `audit` | Runs `make audit-deps` on every push and pull request. |

(`make audit` is a different target: it audits generated **repositories** against the golden-path contract, not dependencies.)

## How it works underneath

pip-audit reads a requirements file, asks PyPI's advisory service about each `name==version`, and prints a table of findings. It needs network access. Exit status 0 means nothing found; 1 means vulnerabilities were found.

## Walkthrough of this repository's use

```make
audit-deps: $(STAMP)
	$(VENV)/bin/pip-audit --no-deps --disable-pip -r requirements-dev.lock
```
- `-r requirements-dev.lock` audits exactly what the project installs, 49 pinned packages.
- `--no-deps` says "do not resolve dependencies": the lock already lists every one.
- `--disable-pip` stops pip-audit from creating a temporary virtual environment through pip; with a fully pinned file it simply reads names and versions.

```yaml
  audit:
    name: Known-vulnerability check of the locked dependencies
    steps:
      - ...
      - run: make audit-deps
```
It is a separate job, so a finding shows as its own red check and does not hide the lint and test results.

## Try it yourself

```bash
.venv/bin/pip-audit --version
```
Expect `pip-audit 2.10.1`.

```bash
make audit-deps
```
Needs network access. Expect `No known vulnerabilities found`. If an advisory exists for a pinned version, a table lists the package, the version, the advisory id and the fixed version. This command was not re-run when this note was written.

```bash
grep -c "^[a-z].*==" requirements-dev.lock requirements.lock
```
Expect `49` and `5`: development and runtime pins.

## Mistakes people make

- Auditing a loose `requirements.txt` instead of the lock.
- Ignoring a finding without a reason and a date to revisit.
- Running it rarely. A new advisory appears without any code change.

## Check yourself

1. What does pip-audit compare? *Pinned versions against known advisories.*
2. Why `--no-deps`? *The lock already contains every dependency.*
3. Is `make audit` the same as `make audit-deps`? *No: `audit` checks generated repositories against the contract.*
4. Does it need the network? *Yes.*
5. Why a separate CI job? *Its failure is visible on its own.*

## Further reading

- pip-audit: https://pypi.org/project/pip-audit/ and https://github.com/pypa/pip-audit
- Python Packaging Advisory Database: https://github.com/pypa/advisory-database
