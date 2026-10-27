# ruff

## What it is

ruff is a very fast tool, written in Rust, that does two jobs for Python: a **linter** (finds likely bugs and style problems) and a **formatter** (rewrites code to one layout). Pinned: 0.17.2. A **lint rule** has a code such as `E501` (line too long) or `S310` (a URL opener that might open a `file:` address). You turn rules on by their letter prefix.

## Why this repository uses it

The platform's `lint` step must be cheap and strict. The security (`S`) rules matter more here than in most projects: this code builds `subprocess` commands and opens URLs, which is where such mistakes happen.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` `[tool.ruff]`, `[tool.ruff.lint]` | Settings. |
| `Makefile` | `lint`: `ruff check .` and `ruff format --check .`; `format`: `ruff check --fix .` and `ruff format .`. |
| `src/` | A few lines end with `# noqa: CODE - reason`. |

## How it works underneath

ruff parses each `.py` file into a syntax tree and applies rules to the tree; it never runs your code. The formatter prints the tree back in a fixed style. `--check` only reports (exit 1) and changes nothing.

## Walkthrough of this repository's use

```toml
[tool.ruff]
line-length = 120
target-version = "py312"
src = ["src", "tests"]
extend-exclude = ["template"]
```
`extend-exclude = ["template"]` matters: the files under `template/` hold placeholders like `__NAME__` and are not valid for this project's rules. They are checked by the golden-path audit instead.

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "N", "C4", "RUF", "PT", "S", "D100", "D101", "D103", "D104"]
```
`E` pycodestyle errors, `F` unused names, `I` import order, `B` likely bugs, `UP` modern syntax, `SIM` simplifications, `N` naming, `C4` comprehensions, `RUF` ruff's own rules, `PT` pytest style, `S` security (bandit), and `D100/D101/D103/D104` missing docstrings on modules, classes, functions and packages.

```toml
[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D", "S"]
```
Tests need no docstrings, and `assert` is flagged by `S101`.

### Reasoned exceptions in this code

```python
request = urllib.request.Request(  # noqa: S310 - scheme checked in __init__
```
`S310` warns that a URL could be `file:///etc/passwd`. `CollectorEventSink.__init__` already refuses anything that does not start with `http://` or `https://`, and the comment says so.

```python
done = subprocess.run(  # noqa: S603
    ["git", "-c", ..., *args],  # noqa: S607
```
`S603` warns about running a subprocess from variable input; `S607` warns about a partial program path (`git`). Here the arguments are a list built by this program and never pass through a shell.

```python
rng = random.Random(seed)  # noqa: S311 - a simulation, not a secret
```
`S311` says `random` is not cryptographically safe. Here that is the point: a repeatable simulation.

## Try it yourself

```bash
.venv/bin/ruff --version
.venv/bin/ruff check .
```
Expect `ruff 0.17.2` and `All checks passed!`.

```bash
.venv/bin/ruff rule S310
```
Prints the rule's explanation.

```bash
.venv/bin/ruff check template --no-force-exclude 2>&1 | tail -3
```
Looks at the template files with the project's rules switched on. They are excluded by default; this command prints findings (nine when this note was written), which is why they are kept out of the project's own lint.

```bash
.venv/bin/ruff format --diff src/goldenpath/domain/events.py
```
Shows what the formatter would change (nothing).

## Mistakes people make

- A bare `# noqa`. Always give the code and a reason.
- Fighting the formatter by hand. Run `make format`.
- Linting placeholder files with project rules.

## Check yourself

1. What is the difference between `ruff check` and `ruff format`? *`check` finds problems; `format` rewrites layout.*
2. Why exclude `template/`? *Its files contain placeholders and are audited by the golden-path rules instead.*
3. What does `S603` warn about? *Running a subprocess from variable input.*
4. Why ignore `S` in tests? *Tests use `assert`.*
5. What goes after `# noqa: S311`? *A reason.*

## Further reading

- ruff documentation: https://docs.astral.sh/ruff/ (0.17.2)
- Rules: https://docs.astral.sh/ruff/rules/
- Configuration: https://docs.astral.sh/ruff/configuration/
