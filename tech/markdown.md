# Markdown

## What it is

**Markdown** is a way to write formatted text in a plain text file using a few simple marks. A `#` at the start of a line makes a heading (`##` a smaller one); `- ` starts a bullet; `1.` a numbered item; words in `**double stars**` are bold; words in `` `backticks` `` are shown as code; three backticks on a line of their own start and end a block of code; and rows with `|` between cells make a table, with a second row of dashes (`| --- | --- |`) under the header row. Files ending in `.md` hold Markdown. GitHub shows them as formatted pages; a text editor shows the marks.

## Why this repository uses it

Documentation lives next to the code and goes through the same review. Two Markdown files are also **product**: `template/README.md` is copied into every generated service and tells the team what they got and what they may change; `docs/golden-path-contract.md` states the three rules that cannot be turned off.

## Where it appears

| Path | Use |
|---|---|
| `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md` | The platform's documentation. |
| `docs/golden-path-contract.md` | The contract: required checks, signed artifacts, short-lived credentials, and the exception process. |
| `docs/adr/0001...0006` | Architecture decision records: one decision each. |
| `template/README.md` | The README of every generated service, with `__NAME__`, `__OWNER__`, `__RUNBOOK__` and `__PLATFORM_REF__` placeholders. |
| `tech/*.md` | These notes. |

## How it works underneath

Nothing in the pipeline renders Markdown. It is plain text, so the contract check treats the README as a list of lines and looks for the line `## The pipeline's contract`. The marks only matter to the reader and to GitHub's page.

## Walkthrough of this repository's use

### `template/README.md`: the file every new service starts with

```markdown
# __NAME__

A service generated from the golden path (platform commit `__PLATFORM_REF__`). It owns nothing but its code: the pipeline,
the signing, the deploy credentials and the catalog entry come from the template and cannot be turned off.

| | |
| --- | --- |
| Owner | `__OWNER__` (a team, not a person) |
| Runbook | __RUNBOOK__ |
| SLO | availability 99.9% over 30 days |

## What you get

- `.github/workflows/ci.yml`: `lint`, `test` and `release` run on every push; `release` runs on `main` only. Every action is pinned to a full commit SHA, the workflow has read-only permissions, and only the release job may ask for an identity token.
- `release` builds one image, pushes it, **signs** it, attaches a provenance statement, **verifies** both, and only then deploys that digest. An image that does not verify is never deployed.
- No stored cloud key or deploy password: the release job gets a short-lived identity token from the CI system (OIDC).
- `protection.json`: the branch protection to apply to `main` (required checks `lint`, `test`, `release`, branch up to date, pull request required, administrators included).
- `catalog-info.yaml`: owner (a team), lifecycle, runbook and SLO.

## Run it

```bash
make ci        # lint and test
make release   # image, sign, attest, verify, deploy (see the Makefile for the variables)
```

## What you may change

The language, framework and tests (`app/`, `tests/`), the number of environments, your own alerts. Anything touching `.github/workflows/ci.yml`, `scripts/`, `protection.json` or `catalog-info.yaml` is audited by the platform (`goldenpath audit`); ask in the platform channel for an exception, and every exception expires (default 30 days).
```

- **Line 1**: `# __NAME__`, a heading with a placeholder. **Line 3**: a paragraph saying the service was generated from the golden path at platform commit `__PLATFORM_REF__`, and that it owns only its code: the pipeline, the signing, the deploy credentials and the catalog entry come from the template and cannot be turned off.
- **Lines 6 to 10**: a table: the first row is the header (empty cells), the second `| --- | --- |` is the separator, the rest are rows: the owner (`__OWNER__` "a team, not a person"), the runbook link and the SLO (`availability 99.9% over 30 days`).
- **Lines 12 to 18**, "What you get": a bulleted list (`- `) with `**bold**` for emphasis and backticks for code names: the workflow (`lint`, `test`, `release`; every action pinned to a full commit; read-only permissions; only the release job may ask for an identity token), what `release` does (build one image, push it, **sign** it, attach provenance, **verify** both, deploy that digest), the lack of stored credentials, `protection.json`, `catalog-info.yaml`.
- **Lines 20 to 25**: "Run it" with a fenced block (three backticks on lines of their own) showing `make ci` and `make release`. **Lines 27 to 29**: "What you may change" (the language, the framework and tests in `app/` and `tests/`, the number of environments, your own alerts) and what is audited (`.github/workflows/ci.yml`, `scripts/`, `protection.json`, `catalog-info.yaml`), with the rule that every exception expires (default 30 days).

### How placeholders are handled

`FileTemplateRenderer` replaces `__NAME__` and the others in every text file with plain text replacement, so this README is rendered like any other file. The audit then refuses a generated repository that still has a placeholder:

<!-- fmt:off -->
```python
def unreplaced_placeholders(files: Mapping[str, str]) -> list[Finding]:
    """A generated repository must not still hold a `__NAME__`-style placeholder."""
    return [
        Finding("GP-PLACEHOLDER", "template", f"{path} still contains a placeholder")
        for path, text in sorted(files.items())
        if re.search(r"__[A-Z_]+__", text)
    ]
```
<!-- fmt:on -->

`re.search(r"__[A-Z_]+__", text)` finds two underscores, capital letters or underscores, two underscores, so `__NAME__` is caught while `__init__` and `__main__` (lower case) are not. Each hit is a `GP-PLACEHOLDER` finding ([python.md](python.md)).

### The platform's own documents

`README.md` has the lesson's "Done when" table with the commands and evidence; `ARCHITECTURE.md` the components and layers; `docs/adr/` six numbered decision records (the pipeline's clock, the metric definitions and window, sign in CI with the identity and verify twice, a collector in front of the store, the audit of the generated repository, the simulation's stated assumptions), each with Context, Decision and Consequences; `CHANGELOG.md` the changes by version.

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
