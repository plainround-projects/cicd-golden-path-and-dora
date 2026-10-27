# YAML

## What it is

**YAML** is a text format for writing structured information that people can read comfortably. Many tools are configured with it. This repository's GitHub workflows, Docker Compose file and Dependabot settings are all YAML. In Python the library **PyYAML** (version 6.0.3 here) reads it.

The building blocks:

- A **mapping** is a set of `key: value` pairs. After the colon there must be a space.
- A **list** is a series of lines each starting with `- ` (dash and space). A list of mappings looks like `- name: a` followed by indented `  uses: b`.
- A **scalar** is a single value: text, a number, `true`/`false`, or `null`.
- **Indentation shows nesting**, with spaces. Tabs are not allowed. Lines indented further belong to the line above.
- `#` starts a comment.
- **Quotes** matter: `"5432"` is text, but `5432` is a number. `"3.12"` is text, but `3.12` is a number, and `3.10` would be read as `3.1`, losing the zero. When a value must stay exactly as written, quote it.
- `|` after a key keeps the line breaks of the indented text below it; `>` folds those lines into one line; adding `-` (`|-`, `>-`) removes the final newline.
- In YAML 1.1 (the version PyYAML follows) the plain words `on`, `off`, `yes` and `no` are read as booleans.

A YAML parser turns the text into plain Python data: dictionaries, lists, strings, numbers, booleans. The *meaning* of the keys belongs to whichever tool reads the file.

## Why this repository uses it

YAML is the format of the tools around the platform (GitHub Actions workflows, Docker Compose) **and** of the platform's own records: the list of teams, the catalog entry of each service, and the marker that says which golden-path version generated a repository. Because the platform reads YAML itself, it can audit what a team has changed.

## Where it appears

| Path | Reader and meaning |
|---|---|
| `.github/workflows/ci.yml`, `template/.github/workflows/ci.yml` | GitHub Actions; PyYAML in the audit ([github-actions.md](github-actions.md)). |
| `docker-compose.yml`, `template/deploy/compose.yaml` | Docker Compose ([docker-compose.md](docker-compose.md)). |
| `catalog/teams.yaml` | The registered teams. |
| `template/catalog-info.yaml` | A service's catalog entry. |
| `template/.golden-path.yaml` | Which golden-path version generated the repository, plus expiring `exceptions`. |
| `src/goldenpath/infrastructure/catalog_files.py`, `auditor.py` | `yaml.safe_load`, `yaml.safe_dump`. |

## How it works underneath

PyYAML's `yaml.safe_load(text)` returns the data. The "safe" version builds only plain data and never creates arbitrary Python objects, so loading a file cannot run code. (`yaml.load` without safety can, which is why it is avoided for files you did not write.)

## Walkthrough of this repository's use

### `catalog/teams.yaml`

```yaml
# The teams that may own a service. An owner must be one of these: a real team, never a person.
teams:
  - team-orders
  - team-billing
  - team-search
  - team-platform
```

- **Line 1** is a comment: an owner must be one of these, a real team and never a person. **Line 2**: `teams:` is a mapping key whose value is the list below. **Lines 3 to 6**: four list items, each a dash and a team name: `team-orders`, `team-billing`, `team-search`, `team-platform`.
- Read by `FileCatalog.teams()`: `data = yaml.safe_load(self._teams_file.read_text()) or {}` gives `{"teams": [...]}` (`or {}` replaces `None`, which an empty file would give); `frozenset(str(team) for team in data.get("teams", []))` makes the set of names. `safe_load` builds only plain data and never runs code.

### `template/catalog-info.yaml`: a service's entry

```yaml
# Written by the template. The owner must be a registered team, never a person.
name: __NAME__
owner: __OWNER__
lifecycle: production
runbook: __RUNBOOK__
slo: availability 99.9% over 30 days
```

- **Line 1** is a comment (the owner must be a registered team, never a person). **Lines 2 to 6**: five keys, one mapping. `name`, `owner` and `runbook` hold placeholders (`__NAME__`, `__OWNER__`, `__RUNBOOK__`) that `FileTemplateRenderer` replaces with plain text replacement when it generates a service ([python.md](python.md)). `lifecycle: production` is one of `experimental`, `production`, `deprecated`. `slo: availability 99.9% over 30 days` is what the service promises (a *service level objective*).
- The audit reads the generated file back: `catalog_rules.from_mapping(yaml.safe_load(files["catalog-info.yaml"]))`, then `validate` checks the name's shape, that the owner looks like `team-...` and is a registered team, the lifecycle, an `https://` runbook and a non-blank SLO.

### `template/.golden-path.yaml`

```yaml
# Which version of the golden path generated this repository.
golden_path: v1
platform_ref: __PLATFORM_REF__
exceptions: []   # each: {control, reason, owner, expires: YYYY-MM-DD}; the platform tracks and expires them
```

- `golden_path: v1` is the version of the template. `platform_ref: __PLATFORM_REF__` becomes the platform commit that generated the repository. `exceptions: []` is an empty list written inline; the comment explains each exception would be a mapping `{control, reason, owner, expires: YYYY-MM-DD}` that the platform tracks and expires.

### Writing YAML

`FileCatalog.register` writes the entry with `yaml.safe_dump(entry.as_mapping(), sort_keys=False)`: the dictionary becomes YAML text, and `sort_keys=False` keeps the keys in the order given (`name`, `owner`, `lifecycle`, `runbook`, `slo`) instead of alphabetical.

### Workflows and Compose

Both are mappings and lists with their own placeholder syntax: `${{ expression }}` is evaluated by **GitHub**, and `${VAR:-default}` by **Compose**; neither is a YAML feature. The folded string `>-` in the platform workflow's `options:` joins lines into one ([github-actions.md](github-actions.md)). Every key is explained with its file.

### The `on:` trap

<!-- fmt:off -->
```python
def load_workflow(text: str) -> dict[str, Any]:
    """Parse a workflow. PyYAML reads the key `on` as the boolean True; put it back under "on"."""
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise ValueError("a workflow must be a mapping")
    if True in document:
        document["on"] = document.pop(True)
    return document
```
<!-- fmt:on -->

PyYAML reads the workflow key `on:` as the boolean `True`. `load_workflow` parses with `yaml.safe_load` (line 36), rejects anything that is not a mapping with `ValueError("a workflow must be a mapping")` (lines 37 and 38), and moves the `True` key back to the text key `"on"` (lines 39 and 40) so the rules can find the triggers. The tests check both (`load_workflow("on:\n  push:\njobs: {}\n")["on"]` contains `push`; `load_workflow("- a\n")` raises) ([pytest.md](pytest.md)).

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
