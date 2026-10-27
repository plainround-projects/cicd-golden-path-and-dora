# ruff

## What it is

Code can be correct and still be hard to read, inconsistent, or full of small mistakes: an unused variable, a name that is used before it exists, a risky call. A **linter** is a program that reads your source files *without running them* and points these out. A **formatter** is a program that rewrites your files into one fixed layout (spaces, line breaks, quote style) so people never argue about it.

**ruff** is both, for Python. It is written in Rust, which makes it very fast. This repository pins ruff 0.17.2. A **lint rule** has a code like `E501` ("line too long") or `S603` ("a program is started from variable input"). Rules are grouped by the letters at the start of their codes, and you switch groups on by those letters.

## Why this repository uses it

The platform's `lint` step must be cheap and strict. The security group (the letter `S`, from a tool named "bandit") matters more than usual here: this code builds `subprocess` commands for `git`, `docker` and `make`, and opens URLs, which is where such mistakes happen.

## Where it appears

| Path | Use |
|---|---|
| `pyproject.toml` lines 32 to 42 | The settings. |
| `Makefile` | `lint` runs `ruff check .` and `ruff format --check .`; `format` runs `ruff check --fix .` then `ruff format .`. |
| `src/` | Lines that end in `# noqa: CODE - reason`. |

## How it works underneath

ruff reads every `.py` file and turns it into a *syntax tree* (a structured picture of the program: functions, statements, calls). It applies each enabled rule to the tree and reports matches with file, line and code. It does not run your program. The formatter prints the same tree back in a fixed style. `ruff check --fix` applies the fixes it is sure about. `ruff format --check` reports unformatted files and exits with 1, changing nothing.

## Walkthrough of this repository's use

### The settings

```toml
[tool.ruff]
line-length = 120
target-version = "py312"
src = ["src", "tests"]
extend-exclude = ["template"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "N", "C4", "RUF", "PT", "S", "D100", "D101", "D103", "D104"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D", "S"]
```

- **Line 32**: `[tool.ruff]` starts the table of general settings ([toml.md](toml.md)). **Line 33**: `line-length = 120`: lines wrap at 120 characters and rule `E501` complains above that. **Line 34**: `target-version = "py312"`: the oldest Python the code must run on, so ruff may suggest newer syntax (group `UP`). **Line 35**: `src = ["src", "tests"]`: the folders that are the project's own code, so the import sorter can tell *ours* from third-party. **Line 36**: `extend-exclude = ["template"]`: **skip the `template/` folder.** Its files contain placeholders such as `__NAME__` and are not meant to satisfy this project's rules; they are checked by the golden-path audit instead ([github-actions.md](github-actions.md)).
- **Line 38**: `[tool.ruff.lint]`. **Line 39**: `select = [...]` switches rule groups on:

| Prefix | What it checks |
|---|---|
| `E` | style errors from pycodestyle (line length, whitespace) |
| `F` | Pyflakes: unused imports and variables, undefined names |
| `I` | isort: the order of `import` lines |
| `B` | bugbear: constructs that are probably bugs (for example a mutable default argument) |
| `UP` | pyupgrade: old syntax that has a newer form |
| `SIM` | simplifications of needlessly complicated code |
| `N` | naming conventions |
| `C4` | clearer ways to write comprehensions |
| `RUF` | ruff's own rules |
| `PT` | style of pytest tests |
| `S` | security (from "bandit") |
| `D100`, `D101`, `D103`, `D104` | a docstring is missing from a module, a class, a function, a package |

- **Lines 41 and 42**: `[tool.ruff.lint.per-file-ignores]` with `"tests/**" = ["D", "S"]`: docstring rules and security rules are off in the tests folder, because tests use `assert` (which the security group flags) and need no docstrings.

### The commands

`ruff check .` prints each finding and exits non-zero if there is any (the dot means the whole project). `ruff format --check .` fails if any file would be reformatted. `make format` runs `ruff check --fix .` (applies the safe fixes) and `ruff format .` ([make.md](make.md)).

### Reasoned exceptions in the code

A line may end with `# noqa: CODE - reason`: `noqa` means "no quality assurance" for that line, for that rule only, and the text after the dash is the reason, so a reviewer can judge it. Those in this repository:

- `collector_client.py` lines 42 and 49: `# noqa: S310 - scheme checked in __init__`. Rule `S310` warns that a URL could use `file:///...` and read a local file. `CollectorEventSink.__init__` refuses any address that does not start with `http://` or `https://`.
- `repositories.py` lines 13, 14 and 34, `local_pipeline.py` line 41, `cli.py` line 97: `# noqa: S603` and `S607`: rules about starting a program from variable input (`S603`) and about naming a program without its full path such as `git` (`S607`). Here the command is always a list built by this program and is never passed through a shell, so nothing a stranger types can become a command.
- `simulation.py` line 90: `# noqa: S311 - a simulation, not a secret`. Rule `S311` says Python's `random` module is not safe for passwords or tokens; here it only drives a repeatable pretend month.

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
