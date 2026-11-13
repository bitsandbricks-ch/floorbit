# Sign-in

The editor and the settings page are behind a sign-in. Code: [`auth/`](../auth/).

## Who can do what

| Request | Signed out | Viewer | Editor | Admin |
| --- | --- | --- | --- | --- |
| `/` (floor plan editor) | redirected to `/login` | read-only | yes | yes |
| `GET /api/...` (switches, seats, status, live events) | yes, while `AUTH_PUBLIC_READ` is on | yes | yes | yes |
| Changes (`POST`, `PUT`, `PATCH`, `DELETE`) | 401 | 403 | yes | yes |
| `/api/checkins...`, `/checkins/history` (user, IP, MAC per seat) | 401 / login | 403 | yes | yes |
| `/settings`, `/settings/users`, `/api/settings`, `/api/users`, `/api/integrations...` | 401 / login | 403 | 403 | yes |
| `/login`, static files, `AUTH_PUBLIC_PATHS` (check-in page, kiosk view) | yes | yes | yes | yes |

Roles are in `auth/roles.py`. Each includes the ones below it. Accounts created before roles existed
count as admin. Viewers get the editor with its editing tools hidden.

Reads stay open by default so a kiosk screen or the check-in page can load the floor plan without an
account. Set `AUTH_PUBLIC_READ=false` to close them too; a kiosk then needs to be signed in.

A path in `AUTH_PUBLIC_PATHS` covers itself and everything below it (`/kiosk` covers `/kiosk/hall-a`,
not `/kioskadmin`). A single view can also be opened from code with `@public_endpoint` (from `auth`).

Signed-out API calls answer `401 {"error": "Sign in required", "login_url": "/login"}`;
`static/js/auth.js` sends the browser to the sign-in page when that happens and back afterwards.

## Accounts

Accounts are stored in `data.json` under `auth_users` (the file compose already mounts), with the
password as a werkzeug scrypt hash. Admins manage them on **Settings › Users** (`/settings/users`):
add, change role, reset password, remove. Or on the server:

```sh
docker compose exec lal-app flask users add mike          # asks for the password; first account is admin
docker compose exec lal-app flask users add helper1 --role viewer
docker compose exec lal-app flask users role helper1 editor
docker compose exec lal-app flask users passwd mike       # also signs out mike's sessions
docker compose exec lal-app flask users remove mike
docker compose exec lal-app flask users list
```

Outside Docker use `flask --app app users ...`.

For a fresh install, `AUTH_ADMIN_USER` and `AUTH_ADMIN_PASSWORD` create the first account on start
when there is none yet. They do nothing once an account exists, so you can remove them afterwards.

Accounts added without a role are editors. The last admin can't be demoted or removed, and admins
can't change their own role or remove themselves. A role change applies to open sessions at once; a
password reset signs that account out everywhere.

## Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `AUTH_ENABLED` | `true` | `false` turns sign-in off (everyone can edit, like before). |
| `SECRET_KEY` | generated | Signs the session cookie. Unset, a random key is generated once and kept in `data.json`. |
| `AUTH_ADMIN_USER`, `AUTH_ADMIN_PASSWORD` | empty | First account, created only when there are no accounts. |
| `AUTH_PUBLIC_READ` | `true` | Read-only `GET /api/...` requests work without signing in. |
| `AUTH_PUBLIC_PATHS` | `/checkin,/api/checkin,/kiosk` | Paths open to everyone, comma separated. |
| `AUTH_SESSION_HOURS` | `12` | How long a sign-in lasts. |
| `AUTH_COOKIE_SECURE` | `false` | `true` when the app is only reached over HTTPS. |
| `AUTH_TRUSTED_ORIGINS` | empty | Extra origins allowed to send changes, e.g. `https://lal.example.com` behind a proxy that rewrites `Host`. |

## Security notes

- Passwords: at least 8 characters, scrypt hashed. Unknown usernames take as long to reject as
  wrong passwords.
- Five failed attempts for one username from one address lock that pair for five minutes.
- The session cookie is `HttpOnly` and `SameSite=Lax`. Changes sent with an `Origin` header from
  another site are refused (403).
- A password change bumps the account's `session_version`, which signs out its other sessions.

## Adding SSO (OIDC) or Discord later

A login method is a provider in `auth/providers/`. Two kinds exist:

- `PasswordProvider`: the sign-in form's username and password are checked by
  `authenticate(username, password)`. `LocalProvider` is one; LDAP would be another.
- `RedirectProvider`: the sign-in page shows a "Sign in with ..." button. `start(callback_url, state)`
  returns the URL to send the browser to, and `finish(request, callback_url)` turns the callback into
  an `Identity(provider, subject, username, display_name, email)`.

The routes `/auth/<id>/start` and `/auth/<id>/callback`, the `state` check and the session are
already there. `Auth.resolve_identity` maps an identity to an account through its linked
`identities` (`users.link_identity("mike", "discord", "<discord user id>")`). A provider with
`auto_create_users = True` creates an account on first sign-in (with the provider's `default_role`,
viewer unless set); leave it off unless the provider
itself limits who gets in (for example only members of a Discord guild role).

An OIDC or Discord provider is then one class, registered in `init_auth` when its env vars are set
(`OIDC_ISSUER`, `OIDC_CLIENT_ID`, ... or `DISCORD_CLIENT_ID`, ...). The tests in
`tests/test_auth.py` run the whole redirect flow with a fake provider.
