# JSON

## What it is

JSON is a text format for data made of objects (`{"key": value}`), arrays (`[1, 2]`), strings, numbers, `true`, `false` and `null`. Almost every web API speaks it. Python's `json` module converts between JSON text and dicts, lists, strings, numbers, booleans and `None`.

## Why this repository uses it

JSON is the common language between the pieces: the pipeline's shell scripts send events to the collector as JSON, the collector replies in JSON, the provenance statement attached to every image is JSON, and the branch-protection rules are a JSON file.

## Where it appears

| Path | Use |
|---|---|
| `template/scripts/emit-event.sh` | Builds the event body with `printf` and reads the identity token reply. |
| `src/goldenpath/interfaces/collector.py` | `json.loads` the request, `json.dumps` the reply. |
| `src/goldenpath/infrastructure/collector_client.py` | `json.dumps` the events, `json.loads` the reply. |
| `template/Makefile` (`attest`) | Writes `.build/provenance.json`. |
| `template/protection.json` | The branch-protection payload for `main`. |
| `src/goldenpath/infrastructure/auditor.py` | `json.loads` of `protection.json`, checked by `rules.check_protection`. |

## How it works underneath

`json.loads(text)` parses text into Python objects; `json.dumps(obj)` writes them back. Only dicts with string keys, lists, strings, numbers, booleans and `None` round-trip; a `datetime` must be converted first (the client sends `event.ts.isoformat()`).

## Walkthrough of this repository's use

### An event on the wire

```json
{"service": "orders", "type": "deploy", "ref": "orders-d1:a1+a2", "detail": ""}
```
No `ts`: the collector stamps the event with its own clock. The collector accepts one object or a list of them.

```python
payload = json.loads(self.rfile.read(length))
items = payload if isinstance(payload, list) else [payload]
```
Normalise to a list, then build and validate each `Event`. A parse error, a wrong type or a missing key becomes a `400` with the reason ([http-server.md](http-server.md)).

### The provenance statement

```make
@printf '{"builder": "%s", "repository": "%s", "commit": "%s", "built_at": "%s"}\n' \
  "$${GITHUB_WORKFLOW:-local}" "$(NAME)" "$$(git rev-parse HEAD)" "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .build/provenance.json
```
Four fields: which workflow built it (`local` on a laptop), which repository, which commit, when (UTC, ISO 8601). `cosign attest` signs this document as the image's attestation ([cosign.md](cosign.md)).

### Branch protection

```json
{
  "required_status_checks": { "strict": true, "contexts": ["lint", "test", "release"] },
  "enforce_admins": true,
  "required_pull_request_reviews": { "required_approving_review_count": 1 },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
```
The body GitHub's branch-protection API expects. `strict: true` means the branch must be up to date. `enforce_admins: true` applies the rules to owners too. `restrictions: null` means no extra restriction on who may push (the pull-request rule already prevents direct pushes). The audit (`check_protection`) fails if a required check, `strict`, administrators or a pull-request requirement is missing.

## Try it yourself

```bash
.venv/bin/python -c "import json; print(json.load(open('template/protection.json'))['required_status_checks']['contexts'])"
```
Expect `['lint', 'test', 'release']`.

```bash
.venv/bin/python -c "
import json
from goldenpath.domain import rules
p = json.load(open('template/protection.json')); p['enforce_admins'] = False
print([f.code for f in rules.check_protection(p)])
"
```
Expect `['GP-ADMINS']`.

```bash
printf '{"builder": "%s", "commit": "%s"}\n' local abc | python3 -m json.tool
```
`json.tool` pretty-prints and also proves the text is valid JSON.

## Mistakes people make

- Building JSON by gluing strings when a value may contain quotes. The shell script's values are service names, ids and types that the collector validates; a value with a quote would be rejected.
- Trailing commas and single quotes (not valid).
- Dumping a `datetime` directly.

## Check yourself

1. Why does the event have no `ts` field? *The collector's clock sets it.*
2. What does `strict: true` mean in the protection body? *The branch must be up to date before merging.*
3. What can the collector accept as a body? *One event object or a list.*
4. What is in the provenance statement? *Builder, repository, commit and build time.*
5. Which function checks the protection JSON? *`rules.check_protection`.*

## Further reading

- JSON: https://www.json.org/ and RFC 8259
- `json` module: https://docs.python.org/3.12/library/json.html
- Branch protection API: https://docs.github.com/en/rest/branches/branch-protection#update-branch-protection
