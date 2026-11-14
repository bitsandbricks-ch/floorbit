# The API

Everything the Floorbit pages show comes from a JSON API under `/api/`, and scripts and other tools
can use the same API: a scoreboard, a Discord bot, your own dashboard (#40). This page covers
signing in with a token, the version promise, how errors look, and webhooks, which tell other tools
when something happens. Each area's endpoints are listed
at the top of its blueprint in `floorbit/blueprints/` and in the area's own doc.

## API tokens

An admin makes tokens under **Settings > API tokens**. A token has:

- **a name**, so you know what breaks when you revoke it;
- **a role**, like an account: the token can do what that role can (see [auth.md](auth.md));
- **read only** (on by default): the token can read, but every change answers 403;
- **an expiry** in days (1 to 365), or none.

Send it in the `Authorization` header:

```sh
curl -H "Authorization: Bearer fbt_..." https://floor.example.com/api/switches
```

- The token is shown once, when it is made. Floorbit keeps only its SHA-256 fingerprint, so a
  lost token can't be shown again: revoke it and make a new one.
- A token reaches `/api/...` only, never the pages. It never reaches accounts, roles, teams or the
  tokens themselves (`/api/users`, `/api/roles`, `/api/teams`, `/api/settings/api-tokens`), whatever
  its role. A leaked token can't make itself a new token or an account.
- Changes made with a token show up in the audit log as `token:<name>`. Making and revoking tokens
  is logged too. Each token shows when it was last used, to the minute.
- A wrong, expired or revoked token answers 401. A request with no token is treated like any visitor
  (with `AUTH_PUBLIC_READ` on, it may read the floor plan). Another `Authorization` scheme, like a
  reverse proxy's Basic auth, is left alone.
- Requests with a token skip the same-origin check that protects signed-in browsers from other
  sites: a browser can't send another site's `Authorization` header without CORS, which Floorbit
  never allows.

## Versions

`GET /api/version` answers `{"api": 1, "app": "<release>"}`, and every `/api/` answer carries the
header `Floorbit-API: 1`.

The API version goes up only when an existing answer changes in a way that breaks a client: a
field removed or renamed, or a field's meaning changed. New fields and new endpoints don't change
it, so a client should ignore fields it doesn't know. A breaking change is named in the changelog.

## Errors

Errors are JSON with an `error` text meant for people, and the usual status codes:

| Status | Means |
| --- | --- |
| 400 | The request is wrong; `error` says what to fix. |
| 401 | Sign in, or the token is wrong, expired or revoked. |
| 403 | The role (or a read-only token) can't do this; `permission_needed` names the permission. |
| 404 | No such thing, or its feature is turned off ([features.md](features.md)). |

## Where to start

| What | Endpoint | Doc |
| --- | --- | --- |
| Switches on the plan, with live status | `GET /api/switches` | [inventory.md](inventory.md) |
| Seat blocks | `GET /api/seat-blocks` | [halls.md](halls.md) |
| Find a player's seat | `GET /api/seats/find?q=` | [seat-mapping.md](seat-mapping.md) |
| Live numbers: seats online, bandwidth | `GET /api/stats` | [stats.md](stats.md) |
| Incidents | `GET`, `POST /api/incidents` | [incidents.md](incidents.md) |
| Service health | `GET /api/health` | [health.md](health.md) |
| The event report | `GET /api/report` | [report.md](report.md) |
| Live changes as they happen | `GET /api/events` (server-sent events) | [integrations.md](integrations.md) |

## Webhooks

An admin adds webhooks under **Settings > Webhooks**: a name, a URL and the events to send.
Floorbit POSTs each event as JSON as it happens:

```json
{"event": "switch.down", "delivery": "3f2a...", "ts": 1794652800.5,
 "data": {"id": "sw1", "name": "sw-a-01", "since": 1794652790.1, "down_for": null, "reason": "ping"}}
```

| Event | When | `data` |
| --- | --- | --- |
| `switch.down`, `switch.up` | The status monitor saw a switch go down or come back | `id`, `name`, `since`, `down_for` (seconds, on `switch.up`), `reason` |
| `monitoring.offline`, `monitoring.online` | The monitoring source stopped or started answering | `source`, `error`, `since`, `down_for` |
| `incident.opened` | An incident was filed on the board, from a seat (helpdesk) or by a power alert | `id`, `title`, `status`, `seat`, `switch_name`, `circuit_name`, `team`, `assignee`, `source`, `created_at`, `updated_at` |
| `incident.changed` | An incident was taken, assigned, noted or fixed | the same as `incident.opened` |
| `seat.checked_in` | A player checked in at a seat | `seat`, `moved_from` |
| `security.finding` | A security plugin reported something new | `id`, `kind`, `severity`, `switch`, `port`, `seat` |
| `power.alert` | A circuit reached its critical load or tripped | `id`, `name`, `board`, `phase`, `state`, `pct`, `rating_a`, `seats` (how many), `switches` |
| `forecast.alert` | The [bandwidth forecast](forecast.md) reaches the warning share of the line within the next hours (once per expected peak) | `t` (the hour), `bps`, `pct`, `capacity_bps` |
| `health.changed` | A service on the health wall changed state | `changes` |

Payloads never carry nicks, IPs or MACs: a check-in says which seat, not who. A feature that is
turned off ([features.md](features.md)) sends nothing. **Send a test** sends `ping`.

### Checking the signature

Each delivery has these headers:

- `Floorbit-Event`: the event's name.
- `Floorbit-Delivery`: an id that stays the same across retries, so a receiver can drop duplicates.
- `Floorbit-Signature`: `t=<unix time>,v1=<hex>`. The `<hex>` part is an HMAC-SHA256 over
  `<t>.<raw body>` with the webhook's secret.

The secret is shown once, when the webhook is added or given a new one. Check the signature, and
reject old `t` values so a recorded delivery can't be replayed:

```python
import hashlib, hmac, time

def valid(secret, header, body, max_age=300):
    parts = dict(p.split("=", 1) for p in header.split(","))
    want = hmac.new(secret.encode(), f"{parts['t']}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, parts["v1"]) and abs(time.time() - int(parts["t"])) < max_age
```

### Delivery

- **Success:** any 2xx answer within 5 seconds. Redirects are not followed.
- **Retries:** a failed delivery is tried again after 10 seconds, 1 minute and 5 minutes, then
  given up.
- **Recent deliveries:** the settings page shows each webhook's last 20 deliveries, kept in
  memory, so they are gone after a restart. Turning a webhook off stops it without losing its
  settings.
- **Backups:** webhooks live in `data.json` but never go into backups, because of their secrets.
- **Receivers on the LAN:** the URL may point inside the network, as receivers often do. Only an
  admin can set it.
