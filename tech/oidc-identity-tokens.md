# OpenID Connect identity tokens (short-lived credentials)

## What it is

Suppose one computer system (a CI job) must prove to another (a signing service, an event collector) who it is. The old way is to give the first system a **password or key** to store: a long-lived secret. Stored secrets leak, and a leaked one stays useful until somebody notices.

**OpenID Connect (OIDC)** offers another way. The platform that runs the job (GitHub) acts as an *identity provider*. A running job can ask it for a **token**: a short text, signed by GitHub, that says "I am the workflow `ci.yml` of repository `owner/name`, on branch `main`, run number N, and this token is meant for the audience X". The token expires in minutes. A service that trusts GitHub can check the signature, the audience and the identity, and accept the job with **no stored secret anywhere**.

The format is a **JWT** (JSON Web Token): three text parts joined by dots; the middle part is a JSON object of **claims**: `iss` (the issuer, who signed it: `https://token.actions.githubusercontent.com`), `sub` (the subject: which repository, branch or environment), `aud` (the audience: who the token is for), `exp` (when it expires). It is signed, not secret: do not log it, but nobody can forge or change it.

## Why this repository uses it

The golden path's third non-negotiable rule: *short-lived deploy credentials from the CI identity, not a stored key. A stored key leaks, and a leaked key lasts.* The release job uses an identity token for two things: keyless image signing ([cosign.md](cosign.md)) and authenticating to the event collector. The template contains no stored cloud key or deploy password, and the audit looks for them.

## Where it appears

| Path | Use |
|---|---|
| `template/.github/workflows/ci.yml` lines 44 to 47 | `id-token: write` on the `release` job only. |
| `template/scripts/emit-event.sh` lines 13 to 15 | Requests a token for the audience `goldenpath-events`. |
| `src/goldenpath/domain/rules.py` | `GP-OIDC` (the release job asks for a token), `GP-PERMS` (not at the top level), `scan_for_credentials` (no stored keys). |
| `docs/adr/0003-sign-in-ci-with-the-identity-and-verify-twice.md` | The decision record. |

## How it works underneath

1. A job whose `permissions` include `id-token: write` receives two environment variables: `ACTIONS_ID_TOKEN_REQUEST_URL` and `ACTIONS_ID_TOKEN_REQUEST_TOKEN`.
2. The job sends a web request to that URL with the request token (and optionally `&audience=NAME`). GitHub replies with JSON: `{"value": "<the JWT>"}`.
3. The job gives the JWT to whoever needs to be convinced.
4. The receiver checks the signature against GitHub's published public keys and then checks `iss`, `aud` and `sub`.

## Walkthrough of this repository's use

### Asking for the permission, only where it is needed

```yaml
permissions:
  contents: read
```

The top of the workflow grants only `contents: read`.

```yaml
    permissions:
      contents: read
      packages: write
      id-token: write # a short-lived identity token for keyless signing and for the event collector; no stored key
```

The `release` job alone adds `packages: write` and `id-token: write` ("a short-lived identity token for keyless signing and for the event collector; no stored key"). A lint or test job cannot request a token at all. The audit enforces both halves: `GP-OIDC` fails if `release` lacks `id-token: write`, and `GP-PERMS` fails if `id-token` appears in the top-level permissions.

### Asking for the token: `emit-event.sh`

```sh
token=${EVENTS_TOKEN:-}
if [ -z "$token" ] && [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then
  token=$(curl -fsS -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=goldenpath-events" | python3 -c 'import json,sys; print(json.load(sys.stdin)["value"])')
fi
payload=$(printf '{"service": "%s", "type": "%s", "ref": "%s", "detail": "%s"}' "$SERVICE_NAME" "$type" "$ref" "$detail")
```

- `token=${EVENTS_TOKEN:-}` takes a static token if given (a local run). `if [ -z "$token" ] && [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then` means: if there is none, *and* this job can request one, then request it: `curl -fsS -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=goldenpath-events"` ([curl.md](curl.md)), and pick the field `value` out of the JSON reply with a one-line Python program (`python3 -c 'import json,sys; print(json.load(sys.stdin)["value"])'`; `|` sends curl's output into Python's input). The audience `goldenpath-events` says the token is meant for the collector and nothing else. The token then goes in the `Authorization: Bearer ...` header of the event request ([http-server.md](http-server.md)).

### Signing needs no code of its own

With no `--key`, cosign sees the same two environment variables itself, fetches a token, and obtains a certificate for it. `verify.sh` then requires `--certificate-identity-regexp "^https://github.com/<repo>/.github/workflows/ci.yml@.*$"` and `--certificate-oidc-issuer "https://token.actions.githubusercontent.com"` ([cosign.md](cosign.md)).

### The audit looks for stored keys

```python
_CREDENTIAL_PATTERNS: Final = {
    "an AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "an AWS secret access key": re.compile(r"aws_secret_access_key\s*[:=]\s*\S+", re.IGNORECASE),
    "a private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "a GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "a stored cloud or registry secret in the workflow": re.compile(
        r"secrets\.[A-Z0-9_]*(ACCESS_KEY|SECRET_KEY|PRIVATE_KEY|PASSWORD|CLIENT_SECRET|SERVICE_ACCOUNT)[A-Z0-9_]*"
    ),
}
```

`_CREDENTIAL_PATTERNS` finds text that looks like a long-lived secret: an AWS access key id, an AWS secret assignment, a private key header, a GitHub token, or a workflow that reads a stored secret named like `..._PASSWORD`, `..._ACCESS_KEY`, `..._SECRET_KEY`, `..._CLIENT_SECRET` or `..._SERVICE_ACCOUNT`. Any hit is `GP-SECRET`.

### What was run and what was not

Locally the collector is protected by a **static bearer token** (`COLLECTOR_TOKEN`), and signing uses a key file. The OIDC paths are written in the template and the scripts but were **not run**: they need a real GitHub Actions run. The collector in this repository does not validate a JWT; a production collector would verify GitHub's signature, the audience and the subject itself.

## Try it yourself

```bash
grep -n "id-token" template/.github/workflows/ci.yml .github/workflows/ci.yml
```
Expect one hit in the template, on the `release` job's permissions, and none in the platform's own workflow.

```bash
.venv/bin/python -c "
from goldenpath.domain import rules
from goldenpath.infrastructure.auditor import load_workflow
doc = load_workflow(open('template/.github/workflows/ci.yml').read())
doc['permissions']['id-token'] = 'write'
print([f.code for f in rules.check_workflow(doc)])
"
```
Expect `['GP-PERMS']`: top-level `id-token` is refused.

```bash
.venv/bin/python -c "
from goldenpath.domain import rules
print(rules.scan_for_credentials({'ci.yml': 'password: \${{ secrets.AWS_SECRET_KEY }}'}))
"
```
Expect one `GP-SECRET` finding.

## Mistakes people make

- Storing a cloud key as a repository secret. It never expires and can be copied.
- Granting `id-token: write` to the whole workflow.
- Accepting any GitHub token: a receiver must check the audience and the subject.
- Treating a JWT as encrypted. It is signed, not secret; do not log it.

## Check yourself

1. What is the point of an audience claim? *It says which service the token is meant for.*
2. Which job may request a token? *Only `release`.*
3. Why is a short-lived token safer than a stored key? *If stolen, it is useless a few minutes later.*
4. What does the receiver check? *The signature, issuer, audience and subject.*
5. What was not run here? *The real GitHub OIDC flow; it needs GitHub Actions.*

## Further reading

- About OIDC in GitHub Actions: https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect
- The token's claims: https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect#understanding-the-oidc-token
- OpenID Connect Core: https://openid.net/specs/openid-connect-core-1_0.html
