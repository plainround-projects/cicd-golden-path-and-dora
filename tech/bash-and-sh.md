# Shell scripts (`sh`)

## What it is

A **shell** is a program that reads commands, starts other programs and connects them. A **shell script** is a text file of such commands. `sh` is the small portable shell language every Unix machine has. The first line `#!/bin/sh` (the **shebang**) tells the operating system to run the file with `sh`; `chmod +x` makes it runnable. This repository's scripts use only features of plain `sh`, so they work on a Mac, on a Linux CI runner and inside a minimal container.

## Why this repository uses it

The generated service must be able to run its own release steps with nothing installed but `make`, `git`, `docker`, `curl` and `cosign`. Three small scripts do the glue: **verify** an image, **deploy** it (only after verifying) and **emit** an event to the platform's collector. They are part of the template, so every service gets the same ones, and the audit checks they stay.

## Where it appears

| File | Role |
|---|---|
| `template/scripts/verify.sh` | Refuses any image that is not signed and attested by this repository's pipeline. |
| `template/scripts/deploy.sh` | Verifies, then starts the image with compose; on a refusal records a `failed` event. |
| `template/scripts/emit-event.sh` | Sends one event (`commit`, `deploy`, `failed`, `recovered`) to the collector with `curl`. |
| `Makefile` (both) | Every recipe line is a shell command ([make.md](make.md)). |
| `.github/workflows/ci.yml` (template) | `run:` lines are shell snippets on the CI machine. |

## How it works underneath

- Every command is a **process**. It ends with an **exit status**: 0 is success, anything else is failure. `if cmd; then` runs the `then` part on 0.
- Three **streams**: 0 stdin, 1 stdout, 2 stderr. `>file` redirects stdout. `2>&1` points stderr where stdout currently points. `>/dev/null` discards.
- `$(command)` runs a command and substitutes its output. `"$@"` is all the arguments, each kept whole. `$1`, `$2` are the first and second.
- `${NAME:-default}` uses a default when `NAME` is unset or empty. `${NAME:?message}` aborts with the message when it is unset.
- `set -eu`: `-e` stops at the first failing command; `-u` makes an unset variable an error.
- `:` is a command that does nothing. `: "${X:?set X}"` is the idiom for "X must be set": the expansion does the check.

## Walkthrough of this repository's use

### `verify.sh`

```sh
set -eu
image=$1
```
Stop on error; the first argument is the image reference, always `registry/name@sha256:...` (a digest, not a tag).

```sh
quiet() {
  if ! output=$("$@" 2>&1 >/dev/null); then
    printf '%s\n' "$output" >&2
    exit 1
  fi
}
```
A function that runs the command given as its arguments. The redirections are read left to right: `2>&1` sends **stderr** into the pipe that `$(...)` captures, and then `>/dev/null` throws **stdout** away. So `output` holds only what the command wrote to stderr. cosign writes its report there. If the command fails, the report is printed to stderr and the script exits 1. If it succeeds, nothing is printed. `!` flips success and failure.

```sh
if [ -n "${COSIGN_PUBLIC_KEY:-}" ]; then
  quiet cosign verify --timeout=15m --key "$COSIGN_PUBLIC_KEY" --insecure-ignore-tlog=true "$image"
  quiet cosign verify-attestation --timeout=15m --key "$COSIGN_PUBLIC_KEY" --type custom --insecure-ignore-tlog=true "$image"
```
`[ -n ... ]` is true when the text is not empty. Local mode: a public key file checks the signature and the attached provenance statement. `--insecure-ignore-tlog=true` skips the public transparency-log check because the local demo never uploads to it. See [cosign.md](cosign.md).

```sh
else
  : "${GITHUB_REPOSITORY:?set GITHUB_REPOSITORY or COSIGN_PUBLIC_KEY}"
  identity="^https://github.com/${GITHUB_REPOSITORY}/.github/workflows/ci.yml@.*$"
  issuer="https://token.actions.githubusercontent.com"
  quiet cosign verify --timeout=15m --certificate-identity-regexp "$identity" --certificate-oidc-issuer "$issuer" "$image"
```
CI mode ("keyless"): the image must have been signed by **this repository's** `ci.yml` workflow, as proved by a certificate issued by GitHub's identity service. `identity` is a regular expression for that workflow's address. A different repository, or a different workflow file, does not match.

### `deploy.sh`

```sh
here=$(cd "$(dirname "$0")/.." && pwd)
if ! "$here/scripts/verify.sh" "$image"; then
  echo "deploy refused: $image does not verify" >&2
  "$here/scripts/emit-event.sh" failed "$deployment" signature || true
  exit 1
fi
IMAGE_REF="$image" docker compose -p "$name-production" -f "$here/deploy/compose.yaml" up -d --wait
"$here/scripts/emit-event.sh" deploy "$deployment:$commits"
```
`$0` is the script's own path; `dirname` strips the file name; `cd ... && pwd` gives the absolute path of the service folder. The deploy path **always** calls `verify.sh` first, so an unsigned image cannot reach `docker compose`. A refusal is recorded as a `failed` event with detail `signature` (and `|| true` means a failure to *record* it does not hide the real error). `IMAGE_REF="$image" docker compose ...` sets an environment variable for that one command only. `-p` names the compose project, `-f` the file, `--wait` waits for the health check. On success, a `deploy` event with ref `<deployment id>:<commits>` is emitted.

### `emit-event.sh`

```sh
type=$1
ref=$2
detail=${3:-}
: "${EVENTS_URL:?set EVENTS_URL}"
: "${SERVICE_NAME:?set SERVICE_NAME}"
```
Required: the event type and ref; optional detail; required variables.

```sh
token=${EVENTS_TOKEN:-}
if [ -z "$token" ] && [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then
  token=$(curl -fsS -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=goldenpath-events" | python3 -c 'import json,sys; print(json.load(sys.stdin)["value"])')
fi
```
A local run uses `EVENTS_TOKEN`. In GitHub Actions there is no stored secret: the job asks GitHub for a short-lived identity token with the audience `goldenpath-events` ([oidc-identity-tokens.md](oidc-identity-tokens.md)). The reply is JSON; a one-line `python3 -c` pulls out the `value` field. `-f` makes curl fail on HTTP errors, `-sS` is silent but shows errors ([curl.md](curl.md)).

```sh
payload=$(printf '{"service": "%s", "type": "%s", "ref": "%s", "detail": "%s"}' "$SERVICE_NAME" "$type" "$ref" "$detail")
curl -fsS -X POST "$EVENTS_URL/events" -H "Content-Type: application/json" -H "Authorization: Bearer $token" -d "$payload" >/dev/null
echo "event: $type $ref"
```
Build a small JSON body with `printf` and POST it. The event has **no time stamp** on purpose: the collector stamps it with its own clock, so a developer cannot set a lead time by hand. Because `set -e` is on, a failing `curl` stops the script.

## Try it yourself

```bash
sh -n template/scripts/verify.sh template/scripts/deploy.sh template/scripts/emit-event.sh && echo "syntax ok"
```
`-n` checks the syntax without running anything.

```bash
(unset EVENTS_URL; cd template && sh scripts/emit-event.sh commit abc 2>&1 | tail -1)
```
Expect `scripts/emit-event.sh: line 10: EVENTS_URL: set EVENTS_URL`. The `:?` form stops the script with the message (the wording around it depends on the shell).

```bash
sh -c 'output=$(echo out; echo err >&2) ; echo "captured: [$output]"' 2>/dev/null
sh -c 'output=$( { echo out; echo err >&2; } 2>&1 >/dev/null) ; echo "captured: [$output]"'
```
The first prints `captured: [out]` (stderr is not captured). The second shows the trick from `quiet()`: it prints `captured: [err]`.

```bash
make demo-unsigned
```
Needs Docker (`make up` first). Expect a refusal message from `deploy.sh`.

## Mistakes people make

- Forgetting quotes: `rm -rf $dir`. Here every expansion is quoted.
- Writing Bash-only features (`[[ ]]`, arrays) in an `sh` script.
- Letting a failed pipeline step go unnoticed. `set -e` stops the script.
- Passing secrets on a command line that others can see. The collector token is read from the environment.
- Trusting a time stamp sent by the caller. The collector sets it.

## Check yourself

1. What does `: "${X:?msg}"` do? *Stops the script with `msg` if `X` is unset.*
2. In `$("$@" 2>&1 >/dev/null)`, what is captured? *Only the command's stderr.*
3. Why does `deploy.sh` call `verify.sh` itself? *So the deploy path cannot be reached with an unsigned image.*
4. Why does the event body have no `ts`? *The collector's clock sets it, so nobody can edit a lead time.*
5. What does `|| true` do after the failed-event call? *Keeps a failure to record the event from replacing the real error.*

## Further reading

- POSIX shell language: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html
- `set` builtin: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html#tag_18_25
