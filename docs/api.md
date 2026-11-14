# The API

Everything the Floorbit pages show comes from a JSON API under `/api/`, and scripts and other tools
can use the same API: a scoreboard, a Discord bot, your own dashboard (#40). This page covers
signing in with a token, the version promise and how errors look. Each area's endpoints are listed
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
