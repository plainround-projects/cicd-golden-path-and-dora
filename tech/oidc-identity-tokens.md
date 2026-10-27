# OpenID Connect identity tokens (short-lived credentials)

## What it is

OpenID Connect (OIDC) lets one system prove its identity to another without a shared password. In GitHub Actions, a running job can ask GitHub for a **token**: a small signed document (a **JWT**, JSON Web Token) that says "I am the job `ci.yml` of repository `owner/name`, on branch `main`, run number N". The token is signed by GitHub, expires in minutes, and names an **audience**: the service it is meant for. A service that trusts GitHub can check the signature and accept the job, with no stored key or password.

## Why this repository uses it

The golden path's third non-negotiable rule: *short-lived deploy credentials from the CI identity, not a stored key. A stored key leaks, and a leaked key lasts.* The release job uses an identity token for two things: keyless image signing ([cosign.md](cosign.md)) and authenticating to the event collector. The template contains no `secrets.AWS_ACCESS_KEY_ID`-style stored credential, and the audit looks for them.

## Where it appears

| Path | Use |
|---|---|
| `template/.github/workflows/ci.yml` | `permissions: id-token: write` on the `release` job only. |
| `template/scripts/emit-event.sh` | Requests a token with audience `goldenpath-events`. |
| `src/goldenpath/domain/rules.py` | `GP-OIDC` (the release job asks for a token), `GP-PERMS` (not at top level), `scan_for_credentials` (no stored keys). |
| `docs/adr/0003-sign-in-ci-with-the-identity-and-verify-twice.md` | The decision record. |

## How it works underneath

1. A job with `id-token: write` gets two environment variables: `ACTIONS_ID_TOKEN_REQUEST_URL` and `ACTIONS_ID_TOKEN_REQUEST_TOKEN`.
2. The job calls the URL with the request token (and optionally `&audience=...`). GitHub replies with `{"value": "<the JWT>"}`.
3. The JWT has three parts. The middle part holds **claims**: `iss` (issuer, `https://token.actions.githubusercontent.com`), `sub` (subject, naming repository and branch), `aud` (audience), `exp` (expiry).
4. The receiver checks the signature against GitHub's published keys, then checks `iss`, `aud` and `sub`.

## Walkthrough of this repository's use

```yaml
    permissions:
      contents: read
      packages: write
      id-token: write # a short-lived identity token for keyless signing and for the event collector; no stored key
```
Only the `release` job has `id-token: write`. The top of the file sets `permissions: contents: read` and the audit rejects `id-token` there, so a lint or test job cannot mint tokens.

```sh
if [ -z "$token" ] && [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then
  token=$(curl -fsS -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=goldenpath-events" | python3 -c 'import json,sys; print(json.load(sys.stdin)["value"])')
fi
```
If no static token is given and the job can request one, fetch a JWT whose audience is `goldenpath-events` and extract the `value` field. The token is then sent as `Authorization: Bearer ...` to the collector ([http-server.md](http-server.md)).

For signing, no code is needed: with no `--key`, cosign sees the same environment variables, fetches a token and gets a certificate for it. `verify.sh` then requires `--certificate-oidc-issuer https://token.actions.githubusercontent.com` and an identity regular expression naming this repository's `ci.yml`.

### What this repository did and did not exercise

Locally, the collector is protected by a **static bearer token** (`COLLECTOR_TOKEN`), and signing uses a key file. The OIDC paths exist in the template and the scripts but were **not run**: they need a real GitHub Actions run. The README says so. The collector here does not validate a JWT; production use would verify GitHub's signature and the audience on the collector's side.

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
