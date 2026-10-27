# curl

## What it is

`curl` is a command-line program that makes network requests, most often HTTP. You give it a URL, it connects, sends a request and prints the reply. It is installed on macOS and on nearly every Linux image, which is why shell scripts use it.

## Why this repository uses it

A pipeline step that runs in plain `sh` needs to talk to two HTTP services: the platform's **event collector** (to record `commit`, `deploy`, `failed`, `recovered`) and GitHub's **identity-token endpoint**. `curl` does both in one line, with no Python needed on the runner.

## Where it appears

| Path | Use |
|---|---|
| `template/scripts/emit-event.sh` | `curl -fsS -X POST "$EVENTS_URL/events" ...` and the token request. |
| `Makefile` (root) | `curl -fsS http://127.0.0.1:$(COLLECTOR_PORT)/healthz` to wait for the collector. |
| `docker-compose.yml` | The registry's health check uses `wget` (curl is not in that image). |

## How it works underneath

curl opens a TCP connection to the host and port, sends an HTTP request (a method, a path, headers, an optional body), reads the status line and body, prints the body, and exits. The **exit code** is 0 if the transfer worked; with `-f` it is 22 for an HTTP error status (400 and above), and other codes mean the connection failed.

## Walkthrough of this repository's use

```sh
curl -fsS -X POST "$EVENTS_URL/events" -H "Content-Type: application/json" -H "Authorization: Bearer $token" -d "$payload" >/dev/null
```

| Flag | Meaning |
|---|---|
| `-f` | Fail silently on HTTP errors: exit non-zero for 4xx and 5xx instead of printing the error page as if it were fine. With `set -e` this stops the script. |
| `-s` | Silent: no progress meter. |
| `-S` | With `-s`, still show an error message when it fails. |
| `-X POST` | The HTTP method. (With `-d`, curl already chooses POST; the flag makes it explicit.) |
| `-H "Name: value"` | Add a header. `Content-Type` says the body is JSON. `Authorization: Bearer ...` carries the token. |
| `-d "$payload"` | The request body. |
| `>/dev/null` | Throw the reply away; the script prints its own line. |

The collector answers `202 Accepted`, `400` (a bad event), `401` (no or wrong token), `413` (body too large) or `503` (the store is down, try again) ([http-server.md](http-server.md)).

```make
for i in $$(seq 1 40); do curl -fsS http://127.0.0.1:$(COLLECTOR_PORT)/healthz >/dev/null 2>&1 && break; sleep 0.5; done; \
```
A **readiness loop**: try up to 40 times, 0.5 seconds apart; `&& break` leaves the loop on the first success.

```sh
token=$(curl -fsS -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=goldenpath-events" | python3 -c '...')
```
Ask GitHub for an identity token and extract the `value` field ([oidc-identity-tokens.md](oidc-identity-tokens.md)).

## Try it yourself

```bash
curl --version | head -1
```

```bash
make up
curl -fsS http://127.0.0.1:55442/healthz
```
Expect `{"status": "ok"}`.

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:55442/events -d '{}'
```
Expect `401`: no bearer token.

```bash
set -a; . ./.env; set +a
curl -s -w "\n%{http_code}\n" -X POST http://127.0.0.1:55442/events -H "Authorization: Bearer $COLLECTOR_TOKEN" -d '{"service":"x"}'
```
Expect a `400` reply that says an event needs a type, service and ref.

## Mistakes people make

- Forgetting `-f`, so a `500` page looks like success.
- Putting the token on the command line in a shared shell history. Here it is read from an environment variable.
- Not quoting `$payload`.
- No timeout on a call that can hang. In scripts use `--max-time`.

## Check yourself

1. What does `-f` change? *HTTP errors make curl exit non-zero.*
2. What does `-sS` do together? *Silent, but still shows errors.*
3. What status does the collector return for a missing token? *401.*
4. Why is there a loop around the health request? *The collector needs a moment to start.*
5. Why `-H "Authorization: Bearer ..."`? *The collector refuses writes without the token.*

## Further reading

- curl manual: https://curl.se/docs/manpage.html
- Exit codes: https://curl.se/docs/manpage.html#EXIT
