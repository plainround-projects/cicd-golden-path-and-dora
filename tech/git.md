# Git

## What it is

Git stores a project's history as a chain of **commits**: snapshots of the files with a message, an author, a time and a pointer to the parent commit. A commit is named by its **SHA**, a 40-character fingerprint of its contents (the short form is the first 7 characters). A **branch** is a name that points at one commit. A **remote** is another copy of the repository. A **bare** repository has the history but no working files; it is what a server holds.

## Why this repository uses it

Two places. First, **creating a service**: the platform makes a new Git repository from the template and pushes it to a remote, which stands in for `gh repo create` on GitHub. Second, **the pipeline's own facts**: the version of an image is the short commit id, the provenance statement names the full commit, and the list of commits in a deployment comes from `git rev-list`. The platform never reads Git history to compute metrics ([dora-metrics.md](dora-metrics.md)); it reads events.

## Where it appears

| Path | Use |
|---|---|
| `src/goldenpath/infrastructure/repositories.py` | `GitRepositories.create`: `git init`, `add`, `commit`, `remote add`, `push`; `commits_since` with `git rev-list`. |
| `template/Makefile` | `git rev-parse --short HEAD` (version) and `git rev-parse HEAD` (provenance). |
| `template/.github/workflows/ci.yml` | `fetch-depth: 0` and `git rev-parse --short HEAD` in the release job. |
| `Makefile` | `git rev-list --max-parents=0 --abbrev-commit HEAD` finds a service's first commit. |
| `.gitignore`, `template/.gitignore` | What git must not track: `.venv/`, `.env`, `.local/`, `keys/`, `*.key`, `.build/`. |

## How it works underneath

- Git keeps content in `.git/` as hashed objects: file contents, folders, commits. A SHA changes if anything in it changes.
- A branch is a small file with one SHA. `HEAD` names the current branch.
- `git rev-parse X` turns a name into a SHA. `--short` shortens it.
- `git rev-list A..B` lists commits reachable from B but not from A. `--reverse` puts the oldest first. `--max-parents=0` selects commits with no parent: the first commit.
- `git init --bare` makes a repository with no working files. Pushing to it works like pushing to GitHub.
- `git -c user.name=... -c user.email=...` sets an identity for one command only, so no global configuration is needed.

## Walkthrough of this repository's use

### `GitRepositories.create`

```python
AUTHOR = ("platform-bot", "platform-bot@example.test")

def _git(directory: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", f"user.name={AUTHOR[0]}", "-c", f"user.email={AUTHOR[1]}", *args],
        cwd=directory, capture_output=True, text=True, check=True,
    )
    return done.stdout.strip()
```
Every Git call gets the bot identity through `-c`, so the commit is made by `platform-bot` on any machine. `check=True` raises if Git fails. The arguments are a list; no shell is involved.

```python
subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
_git(directory, "init", "-q", "-b", "main")
_git(directory, "add", "-A")
_git(directory, "commit", "-q", "-m", message)
_git(directory, "remote", "add", "origin", str(remote))
_git(directory, "push", "-q", "origin", "main")
return _git(directory, "rev-parse", "HEAD")
```
In order: a bare "server" repository under `.local/remotes/<name>.git`; a new repository in the generated folder; stage all files (`add -A`); one commit; name the remote `origin`; push `main`; return the commit id. `-b main` sets the branch name without depending on the user's Git settings; `-q` is quiet.

### `commits_since`

```python
spec = f"{base}..HEAD" if base else "HEAD"
return _git(directory, "rev-list", "--reverse", "--abbrev-commit", spec).split()
```
The commits that belong to the *next* deployment: everything after the last deployed commit, oldest first, as short ids. These become the `commit` events and the `commits` part of the `deploy` event's ref (`d1:a1+a2`).

### In the template

`VERSION ?= $(shell git rev-parse --short HEAD)` names the image tag. The attestation records `git rev-parse HEAD` (the full commit). In CI, `actions/checkout` with `fetch-depth: 0` fetches the whole history so these commands work ([github-actions.md](github-actions.md)).

### In the root `Makefile`

```make
@first=$$(git -C .local/services/orders rev-list --max-parents=0 --abbrev-commit HEAD); \
  $(VENV)/bin/goldenpath trace orders $$first
```
`git -C DIR` runs Git as if started in `DIR`. The first commit of the `orders` service is traced from its commit event to its deployment event.

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
