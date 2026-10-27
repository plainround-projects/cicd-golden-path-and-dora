# JSON

## What it is

**JSON** ("JavaScript Object Notation") is a text format for data, used by almost every web service and many tools. It has:

- **objects**: `{"name": "value", "count": 3}`, a set of key/value pairs where keys are text in double quotes;
- **arrays**: `[1, 2, 3]`, ordered lists;
- **strings** in double quotes, **numbers**, `true`, `false` and `null`.

Python's `json` module converts between JSON text and Python values: `json.loads(text)` turns text into dictionaries, lists, strings, numbers, booleans and `None`; `json.dumps(value)` turns them back into text (`indent=2` makes it readable). JSON has no dates and no tuples: a `datetime` must be converted to text first.

## Why this repository uses it

JSON is the common language between the pieces: the pipeline's shell scripts send events to the collector as JSON, the collector replies in JSON, the provenance statement attached to every image is JSON, and the branch-protection rules are a JSON file.

## Where it appears

| Path | Use |
|---|---|
| `template/scripts/emit-event.sh` | Builds the event body with `printf`; reads the identity-token reply. |
| `src/goldenpath/interfaces/collector.py` | `json.loads` the request, `json.dumps` the reply. |
| `src/goldenpath/infrastructure/collector_client.py` | `json.dumps` the events, `json.loads` the reply. |
| `template/Makefile` (`attest`) | Writes `.build/provenance.json`. |
| `template/protection.json` | The branch-protection body for `main`. |
| `src/goldenpath/infrastructure/auditor.py` | `json.loads` of `protection.json`, checked by `rules.check_protection`. |

## How it works underneath

`json.dumps({"ok": True, "none": None})` produces `{"ok": true, "none": null}`. Python's `True` becomes `true`, `None` becomes `null`. A JSON object's keys are always text. Parsing fails with an error if the text is not valid JSON (single quotes, a trailing comma and comments are not allowed).

## Walkthrough of this repository's use

### An event on the wire

```json
{"service": "orders", "type": "deploy", "ref": "orders-d1:a1+a2", "detail": ""}
```

Built by `emit-event.sh`: `payload=$(printf '{"service": "%s", "type": "%s", "ref": "%s", "detail": "%s"}' "$SERVICE_NAME" "$type" "$ref" "$detail")` ([bash-and-sh.md](bash-and-sh.md)). There is **no `ts`**: the collector adds its own time. The Python client builds the same shape (with `ts` as text from `event.ts.isoformat()`) in `collector_client.py` lines 30 to 41.

### In the collector

```python
        def _accept(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY_BYTES:
                self._reply(413 if length else 400, {"error": f"body must be 1 to {MAX_BODY_BYTES} bytes"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
                items = payload if isinstance(payload, list) else [payload]
                events = [event_from_json(item, now()) for item in items]
            except (json.JSONDecodeError, InvalidEventError, TypeError, AttributeError) as error:
                self._reply(400, {"error": str(error)})
                return
            try:
                accepted = record(sink, events)
            except (
                Exception
            ):  # the store is down or slow: say so, so the pipeline step can retry; never crash the handler
                self._reply(503, {"error": "the event store is unavailable, try again"})
                return
            self._reply(202, {"accepted": accepted, "received": len(events)})
```

- `payload = json.loads(self.rfile.read(length))` reads exactly `length` bytes of the request and parses them; `items = payload if isinstance(payload, list) else [payload]` accepts one object or a list; each becomes a validated `Event`. `except (json.JSONDecodeError, InvalidEventError, TypeError, AttributeError)` turns broken JSON or a wrong shape into a `400` with a message. Replies are built with `json.dumps(payload) + "\n"` and encoded to bytes ([http-server.md](http-server.md)).

### The provenance statement

```make
# A provenance statement: which commit and which build produced the digest.
attest:
	@printf '{"builder": "%s", "repository": "%s", "commit": "%s", "built_at": "%s"}\n' \
	  "$${GITHUB_WORKFLOW:-local}" "$(NAME)" "$$(git rev-parse HEAD)" "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .build/provenance.json
	cosign attest --yes --type custom --predicate .build/provenance.json $(KEY_FLAGS) $(IMAGE)@$$(cat $(DIGEST_FILE))
```

`printf '{"builder": "%s", "repository": "%s", "commit": "%s", "built_at": "%s"}\n' ... > .build/provenance.json` writes four fields: which workflow built it (`${GITHUB_WORKFLOW:-local}`: the workflow's name or `local`), the repository (`$(NAME)`), the full commit (`$(git rev-parse HEAD)`) and the UTC time (`date -u +%Y-%m-%dT%H:%M:%SZ`). `cosign attest` signs this file as the image's attestation ([cosign.md](cosign.md)).

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

The body GitHub's branch-protection API expects. `required_status_checks` is an object: `strict: true` means the branch must be up to date with `main` before merging, and `contexts` lists the job names that must pass (`lint`, `test`, `release`). `enforce_admins: true` applies the rules to owners too. `required_pull_request_reviews` requires a pull request and one approval. `restrictions: null` means no extra limit on who may push (the pull-request rule already prevents direct pushes). `allow_force_pushes: false` and `allow_deletions: false` protect the history. The audit parses this file with `json.loads` and `rules.check_protection` fails if a required check, `strict`, administrators or a pull-request requirement is missing ([github-actions.md](github-actions.md)).

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
