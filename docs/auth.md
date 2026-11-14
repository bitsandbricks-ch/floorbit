# Sign-in

The editor and the settings page are behind a sign-in. Code: [`auth/`](../auth/).

## Who can do what

Access is role based (RBAC). Every request needs one **permission**; an account's **role** is a
named set of permissions. The rules live in `auth/roles.py` (`RULES`): the first matching path
wins, any other read needs `floorplan.view`, and any other change needs `settings.manage`, so a new
route stays admin-only until someone gives it a rule.

| Permission | Allows |
| --- | --- |
| `floorplan.view` | See the floor plan, dashboards and live switch status |
| `floorplan.edit` | Change the floor plan and the inventory, run syncs |
| `seats.view` | See who sits where: nicks, IPs, MACs and check-ins |
| `seats.edit` | Change the seat mapping and check-ins |
| `incidents.work` | Work incidents assigned to their teams |
| `incidents.assign` | Assign incidents to any team |
| `ports.act` | Run port actions and show commands on switches ([commands.md](commands.md)) |
| `commands.change` | Run switch commands that change something, such as clearing counters |
| `configs.read` | Back up switch configs and read them and what changed ([configs.md](configs.md)) |
| `terminal.open` | Open a terminal on a switch in the browser ([terminal.md](terminal.md)) |
| `power.edit` | Change power boards and circuits, enter readings and trips ([power.md](power.md)) |
| `plugins.run` | Run plugin actions |
| `audit.read` | Read the audit log |
| `settings.manage` | Change settings, plugins and backups |
| `accounts.manage` | Manage accounts, roles and teams |

Built-in roles (they can't be changed):

| Role | Permissions |
| --- | --- |
| Admin | all |
| Lead | everything except `settings.manage` and `accounts.manage` |
| Tech | `floorplan.view`, `seats.view`, `incidents.work`, `ports.act` |
| Viewer | `floorplan.view` |
| Kiosk | `floorplan.view` (an account for a big screen; remove it to revoke it) |

Admins add their own roles on **Settings › Roles and teams** (`/settings/teams`), with any mix of
the permissions above. Custom roles are stored in `data.json` under `auth_roles`. A role still in
use can't be removed, and no change may leave nobody with `accounts.manage`.

| Request | Signed out | Needs |
| --- | --- | --- |
| `/` (floor plan editor) | redirected to `/login` | `floorplan.view`; editing tools need `floorplan.edit` |
| `GET /api/...` (switches, status, live events, `/api/seats/occupancy`) | yes, while `AUTH_PUBLIC_READ` is on | `floorplan.view` |
| `/api/seats/info`, `/api/seat-map`, `/api/checkins`, `/seat-mapping` (nicks, IPs, MACs) | 401 / login | `seats.view` (changes: `seats.edit`) |
| Floor plan, seat block and inventory changes | 401 | `floorplan.edit` |
| `/settings/audit`, `/api/settings/audit` | 401 / login | `audit.read` |
| `/settings/users`, `/settings/teams`, `/api/users`, `/api/roles`, `/api/teams` | 401 / login | `accounts.manage` |
| `/settings`, `/api/settings`, `/api/integrations...`, `/api/demo` | 401 / login | `settings.manage` |
| `/login`, static files, `AUTH_PUBLIC_PATHS` (check-in page, kiosk view) | yes | nothing |

A refused request answers `403` with `permission_needed`. Plugin actions and widgets name the
permission they need in their manifest (`permission:`; the older `role:` still works and maps to
`floorplan.view`, `plugins.run` or `settings.manage`).

Viewers, kiosks and signed-out screens see which seats are taken (`/api/seats/occupancy`), never
who sits there.

### Teams

Teams are a tree (Infra › Core, Access, Wi-Fi; Operations; Electrics to start with), stored under
`auth_teams`. An account can be in several teams, each with a role. A team role counts for that team
and every team below it, and only adds permissions *inside* those teams (for example working the
incidents routed to them, issue #11). Everything else is decided by the account's own role. Teams go
at most 5 levels deep.

### Upgrading

Accounts from before roles existed have no role stored and count as admin, so nobody is locked out.
The old `editor` role is now **Lead** (stored values are read as `lead`), which now also reads the
audit log. Viewers lost access to `/api/seats/info`; the kiosk view uses `/api/seats/occupancy`.

Reads stay open by default so a kiosk screen or the check-in page can load the floor plan without an
account. Set `AUTH_PUBLIC_READ=false` to close them too; a kiosk then needs to be signed in.

A path in `AUTH_PUBLIC_PATHS` covers itself and everything below it (`/kiosk` covers `/kiosk/hall-a`,
not `/kioskadmin`). A single view can also be opened from code with `@public_endpoint` (from `auth`).

Signed-out API calls answer `401 {"error": "Sign in required", "login_url": "/login"}`;
`static/js/auth.js` sends the browser to the sign-in page when that happens and back afterwards.

## Accounts

Accounts are stored in `data.json` under `auth_users` (in the compose file's state volume), with the
password as a werkzeug scrypt hash. Admins manage them on **Settings › Users** (`/settings/users`):
add, change role, reset password, remove. Or on the server:

```sh
docker compose exec floorbit flask users add mike          # asks for the password; first account is admin
docker compose exec floorbit flask users add helper1 --role viewer
docker compose exec floorbit flask users role helper1 lead
docker compose exec floorbit flask users passwd mike       # also signs out mike's sessions
docker compose exec floorbit flask users remove mike
docker compose exec floorbit flask users list
```

Outside Docker use `flask --app app users ...`.

For a fresh install, `AUTH_ADMIN_USER` and `AUTH_ADMIN_PASSWORD` create the first account on start
when there is none yet. They do nothing once an account exists, so you can remove them afterwards.

Accounts added without a role are leads. The last account that can manage accounts can't be demoted or removed, and admins
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

## Sign in with Discord

A "Sign in with Discord" button appears on the sign-in page once a Discord application is set
up. Settings > Discord sign-in holds the values; each one can also come from an environment
variable.

1. Create an application at <https://discord.com/developers/applications>. Under OAuth2, add the
   redirect `https://<your Floorbit address>/auth/discord/callback`. Behind a reverse proxy, set
   **Public URL** (Settings > General, `PUBLIC_URL`) so Floorbit sends Discord that exact address.
2. Paste the application's **client ID** and **client secret** (`DISCORD_CLIENT_ID`,
   `DISCORD_CLIENT_SECRET`). The secret is write-only, like the other tokens, and never in a backup.

Who gets in depends on whether a server is set:

| Server ID (`DISCORD_GUILD_ID`) | Who can sign in |
| --- | --- |
| empty | Only accounts an admin linked to a Discord user. On the Users page, click **Link Discord** on an account and paste the person's Discord user ID (in Discord: Settings > Advanced > Developer mode, then right-click the person > Copy User ID). |
| set | Linked accounts, plus members of that Discord server. A member's first sign-in creates an account (no password) whose role comes from their server roles. |

Role mapping for server members, by Discord role ID (comma separated):

| Setting | Env var | Members with one of these roles become |
| --- | --- | --- |
| Admin roles | `DISCORD_ADMIN_ROLES` | admin |
| Editor roles | `DISCORD_EDITOR_ROLES` | lead |
| Viewer roles | `DISCORD_VIEWER_ROLES` | viewer |

The highest matching role wins. With all three lists empty, every member of the server can sign in
as a viewer; with any list set, members without one of those roles are refused.

- The Discord role sets the role of a new account only. Change it later on the Users page.
- An account Discord created stops working when its owner leaves the server or loses every listed
  role (checked on each sign-in; a session that is already open lasts until it expires, see
  `AUTH_SESSION_HOURS`). Remove the account on the Users page to end it at once.
- Accounts an admin linked by hand don't need the server or a role.
- Floorbit asks Discord for `identify`, plus `guilds.members.read` when a server is set. It keeps the
  Discord user ID on the account and nothing else (no token, no email).
- Discord sign-ins and refused ones are in the audit log, under *sign-in*.

## Sign in with OpenID Connect

Admins add OIDC providers (Authentik, Keycloak, Microsoft Entra ID, Google, ...) under
**Settings › Sign-in providers** (`/settings/sign-in`, needs `settings.manage`). Each one gets its own
"Sign in with <name>" button next to local accounts and Discord. Code: [`auth/oidc.py`](../auth/oidc.py).

Per provider:

| Setting | |
| --- | --- |
| ID | Lowercase letters and digits. It is part of the redirect URL and of the secret's variable name. |
| Name | The button text. |
| Issuer URL | Endpoints and signing keys come from `<issuer>/.well-known/openid-configuration`, which must name the same issuer. https only, except `localhost`. |
| Client ID | From the identity provider. |
| Scopes | Default `openid profile email`; must include `openid`. Add `groups` (or what your provider calls it) for role mapping. |
| Role claim | Default `groups`. If the ID token doesn't carry it, Floorbit asks the userinfo endpoint. |
| Who gets in | Claim values and the role each gives. Several matches: the role with the most permissions wins. |

Register this redirect URL at the identity provider (the settings page shows it):
`<PUBLIC_URL>/auth/oidc-<id>/callback`.

**The client secret** is never stored in `data.json` or shown in Settings. Set
`OIDC_<ID>_CLIENT_SECRET`, or point `OIDC_<ID>_CLIENT_SECRET_FILE` at a Docker secret:

```yaml
services:
  app:
    environment:
      OIDC_AUTHENTIK_CLIENT_SECRET_FILE: /run/secrets/oidc_authentik
    secrets: [oidc_authentik]
secrets:
  oidc_authentik:
    file: ./secrets/oidc_authentik.txt
```

The button only appears once the secret is there. **Test** on the settings page checks discovery,
the keys and PKCE support.

**Who can sign in:**

- Without any role rule, only accounts an admin linked on **Settings › Users** (Link sign-in, with
  the person's `sub` at the provider).
- With rules, a first sign-in from someone with a mapped value creates an account without a
  password. That account is refused once the person has no mapped value any more. Accounts an
  admin linked by hand are trusted as they are.
- Local accounts always keep working, so an admin can sign in while the identity provider is down.

**How it is checked:** authorization code flow with PKCE (S256), `state` and `nonce`. The ID token's
signature is checked against the issuer's published keys (asymmetric algorithms only, never `none`
or HS256), plus `iss`, `aud` (and `azp` when there are several audiences), `exp`, `iat` and the
`nonce`, with 60 seconds of clock skew. Keys are cached for an hour and fetched again when a token
names a key we don't know. Every sign-in and refusal goes to the audit log with the provider.

## Adding another login method

A login method is a provider in `auth/providers/`. Two kinds exist:

- `PasswordProvider`: the sign-in form's username and password are checked by
  `authenticate(username, password)`. `LocalProvider` is one; LDAP would be another.
- `RedirectProvider`: the sign-in page shows a "Sign in with ..." button. `start(callback_url, state)`
  returns the URL to send the browser to, and `finish(request, callback_url)` turns the callback into
  an `Identity(provider, subject, username, display_name, email)`. `DiscordProvider` is one.

The routes `/auth/<id>/start` and `/auth/<id>/callback`, the `state` check and the session are
shared. `Auth.resolve_identity` maps an identity to an account through its linked `identities`
(`users.link_identity("mike", "discord", "<discord user id>")`) and calls the provider's
`check_existing(user, identity)` on every sign-in. A provider with `auto_create_users = True`
creates an account on first sign-in with the role from `new_user_role(identity)`; leave it off
unless the provider itself limits who gets in (as Discord does with a server). The tests in
`tests/test_auth.py` run the redirect flow with a fake provider, and `tests/test_discord_login.py`
runs Discord's against a fake Discord API.
