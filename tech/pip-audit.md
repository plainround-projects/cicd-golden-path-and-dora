# pip-audit

## What it is

Software libraries have bugs, and some bugs are security holes. When a hole is found in a published version of a library, it is reported with an identifier (an **advisory**, for example `PYSEC-2024-1234` or a CVE number) and a note of which versions are affected and which version fixes it. These reports are collected in databases.

**pip-audit** compares the packages you depend on with such a database. Give it a list of exact versions (a lock file) and it says which of them have a known advisory. This repository pins pip-audit 2.10.1. It asks the Python Packaging Advisory Database (through PyPI), so it needs network access.

## Why this repository uses it

A golden path is about secure delivery, so the platform's own dependencies are held to the same standard: a job `audit` runs on every push and pull request. The generated services have no dependencies, so there is nothing to audit inside them.

## Where it appears

| Path | Use |
|---|---|
| `Makefile` target `audit-deps` (lines 121 and 122) | `pip-audit --no-deps --disable-pip -r requirements-dev.lock` |
| `.github/workflows/ci.yml` job `audit` (lines 62 to 70) | Runs `make audit-deps`. |

(`make audit` is a different target: it audits generated *repositories* against the golden-path contract, not dependencies.)

## How it works underneath

pip-audit reads a requirements file, takes each `name==version`, asks the advisory service whether that exact version is affected, and prints a table of findings: package, installed version, advisory id and the version that fixes it. Exit status 0 means nothing found; 1 means at least one finding. By default it also builds a temporary environment to resolve dependencies; the flags below turn that off because the lock already contains every dependency.

## Walkthrough of this repository's use

```make
audit-deps: $(STAMP) ## check the locked dependencies for known vulnerabilities
	$(VENV)/bin/pip-audit --no-deps --disable-pip -r requirements-dev.lock
```

- **Line 121**: the target needs the environment (`$(STAMP)`) so the tool is installed; the `##` text is its description for `make help`.
- **Line 122**: `$(VENV)/bin/pip-audit --no-deps --disable-pip -r requirements-dev.lock`. `-r requirements-dev.lock` audits the 49 packages in the lock, exactly what the project installs. `--no-deps` means "do not work out dependencies yourself"; the lock already lists every one. `--disable-pip` means "do not call pip to build a temporary environment".

```yaml
  audit:
    name: Known-vulnerability check of the locked dependencies
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
        with:
          python-version: "3.12"
      - run: make audit-deps
```

The job has a long `name` (the description GitHub shows), checks out the repository, installs Python and runs `make audit-deps`. It runs in parallel with the other two jobs and has no `needs`. Nothing in the template's branch protection requires it. It needs network access, so it was not re-run when these notes were written.

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
