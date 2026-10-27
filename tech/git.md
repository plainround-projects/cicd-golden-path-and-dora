# Git

## What it is

Imagine a project folder in which you keep changing files. **Git** is a program that remembers every version of that folder, so you can see what changed, when, by whom and why, and go back if something broke. This memory is called a **repository** (or "repo"). It lives in a hidden folder named `.git` inside the project folder.

The words you need:

- A **commit** is one saved version: a snapshot of all the files, plus a message ("fix the cache"), an author, a time, and a pointer to the commit that came before it. A repository is a chain of commits.
- A **SHA** (also called a *hash* or *commit id*) is the commit's name: a 40-character code such as `3fa91bc2...`, computed from the commit's contents. Change anything in a commit and its SHA changes, so the SHA is a fingerprint. People usually write only the first 7 characters.
- A **branch** is a movable name for a commit, such as `main`. When you commit on a branch, the name moves forward to the new commit.
- `HEAD` is Git's name for "the commit I am looking at right now".
- A **remote** is another copy of the repository, usually on a server; `origin` is the usual name for the one you cloned from. `git clone` copies a repository; `git push` sends your commits to a remote; `git fetch`/`git pull` bring commits from it.
- A **bare repository** has the history but no working files. It is what a server keeps, because nobody edits files on a server.
- A **working tree** is the actual folder of files you edit. **Staging** (`git add`) chooses which changes go into the next commit.
- A **diff** is the list of differences between two versions.
- A **hook** is a program that Git runs automatically at a given moment, such as before it accepts a push.

## Why this repository uses it

Git appears in two places. First, **creating a service**: the platform makes a new Git repository from the template, commits it as a bot, and pushes it to a remote, which stands in for `gh repo create` on GitHub. Second, **the pipeline's own facts**: the version of an image is the short commit id, the provenance statement names the full commit, and the list of commits in a deployment comes from `git rev-list`. The platform never reads Git history to compute metrics ([dora-metrics.md](dora-metrics.md)); it reads events, which cannot be rewritten the way history can.

## Where it appears

| Path | Use |
|---|---|
| `src/goldenpath/infrastructure/repositories.py` | `GitRepositories.create` and `commits_since`. |
| `template/Makefile` | `git rev-parse --short HEAD` (the version) and `git rev-parse HEAD` (provenance). |
| `template/.github/workflows/ci.yml` | `fetch-depth: 0` and `git rev-parse --short HEAD` in the release job. |
| `Makefile` | `git -C .local/services/orders rev-list --max-parents=0 --abbrev-commit HEAD`. |
| `src/goldenpath/interfaces/cli.py` | `_platform_ref` runs `git rev-parse HEAD`. |
| `.gitignore`, `template/.gitignore` | What Git must never track. |

## How it works underneath

- Git stores its data in `.git/` as **objects**: the contents of files, folders, and commits, each stored under the hash of its content. That is why a SHA changes when anything inside changes.
- A branch is a tiny file that holds one SHA. `HEAD` says which branch you are on.
- `git diff A B` compares two commits. `git diff A...B` (three dots) compares B with the point where it split from A, which is the right question for "what did this branch change".
- A **ref** is any name that points at a commit. Branches live under `refs/heads/`. A repository may also hold refs with invented names. This project uses `refs/status/green/<sha>` to mean "CI says this commit is green". Git does not care what the names mean.
- A **push option** (`git push --push-option text`) is extra text a client sends along with a push. The server may read it. A server only accepts push options if it is configured with `receive.advertisePushOptions true`.
- A **hook** is an executable file in the repository's `hooks/` folder. Hooks are not copied by `git clone`, so they must be installed on the server by hand. A non-zero exit from `pre-receive` rejects the push.

## Walkthrough of this repository's use

### `src/goldenpath/infrastructure/repositories.py`

```python
"""Create a new service's Git repository and publish it to a local bare remote (standing in for `gh repo create`)."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

AUTHOR = ("platform-bot", "platform-bot@example.test")


def _git(directory: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603
        ["git", "-c", f"user.name={AUTHOR[0]}", "-c", f"user.email={AUTHOR[1]}", *args],  # noqa: S607
        cwd=directory,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()
```

- **Line 9**: `AUTHOR = ("platform-bot", "platform-bot@example.test")`: a fixed name and e-mail for the commits the platform makes. The `.test` domain is reserved and can never be a real address.
- **Lines 12 to 20**, `_git(directory, *args)`: runs `git -c user.name=platform-bot -c user.email=platform-bot@example.test ARGS...` inside `directory`. `-c name=value` sets a Git setting for this one command, so a commit works on a machine with no Git identity configured. `*args` collects any number of extra words into a tuple and `*args` in the call spreads them back out. `subprocess.run([...], cwd=directory, capture_output=True, text=True, check=True)` starts Git as a separate program with the words as a *list* (never a shell string), captures its output as text, and raises an error if Git exits non-zero. `done.stdout.strip()` returns the printed text without the trailing newline. The `# noqa: S603` and `# noqa: S607` comments silence two security-lint warnings about starting programs ([ruff.md](ruff.md)).

```python
class GitRepositories:
    """`create` runs `git init`, commits everything, creates `<remotes>/<name>.git` and pushes `main` to it."""

    def __init__(self, remotes: Path) -> None:
        """`remotes` is the folder that holds the bare repositories."""
        self._remotes = remotes

    def create(self, directory: Path, name: str, message: str) -> str:
        """Publish the repository; return the commit id."""
        remote = self._remotes / f"{name}.git"
        remote.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)  # noqa: S603, S607
        _git(directory, "init", "-q", "-b", "main")
        _git(directory, "add", "-A")
        _git(directory, "commit", "-q", "-m", message)
        _git(directory, "remote", "add", "origin", str(remote))
        _git(directory, "push", "-q", "origin", "main")
        return _git(directory, "rev-parse", "HEAD")


def commits_since(directory: Path, base: str | None) -> Sequence[str]:
    """Short ids of the commits after `base` (all of them when `base` is None), oldest first."""
    spec = f"{base}..HEAD" if base else "HEAD"
    return _git(directory, "rev-list", "--reverse", "--abbrev-commit", spec).split()
```

- **Lines 30 to 40**, `create(directory, name, message)`: `remote = self._remotes / f"{name}.git"` is the path of the "server" copy; `remote.parent.mkdir(parents=True, exist_ok=True)` creates its folder. Then, in order:
  1. `git init -q --bare -b main REMOTE`: a **bare** repository (history only, no working files, what a server keeps) with `main` as its first branch name (`-b main` means the result does not depend on the user's global Git settings; `-q` is quiet).
  2. `git init -q -b main` in the service's folder: a new repository there.
  3. `git add -A`: stage every file for the next commit.
  4. `git commit -q -m MESSAGE`: record the commit.
  5. `git remote add origin REMOTE`: name the server copy `origin`.
  6. `git push -q origin main`: send the branch there.
  7. `git rev-parse HEAD`: return the new commit's id.
- **Lines 43 to 46**, `commits_since(directory, base)`: `spec = f"{base}..HEAD" if base else "HEAD"`; `git rev-list --reverse --abbrev-commit SPEC` lists the commits reachable from `HEAD` but not from `base` (the two dots mean "since"), oldest first (`--reverse`), as short ids (`--abbrev-commit`); `.split()` makes a list. These are the commits that belong to the *next* deployment.

### Version and provenance in the template

```make
# make ci | release      Every job of .github/workflows/ci.yml is one of these targets, so a laptop runs the same steps.
NAME := __NAME__
REGISTRY ?= localhost:55061
VERSION ?= $(shell git rev-parse --short HEAD)
IMAGE := $(REGISTRY)/$(NAME)
DIGEST_FILE := .build/digest
```

`VERSION ?= $(shell git rev-parse --short HEAD)` makes the image tag the short commit id. In the `attest` target, `$$(git rev-parse HEAD)` writes the **full** commit id into the provenance statement ([make.md](make.md)).

### In the workflow

```yaml
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          fetch-depth: 0
      - uses: sigstore/cosign-installer@d58896d6a1865668819e1d91763c7751a165e159 # v3.9.2
      - uses: docker/login-action@74a5d142397b4f367a81961eba4e8cd7edddf772 # v3.4.0
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - run: scripts/emit-event.sh commit "$(git rev-parse --short HEAD)"
      - run: make image
      - run: make sign
      - run: make attest
      - run: make verify
      - run: make deploy COMMITS="$(git rev-parse --short HEAD)" DEPLOYMENT="${{ github.run_id }}"
```

The `release` job checks out with `fetch-depth: 0` (the whole history, so `git rev-parse` and `rev-list` see everything) and runs `scripts/emit-event.sh commit "$(git rev-parse --short HEAD)"` and `make deploy COMMITS="$(git rev-parse --short HEAD)" ...` ([github-actions.md](github-actions.md)).

### In the root `Makefile`

```make
# What the pipelines recorded for the three real services, before the simulation replaces the store (step 4 and 5).
evidence: $(STAMP) ## every production deployment of each demo service with its commits, and one lead time traced
	@for service in orders billing search; do echo "$$service:"; $(VENV)/bin/goldenpath deployments $$service; done
	@first=$$(git -C .local/services/orders rev-list --max-parents=0 --abbrev-commit HEAD); \
	  $(VENV)/bin/goldenpath trace orders $$first
	$(VENV)/bin/goldenpath metrics
```

`git -C .local/services/orders rev-list --max-parents=0 --abbrev-commit HEAD` finds the generated service's first commit (`-C DIR` runs Git as if started in `DIR`; `--max-parents=0` selects commits with no parent, i.e. the first). `goldenpath trace orders <that commit>` then follows its lead time.

### `_platform_ref` and the marker file

```python
def _platform_ref() -> str:
    done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S607
    return done.stdout.strip() or "0" * 40
```

The platform's own commit id (`git rev-parse HEAD`, or forty zeros if Git says nothing) is written into each generated repository's `.golden-path.yaml` as `platform_ref`, so every service records which version of the golden path made it ([yaml.md](yaml.md)).

### `.gitignore` files

```
.venv/
__pycache__/
*.pyc
*.egg-info/
build/
dist/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.import_linter_cache/
.coverage
coverage.xml
.env
.DS_Store
logs/
reports/
.cache/
.omc/
.local/
keys/
*.key
```

Patterns, one per line, for files Git must never track: `.venv/`, `__pycache__/` and `*.pyc` (Python's environment and compiled files), `*.egg-info/`, `build/`, `dist/` (packaging output), the tool caches, `.coverage` and `coverage.xml`, `.env` (local settings), `.DS_Store`, `logs/`, `reports/`, `.cache/`, `.omc/`, **`.local/`** (all state the platform generates: the generated services, remotes, keys and logs), and **`keys/`** and **`*.key`** (a private signing key must never be committed). The template's own `.gitignore` (`__pycache__/`, `*.pyc`, `.build/`, `*.key`, `.env`, `.DS_Store`) protects every generated service the same way.

## Try it yourself

```bash
git log --oneline | head -5
git rev-parse --short HEAD
git rev-list --max-parents=0 --abbrev-commit HEAD
```
The last one prints the repository's first commit.

```bash
make up
.venv/bin/goldenpath new-service try-it team-platform
git -C .local/services/try-it log --format='%h %an %s'
```
Expect one commit by `platform-bot`: `Create try-it from golden path <ref>`. (The command without `--release` stops after publishing the repository.) Clean up with `make down`.

```bash
git -C .local/remotes/try-it.git log --oneline
```
The "server" copy has the same commit.

## Mistakes people make

- Relying on the global Git identity; on a fresh CI machine there is none. The bot identity is passed explicitly.
- Shallow clones (`fetch-depth: 1`) that lack the history `rev-list` needs.
- Using branch names without `-b`, which depend on the local default.
- Committing keys or `.env`. The `.gitignore` files list them.

## Check yourself

1. What is a bare repository? *A repository with history and no working files, used as a server.*
2. What does `git rev-list A..B` list? *Commits reachable from B but not from A.*
3. Why `-c user.name=...`? *To set an identity for one command without touching global settings.*
4. Why does the pipeline read events, not Git, to measure lead time? *Events carry the pipeline's own clock and cannot be edited after the fact.*
5. What does `--max-parents=0` find? *Commits with no parent: the first commit.*

## Further reading

- Git documentation: https://git-scm.com/docs
- `git-rev-list`: https://git-scm.com/docs/git-rev-list
- `git-init` (`--bare`): https://git-scm.com/docs/git-init
