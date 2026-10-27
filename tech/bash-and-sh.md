# Shell scripts (`sh`)

## What it is

A **terminal** is a window in which you type text commands. The program that reads what you type and starts other programs for you is called a **shell**. `sh` is the oldest and most portable shell language: every Unix-like computer (Linux, macOS, the little Linux inside a container) understands it. **Bash** is a larger shell that adds features; this repository's scripts avoid those features on purpose, so they begin with `#!/bin/sh`.

A **shell script** is a text file of shell commands that the shell runs from top to bottom. Its first line, `#!/bin/sh`, is called the **shebang**: it tells the operating system "run this file with the program `/bin/sh`". For the file to be runnable you also set its *execute permission* (`chmod +x file`). A line starting with `#` anywhere else is a **comment**: the shell ignores it and it is there for people.

You will meet these ideas in every script below, so here they are in one place:

- **Process.** Every command you run becomes a *process*: one running copy of a program. When it ends it hands back an **exit status**, a number from 0 to 255. By convention `0` means "it worked" and any other number means "it failed". The shell remembers the last status in `$?`.
- **Streams.** A process has three channels: **standard input** (number 0, what it reads), **standard output** (number 1, what it prints normally) and **standard error** (number 2, where it prints complaints). `command > file` sends standard output to a file; `command 2> file` sends the errors; `2>&1` means "send errors to wherever output goes"; `>&2` on a command means "send its output to the error channel"; `/dev/null` is a place where anything written is thrown away. `<` feeds a file to a command's input.
- **Pipe.** `a | b` connects the output of `a` to the input of `b`; both run at the same time.
- **Variable.** A named piece of text. `name=value` sets it (no spaces around `=`). `$name` or `${name}` reads it. Always put quotes around a read, as in `"$name"`: without quotes the shell splits the text at spaces and expands wildcard characters, which causes bugs when a name contains a space.
- **Command substitution.** `$(command)` runs the command and is replaced by what it printed.
- **Arguments.** `$1`, `$2`, ... are the words given to the script. `"$@"` means "all of them, each kept as one word". `$0` is the script's own path.
- **Defaults and checks.** `${name:-default}` means "the variable, or `default` if it is unset or empty". `${name:?message}` means "the variable, or stop with `message` if it is unset".
- **Tests.** `[ ... ]` is a command (it is called `test`) that exits 0 if the condition inside is true. `[ -z "$x" ]` is true if `x` is empty; `[ -n "$x" ]` if it is not empty; `[ a = b ]` if the two texts are equal; `[ "$i" -lt 5 ]` if the number `i` is less than 5. `!` in front reverses it. `if cmd; then ...; elif ...; else ...; fi` runs a command and branches on its exit status.
- **Lists.** `a && b` runs `b` only if `a` succeeded. `a || b` runs `b` only if `a` failed. `a; b` runs both. `{ a; b; }` groups commands.
- **Loops.** `while cmd; do ...; done` repeats while the command succeeds; `for x in a b c; do ...; done` repeats once for each item.
- **Functions.** `name() { ...; }` defines a reusable block of commands; `return N` leaves it with status N.
- **`set -eu`.** `set -e` makes the script stop at the first command that fails; `set -u` makes using an unset variable an error.
- **`trap`.** `trap 'commands' EXIT` runs the commands when the script ends, however it ends: a clean-up that cannot be forgotten.

## Why this repository uses it

A service generated from the golden path must be able to run its own release steps on a plain CI machine or a laptop with nothing installed but `make`, `git`, `docker`, `curl` and `cosign`. Three small scripts do the glue between those programs: **verify** an image, **deploy** it (only after verifying) and **emit** an event to the platform's collector. They are part of the template, so every generated service gets the same three, and the platform's audit checks they stay. They run in plain `sh` for the same reason: no Bash is needed.

## Where it appears

| File | Role |
|---|---|
| `template/scripts/verify.sh` | Refuses any image that is not signed and attested by this repository's pipeline. |
| `template/scripts/deploy.sh` | Verifies, then starts the image with Compose; on a refusal records a `failed` event. |
| `template/scripts/emit-event.sh` | Sends one event (`commit`, `deploy`, `failed`, `recovered`) to the collector with `curl`. |
| `Makefile` (both) | Every recipe line is a shell command ([make.md](make.md)). |
| `template/.github/workflows/ci.yml` | `run:` lines are shell snippets on the CI machine ([github-actions.md](github-actions.md)). |

## How it works underneath

When you type a command, the shell: (1) reads the line, (2) performs **expansions** (replaces `$variables`, `$(...)`, and wildcards such as `*.sql`), (3) finds the program (looking through the folders listed in the `PATH` variable), (4) starts it as a new process with the arguments, (5) waits for it to end and records its exit status. A script is that, repeated line by line, with `if`/`while` deciding which lines run.

`mktemp -d` creates a new empty folder with an unpredictable name in the system's temporary area. `eval` runs a string as shell code after expanding it. `read -r a b c` reads a line from standard input and splits it into three variables (`-r` stops backslashes being treated specially). `case value in pattern) ... ;; esac` compares a value with patterns, like a tidier `if`. `printf 'format' args` prints text exactly (unlike `echo`, it never treats the text as options). `grep` searches text for a pattern; `sed` edits text as it flows past; `head -3` keeps the first three lines; `cut`, `sort`, `tee -a file` (copy output to a file and to the screen, appending) are small tools for reshaping text.

## Walkthrough of this repository's use

All three scripts, line by line, then the shell lines in the Makefiles and the workflow.

### `template/scripts/verify.sh`: "is this image ours?"

```sh
#!/bin/sh
# Refuse anything that is not signed and attested by this repository's pipeline. Used by `make verify` and by
# scripts/deploy.sh, so the deploy path cannot be reached with an unsigned image.
#   usage: verify.sh IMAGE@sha256:...
# CI uses keyless verification (the identity is this repository's workflow); a local run uses COSIGN_PUBLIC_KEY.
set -eu
image=$1
```

- **Lines 2 to 5** are comments: refuse anything not signed and attested by this repository's pipeline; used by `make verify` and by `deploy.sh`, so the deploy path cannot be reached with an unsigned image. **Line 4** gives the usage: `verify.sh IMAGE@sha256:...`. **Line 5**: CI uses *keyless* verification (the identity is this repository's workflow); a local run uses a public key file in `COSIGN_PUBLIC_KEY`. (Both are explained in [cosign.md](cosign.md).)
- **Line 6**: `set -eu`. **Line 7**: `image=$1` stores the first argument, which is always a reference by **digest** (`registry/name@sha256:...`), never by tag.

```sh
# cosign writes its report to standard error; it is shown only when a check fails.
quiet() {
  if ! output=$("$@" 2>&1 >/dev/null); then
    printf '%s\n' "$output" >&2
    exit 1
  fi
}
```

- **Line 8** is a comment: cosign writes its report to standard error and it is shown only when a check fails.
- **Lines 9 to 14**: the function `quiet`. `"$@"` is the command that was passed to it. `output=$("$@" 2>&1 >/dev/null)` runs it and captures what it prints. The redirections are read left to right: `2>&1` sends **standard error** to where standard output currently points (the capture), and *then* `>/dev/null` sends standard output to nowhere. So `output` holds only the command's error channel, which is where cosign writes. `if ! output=$(...); then` is true when the command **failed** (the `!` reverses the status); the body prints the saved text to standard error (`>&2`) and `exit 1` stops the script. When the command succeeds, nothing is printed.

```sh
if [ -n "${COSIGN_PUBLIC_KEY:-}" ]; then
  quiet cosign verify --timeout=15m --key "$COSIGN_PUBLIC_KEY" --insecure-ignore-tlog=true "$image"
  quiet cosign verify-attestation --timeout=15m --key "$COSIGN_PUBLIC_KEY" --type custom --insecure-ignore-tlog=true "$image"
else
```

- **Line 15**: `if [ -n "${COSIGN_PUBLIC_KEY:-}" ]; then` is the local mode: `-n` tests that the text is not empty; the `:-` default stops `set -u` complaining when the variable is unset.
- **Lines 16 and 17**: `quiet cosign verify --timeout=15m --key "$COSIGN_PUBLIC_KEY" --insecure-ignore-tlog=true "$image"` checks the image's **signature** with the public key, and `quiet cosign verify-attestation ... --type custom ...` checks the attached **provenance statement**. `--timeout=15m` replaces cosign's three-minute default (a busy machine can need longer). `--insecure-ignore-tlog=true` skips the check against the public transparency log, because the local demo never uploaded to it; the flag's name warns it is for a demo only.

```sh
else
  : "${GITHUB_REPOSITORY:?set GITHUB_REPOSITORY or COSIGN_PUBLIC_KEY}"
  identity="^https://github.com/${GITHUB_REPOSITORY}/.github/workflows/ci.yml@.*$"
  issuer="https://token.actions.githubusercontent.com"
  quiet cosign verify --timeout=15m --certificate-identity-regexp "$identity" --certificate-oidc-issuer "$issuer" "$image"
  quiet cosign verify-attestation --timeout=15m --type custom --certificate-identity-regexp "$identity" --certificate-oidc-issuer "$issuer" "$image"
fi
echo "verified: $image"
```

- **Line 18**: `else`: CI mode. **Line 19**: `: "${GITHUB_REPOSITORY:?set GITHUB_REPOSITORY or COSIGN_PUBLIC_KEY}"`: the `:` command does nothing; the `${NAME:?message}` expansion stops the script with the message when the variable is unset. This is the idiom for "this must be set".
- **Line 20**: `identity="^https://github.com/${GITHUB_REPOSITORY}/.github/workflows/ci.yml@.*$"` is a regular-expression pattern for the address of *this repository's `ci.yml` workflow*. **Line 21**: `issuer="https://token.actions.githubusercontent.com"` names GitHub's identity service.
- **Lines 22 and 23**: `cosign verify --certificate-identity-regexp "$identity" --certificate-oidc-issuer "$issuer" "$image"` accepts a signature only if its certificate names that workflow and was issued by GitHub's identity service; `verify-attestation` does the same for the provenance. A signature made by another repository, or another workflow file, fails.
- **Line 25**: `echo "verified: $image"` prints only if every check above passed (`set -e` stops the script otherwise).

### `template/scripts/deploy.sh`: deploy only what verifies

```sh
#!/bin/sh
# Deploy a digest, but only after it verifies. A failed verification is recorded as a failed deployment and nothing runs.
#   usage: deploy.sh NAME IMAGE@sha256:... DEPLOYMENT_ID COMMITS   (COMMITS: ids joined by +)
set -eu
name=$1
image=$2
deployment=$3
commits=$4
here=$(cd "$(dirname "$0")/.." && pwd)

if ! "$here/scripts/verify.sh" "$image"; then
  echo "deploy refused: $image does not verify" >&2
  "$here/scripts/emit-event.sh" failed "$deployment" signature || true
  exit 1
fi
IMAGE_REF="$image" docker compose -p "$name-production" -f "$here/deploy/compose.yaml" up -d --wait
"$here/scripts/emit-event.sh" deploy "$deployment:$commits"
echo "deployed: $image as $name-production"
```

- **Lines 1 to 3**: comments. Usage: `deploy.sh NAME IMAGE@sha256:... DEPLOYMENT_ID COMMITS` (the commits joined by `+`). A failed verification is recorded as a failed deployment and nothing runs.
- **Lines 5 to 8**: four arguments into four variables: `name`, `image`, `deployment`, `commits`.
- **Line 9**: `here=$(cd "$(dirname "$0")/.." && pwd)`: `$0` is this script's path; `dirname` removes the file name; `/..` goes up one folder; `cd` there and `pwd` prints the absolute path. So `here` is the generated service's folder wherever the script is started from.
- **Lines 11 to 15**: `if ! "$here/scripts/verify.sh" "$image"; then` runs the verification script; it is true when verification **failed**. The body prints `deploy refused: ... does not verify` to standard error, runs `emit-event.sh failed "$deployment" signature || true` to record a failed deployment with the reason `signature` (the `|| true` means a failure to *record* the event does not hide the real problem), and exits 1.
- **Line 16**: `IMAGE_REF="$image" docker compose -p "$name-production" -f "$here/deploy/compose.yaml" up -d --wait`. A variable assignment in front of a command sets it for that command only. `-p` names the Compose project, so the containers are called `orders-production-...` and `make down` can remove them. `-f` names the file. `up -d --wait` starts the container in the background and waits until its health check passes ([docker-compose.md](docker-compose.md)).
- **Lines 17 and 18**: record a `deploy` event whose ref is `deployment:commits`, and print `deployed: ... as NAME-production`.

### `template/scripts/emit-event.sh`: tell the platform what happened

```sh
#!/bin/sh
# Record one delivery event (commit, deploy, failed, recovered) at the platform's collector.
#   usage: emit-event.sh TYPE REF [DETAIL]
# The collector's address is EVENTS_URL. The credential is EVENTS_TOKEN (a local run) or, in CI, a short-lived
# identity token requested from the CI system for the audience "goldenpath-events": no stored secret.
set -eu
type=$1
ref=$2
detail=${3:-}
: "${EVENTS_URL:?set EVENTS_URL}"
: "${SERVICE_NAME:?set SERVICE_NAME}"
token=${EVENTS_TOKEN:-}
```

- **Lines 2 to 5** are comments. Usage: `emit-event.sh TYPE REF [DETAIL]`. The collector's address is `EVENTS_URL`. The credential is `EVENTS_TOKEN` (local) or, in CI, a short-lived identity token requested from the CI system for the audience `goldenpath-events`: no stored secret ([oidc-identity-tokens.md](oidc-identity-tokens.md)).
- **Lines 7 to 9**: `type=$1`, `ref=$2`, `detail=${3:-}` (the third argument, or empty). **Lines 10 and 11**: `: "${EVENTS_URL:?set EVENTS_URL}"` and the same for `SERVICE_NAME`: the script stops with a message if either is unset. **Line 12**: `token=${EVENTS_TOKEN:-}`.

```sh
if [ -z "$token" ] && [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then
  token=$(curl -fsS -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=goldenpath-events" | python3 -c 'import json,sys; print(json.load(sys.stdin)["value"])')
fi
payload=$(printf '{"service": "%s", "type": "%s", "ref": "%s", "detail": "%s"}' "$SERVICE_NAME" "$type" "$ref" "$detail")
curl -fsS -X POST "$EVENTS_URL/events" -H "Content-Type: application/json" -H "Authorization: Bearer $token" -d "$payload" >/dev/null
echo "event: $type $ref"
```

- **Lines 13 to 15**: `if [ -z "$token" ] && [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then`: if no static token is given (`-z` is "empty") and the job can ask GitHub for an identity token, then `token=$(curl -fsS -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=goldenpath-events" | python3 -c '...')`. `curl` calls GitHub's token endpoint ([curl.md](curl.md)); its reply is JSON; a one-line `python3 -c 'import json,sys; print(json.load(sys.stdin)["value"])'` reads standard input and prints the field `value`. The pipe `|` sends curl's output to Python's input. `$(...)` stores the result.
- **Line 16**: `payload=$(printf '{"service": "%s", "type": "%s", "ref": "%s", "detail": "%s"}' "$SERVICE_NAME" "$type" "$ref" "$detail")` builds a small JSON text; `printf` replaces each `%s` with the next argument. The event has **no timestamp**: the collector adds its own, so a lead time cannot be edited.
- **Line 17**: `curl -fsS -X POST "$EVENTS_URL/events" -H "Content-Type: application/json" -H "Authorization: Bearer $token" -d "$payload" >/dev/null`. `-f` makes curl exit with an error on HTTP error statuses (so `set -e` stops the script); `-s` silent; `-S` still show errors; `-X POST` the HTTP method; `-H` adds a header; `-d` the request body; `>/dev/null` discards the reply. **Line 18**: `echo "event: $type $ref"`.

### Shell lines in the Makefiles

- Root `Makefile`: `help`'s `grep`/`sed`/`sort` pipeline; the `for pair in orders:team-orders ...` loop in `demo-services` with the parameter expansions `${pair%%:*}` (remove everything from the first `:`: the service) and `${pair##*:}` (remove everything up to the last `:`: the team); the `collector` target's `kill -0 $(cat .local/collector.pid)` (test that a process exists), `nohup ... &` (run in the background, immune to the terminal closing), `echo $$! > file` (save the background process's id) and the `for i in $(seq 1 40)` loop with `curl -fsS ... && break`. Each is explained in [make.md](make.md).
- `template/Makefile`: `docker push ... | sed -n 's/.*digest: \(sha256:[0-9a-f]*\).*/\1/p' | tail -1 > .build/digest` (cut the digest out of the push output), `test -s FILE || { ...; exit 1; }` (fail if the file is empty), and the `printf` that writes the provenance JSON. Explained in [make.md](make.md) and [json.md](json.md).
- `template/.github/workflows/ci.yml`: `scripts/emit-event.sh commit "$(git rev-parse --short HEAD)"` and `make deploy COMMITS="$(git rev-parse --short HEAD)" DEPLOYMENT="${{ github.run_id }}"` ([github-actions.md](github-actions.md)).

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
