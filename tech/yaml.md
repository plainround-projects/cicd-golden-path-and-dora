# YAML

## What it is

YAML is a text format for structured data: **mappings** (`key: value`), **lists** (lines starting with `- `) and **scalars** (text, numbers, true/false). Indentation with spaces shows nesting; tabs are not allowed. PyYAML 6.0.3 reads and writes it in Python.

## Why this repository uses it

YAML is the format of the tools around the platform (GitHub Actions workflows, Docker Compose) **and** of the platform's own records: the list of teams, the catalog entry of each service, and the file that says which golden path generated a repository. Because the platform reads YAML itself, it can audit what a team has changed.

## Where it appears

| Path | Reader and meaning |
|---|---|
| `.github/workflows/ci.yml`, `template/.github/workflows/ci.yml` | GitHub Actions; PyYAML in the audit. |
| `docker-compose.yml`, `template/deploy/compose.yaml` | Docker Compose. |
| `catalog/teams.yaml` | The registered teams: `team-orders`, `team-billing`, `team-search`, `team-platform`. |
| `template/catalog-info.yaml` | A service's catalog entry: name, owner, lifecycle, runbook, SLO. |
| `template/.golden-path.yaml` | Which golden-path version generated the repository, plus expiring `exceptions`. |
| `src/goldenpath/infrastructure/catalog_files.py`, `auditor.py` | `yaml.safe_load`, `yaml.safe_dump`. |

## How it works underneath

A YAML parser turns text into plain data (dicts, lists, strings, numbers, booleans, null); the meaning of the keys belongs to whatever reads it. Rules that matter: `key: value` needs a space after the colon; quote values that must stay text (`"5432"`, `"3.12"`); `#` starts a comment; `|` keeps line breaks and `>` folds them; in YAML 1.1 (PyYAML's version) the words `on`, `off`, `yes`, `no` read as booleans.

## Walkthrough of this repository's use

### The teams list

```yaml
teams:
  - team-orders
  - team-billing
  - team-search
  - team-platform
```
```python
data = yaml.safe_load(self._teams_file.read_text()) or {}
return frozenset(str(team) for team in data.get("teams", []))
```
`safe_load` builds only plain data and never runs code (a plain `yaml.load` of untrusted text can). `or {}` handles an empty file. A service's `owner` must be in this set: a team, never a person.

### A service's catalog entry (template, before rendering)

```yaml
name: __NAME__
owner: __OWNER__
lifecycle: production
runbook: __RUNBOOK__
slo: availability 99.9% over 30 days
```
The renderer replaces `__NAME__` and the others ([python.md](python.md)). Then `catalog.validate` checks: the name is lowercase letters, digits and dashes; the owner matches `team-<name>` and is a registered team; the lifecycle is one of `experimental`, `production`, `deprecated`; the runbook starts with `https://`; the SLO is not empty.

`FileCatalog.register` writes the entry with `yaml.safe_dump(entry.as_mapping(), sort_keys=False)`: the keys stay in the order of the mapping.

### The golden-path marker

```yaml
golden_path: v1
platform_ref: __PLATFORM_REF__
exceptions: []   # each: {control, reason, owner, expires: YYYY-MM-DD}; the platform tracks and expires them
```
`[]` is an empty list written inline. An exception to the contract needs a control, a reason, an owner and an expiry date.

### The `on:` surprise

```python
document = yaml.safe_load(text)
if True in document:
    document["on"] = document.pop(True)
```
PyYAML reads the workflow key `on:` as the boolean `True`. `load_workflow` moves it back under the string `"on"` before the rules look at it.

### Compose and workflows

Both are mappings and lists with `${VAR:-default}` and `${{ expression }}` text that **Compose** and **GitHub** (not YAML) interpret ([docker-compose.md](docker-compose.md), [github-actions.md](github-actions.md)). The folded string `>-` in the workflow's `options:` joins lines with spaces.

## Try it yourself

```bash
.venv/bin/python -c "import yaml; print(yaml.safe_load(open('catalog/teams.yaml')))"
```
Expect `{'teams': ['team-orders', 'team-billing', 'team-search', 'team-platform']}`.

```bash
.venv/bin/python -c "
import yaml
print(yaml.safe_dump({'name': 'x', 'owner': 'team-a'}, sort_keys=False), end='')
print(yaml.safe_load('v: 3.10'), yaml.safe_load('v: \"3.10\"'))
"
```
Expect the two lines `name: x` and `owner: team-a`, then `{'v': 3.1} {'v': '3.10'}`.

```bash
.venv/bin/goldenpath audit template 2>&1 | tail -3
```
The template still holds `__NAME__`-style placeholders, so the audit reports `GP-PLACEHOLDER` findings for its files; a generated repository reports `conforms to the golden path contract`.

## Mistakes people make

- Tabs for indentation.
- Unquoted version numbers that lose digits.
- Treating `on` or `no` as text.
- `yaml.load` on untrusted input (use `safe_load`).
- Letting a person's name be an owner. The catalog accepts only `team-*` names.

## Check yourself

1. What shows nesting in YAML? *Indentation with spaces.*
2. Why `safe_load`? *It builds only plain data and cannot run code.*
3. Why quote `"3.12"`? *Unquoted it is a number; `3.10` would become `3.1`.*
4. What can a team owner be? *A registered `team-*` name from `catalog/teams.yaml`.*
5. What does an exception need? *A control, a reason, an owner and an expiry date.*

## Further reading

- YAML 1.2: https://yaml.org/spec/1.2.2/
- PyYAML: https://pyyaml.org/wiki/PyYAMLDocumentation (6.0.3)
