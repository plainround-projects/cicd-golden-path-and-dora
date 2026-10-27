# curl

## What it is

Programs on different computers talk over a network. The most common way is **HTTP**, the language of the web. In HTTP a **client** sends a **request** and a **server** sends back a **response**. A request has a **method** (`GET` to read, `POST` to send something new), an **address path** (`/events`), **headers** (lines of `Name: value`) and sometimes a **body** (the data). A response has a **status code**: 2xx means success, 4xx means the client did something wrong (401 means "you did not say who you are", 413 "too large"), 5xx means the server had a problem (503 "try again later").

**curl** is a command-line program that makes such requests. You give it an address; it connects, sends the request, prints the reply and ends. It is installed on macOS and on nearly every Linux image, which is why shell scripts use it.

## Why this repository uses it

A pipeline step written in plain `sh` needs to talk to two HTTP services: the platform's **event collector** (to record `commit`, `deploy`, `failed`, `recovered`) and GitHub's **identity-token endpoint** ([oidc-identity-tokens.md](oidc-identity-tokens.md)). `curl` does both in one line, with nothing but the shell needed on the runner.

## Where it appears

| Path | Use |
|---|---|
| `template/scripts/emit-event.sh` | The token request (line 14) and the event `POST` (line 17). |
| `Makefile` (root) lines 47 and 48 | `curl -fsS http://127.0.0.1:$(COLLECTOR_PORT)/healthz` to wait for the collector and show that it is up. |
| `docker-compose.yml` | The registry's health check uses `wget` instead (curl is not in that image). |

## How it works underneath

curl opens a network connection to the host and port in the address, writes the request as text, reads the reply, prints the body and exits. Its **exit status** is 0 if the transfer worked. With the option `-f`, an HTTP error status (400 and above) also gives a non-zero exit status (22); without `-f`, curl prints an error page and exits 0 as if all were well.

## Walkthrough of this repository's use

### Sending an event: `emit-event.sh`

```sh
payload=$(printf '{"service": "%s", "type": "%s", "ref": "%s", "detail": "%s"}' "$SERVICE_NAME" "$type" "$ref" "$detail")
curl -fsS -X POST "$EVENTS_URL/events" -H "Content-Type: application/json" -H "Authorization: Bearer $token" -d "$payload" >/dev/null
echo "event: $type $ref"
```

`curl -fsS -X POST "$EVENTS_URL/events" -H "Content-Type: application/json" -H "Authorization: Bearer $token" -d "$payload" >/dev/null`, option by option:

- `-f` ("fail"): exit non-zero on an HTTP error status, so `set -e` stops the script instead of a failed event being silently lost.
- `-s` ("silent"): no progress meter. `-S` ("show error"): with `-s`, still print an error message if it fails. They are written together as `-fsS`.
- `-X POST`: the method. (With `-d`, curl chooses POST anyway; the flag makes it explicit.)
- `"$EVENTS_URL/events"`: the address: the collector's base URL from the environment plus the path `/events`.
- `-H "Content-Type: application/json"`: a header telling the server the body is JSON. `-H "Authorization: Bearer $token"`: a header carrying the token; "Bearer" means "whoever bears this token is allowed" ([http-server.md](http-server.md)).
- `-d "$payload"`: the request body (the JSON built by `printf` on the line above). The double quotes keep it as one word.
- `>/dev/null`: throw the server's reply away; the script prints its own line.

The collector answers `202` (accepted), `400` (a bad event), `401` (missing or wrong token), `413` (body too large) or `503` (its store is down; try again).

### Asking for an identity token

```sh
if [ -z "$token" ] && [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then
  token=$(curl -fsS -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=goldenpath-events" | python3 -c 'import json,sys; print(json.load(sys.stdin)["value"])')
fi
```

`token=$(curl -fsS -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=goldenpath-events" | python3 -c '...')`: a `GET` request (the default) to GitHub's token address, with a header proving the job may ask, and `&audience=goldenpath-events` added to the address as a query parameter. The reply is JSON; the pipe `|` sends it to a one-line Python program that prints the `value` field. `$(...)` stores the result in `token`.

### Waiting for the collector: the root `Makefile`

```make
collector: ## start the event collector in the background (logs in .local/logs)
	@if [ -f .local/collector.pid ] && kill -0 $$(cat .local/collector.pid) 2>/dev/null; then echo "collector already running"; else \
	  nohup $(VENV)/bin/goldenpath collector > .local/logs/collector.log 2>&1 & echo $$! > .local/collector.pid; \
	  for i in $$(seq 1 40); do curl -fsS http://127.0.0.1:$(COLLECTOR_PORT)/healthz >/dev/null 2>&1 && break; sleep 0.5; done; \
	  curl -fsS http://127.0.0.1:$(COLLECTOR_PORT)/healthz && echo " collector up on port $(COLLECTOR_PORT)"; fi
```

`for i in $$(seq 1 40); do curl -fsS http://127.0.0.1:$(COLLECTOR_PORT)/healthz >/dev/null 2>&1 && break; sleep 0.5; done` asks the collector's health address up to 40 times (`seq 1 40` counts from 1 to 40), half a second apart. `>/dev/null 2>&1` throws away both the output and the errors; `&& break` leaves the loop on the first success. After the loop a final `curl -fsS .../healthz && echo " collector up on port ..."` prints the answer `{"status": "ok"}`. `$$` is how a Makefile writes a single `$` for the shell ([make.md](make.md)).

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
