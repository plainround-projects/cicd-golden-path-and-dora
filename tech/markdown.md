# Markdown

## What it is

Markdown is a lightweight way to write formatted text in a plain file: `#` for headings, `-` for bullets, backticks for code, `|` for tables. GitHub shows `.md` files as formatted pages. Every document in this repository is Markdown.

## Why this repository uses it

Documentation sits next to the code and goes through the same review. Two Markdown files are also **product**: `template/README.md` is copied into every generated service and tells the team what they got and what they may change, and `docs/golden-path-contract.md` states the three rules that cannot be turned off.

## Where it appears

| Path | Use |
|---|---|
| `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md` | The platform's documentation. |
| `docs/golden-path-contract.md` | The contract: required checks, signed artifacts, short-lived credentials, and the exception process. |
| `docs/adr/0001...0006` | Architecture decision records: one decision each. |
| `template/README.md` | The README of every generated service, with `__NAME__`, `__OWNER__`, `__RUNBOOK__`, `__PLATFORM_REF__` placeholders. |
| `tech/*.md` | These notes. |

## How it works underneath

Markdown is just text. A renderer turns it into HTML. Nothing in the pipeline renders it; the template renderer copies the README as a text file and replaces the placeholders like in any other file, and the audit refuses a repository in which a placeholder is left (`GP-PLACEHOLDER`).

## Walkthrough of this repository's use

```markdown
| | |
| --- | --- |
| Owner | `__OWNER__` (a team, not a person) |
| Runbook | __RUNBOOK__ |
| SLO | availability 99.9% over 30 days |
```
A table: the first row is the header (empty here), the second the separator, the rest are rows. After rendering, `__OWNER__` becomes `team-orders` and `__RUNBOOK__` becomes a link such as `https://wiki.example.com/runbooks/orders`.

```markdown
- `release` builds one image, pushes it, **signs** it, attaches a provenance statement, **verifies** both, and only then deploys that digest.
```
`**bold**` for emphasis, backticks for code names. The "What you get" and "What you may change" sections of the template README tell a team where the line is between their code (`app/`, `tests/`) and the platform's (`.github/workflows/ci.yml`, `scripts/`, `protection.json`, `catalog-info.yaml`).

The renderer skips nothing in this file: any `__SOMETHING__` in it is replaced, and any left over would be caught by `rules.unreplaced_placeholders`:

```python
re.search(r"__[A-Z_]+__", text)
```
A pattern for two underscores, capital letters or underscores, two underscores.

Decision records (`docs/adr/*.md`) follow one shape: a title, the context, the decision and what follows from it. The six cover the pipeline's clock, the metric definitions, signing and verifying, the collector, the audit, and the simulation's assumptions.

## Try it yourself

```bash
grep -n "^## " README.md
```
Lists the headings of the platform README.

```bash
grep -c "__[A-Z_]*__" template/README.md
```
The template README has several placeholders.

```bash
.venv/bin/python -c "
from pathlib import Path
from goldenpath.domain import rules
print(rules.unreplaced_placeholders({'README.md': Path('template/README.md').read_text()}))
"
```
Expect one `GP-PLACEHOLDER` finding.

## Mistakes people make

- Documentation that nothing checks and so goes stale.
- Leaving a placeholder in a generated file.
- Using bold text where a heading is meant.

## Check yourself

1. What does the template README tell a team? *What they get, how to run it, and what they may change.*
2. Why does the audit look for `__X__`? *A leftover placeholder means rendering was incomplete.*
3. What is an ADR? *A short record of one design decision.*
4. Is Markdown rendered by the pipeline? *No; it is copied as text.*
5. Which file lists the non-negotiables? *`docs/golden-path-contract.md`.*

## Further reading

- CommonMark: https://spec.commonmark.org/
- GitHub Flavored Markdown: https://github.github.com/gfm/
