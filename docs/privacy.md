# Privacy

ROS systems can expose sensitive information. This tool is designed so that you decide what leaves the machine.

## What is collected

Graph structure (node, topic, service, action names and types, QoS), TF frame names, lifecycle states,
controller names/states, `/diagnostics` statuses, recent WARN+ log text, host CPU/memory/disk and network
interface names/addresses, and these environment variables only: `ROS_DISTRO`, `ROS_DOMAIN_ID`,
`RMW_IMPLEMENTATION`, `ROS_LOCALHOST_ONLY`.

**Never collected:** other environment variables, file contents, parameter values, message payloads (camera
images, point clouds, joint values...), credentials. The one exception in spirit is `--watch-topic`: it subscribes to
the topics you name and keeps **only a message count** (raw subscription, payload bytes are discarded unread).

## When data is sent anywhere

Only when you pass `--provider <cloud>`. Rule-based runs and `--local` (loopback Ollama) send nothing off the
machine. Before a cloud send you see the sections and approximate size, and must confirm (or pass `--yes`).
`--dry-run` prints the exact system prompt and JSON payload without sending anything.

## Redaction

| Applied | Removes |
|---|---|
| Always (anything analysed or reported) | API keys (`sk-...`, `AIza...`, `ghp_...`, `AKIA...`), bearer tokens, `password/secret/token/api_key/credential = value`, PEM private keys; messages truncated to 300 chars |
| `--redact` (always for `.md` reports and `--github`) | IPv4 addresses, MAC addresses, e-mail addresses, hostname, current username, `/home/<user>` paths, diagnostic hardware IDs and values whose key looks like serial/password/token/key |

Placeholders are stable within a run (`<ip-1>`, `<ip-2>`). Node, topic and service names are **kept**, since a
diagnosis is impossible without them. If your names are themselves sensitive, do not use cloud providers.

Redaction is pattern-based and best effort: it will miss secrets that do not look like secrets. Read a report
before you post it publicly.

## Reports

`--output report.md` and `--github` produce redacted Markdown suitable for a GitHub issue. `--output x.json`
and `--format json` are redacted only with `--redact` (secrets are always scrubbed). The JSON includes the full
snapshot so it can be replayed with `--from-snapshot`.
