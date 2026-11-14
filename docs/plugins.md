# Plugins

Plugins add things to Floorbit without changing its core: buttons that run code (actions), tiles on
the dashboard (widgets), read-only JSON (endpoints) and code that runs when something changes
(hooks). The design is borrowed from labdex (manifest, `Plugin` class, widgets as data) and Hubra
(`uses:`: a plugin can touch only the areas it lists).

## Turning plugins on

Settings > Plugins lists every plugin, what it may touch, and whether it is on. All plugins start
**off**. Turning one on or off is in the audit log. A plugin's settings are on the settings page,
in a section called *Plugin: <name>*. Secrets are write-only there, as everywhere.

The **Dashboard** (top bar of the floor plan, `/dashboard`) shows the tiles of the plugins that are
on, for anyone signed in whose role is allowed to see them.

Where plugins come from:

| Trust | Where | Notes |
| --- | --- | --- |
| Ships with Floorbit | `floorbit/builtin_plugins/` | Reviewed with Floorbit itself. |
| Development checkout | the folder in `FLOORBIT_DEV_PLUGINS` | For writing plugins. **Never set it in production**: the code runs inside Floorbit. |

Installing other plugins (signed releases that run in a locked-down process of their own, like
labdex's community plugins) comes in a later step. Until then, no outside code runs.

Which plugins are on, and each plugin's small private state, live in `plugins.json` next to
`data.json`, or wherever `PLUGINS_FILE` points (Compose: the `state` volume).

## Built in: HTTP check

Checks that web services answer (the LAN cache, the ticket shop, a game server's web panel) and
shows them as a status tile. Settings: the services (`Name=URL`, comma separated), a timeout, and
whether to verify TLS. Editors can run **Check now**; the tile checks again when its results are
older than a minute. Redirects are not followed, so a service that redirects shows its 3xx status.

## Writing a plugin

A plugin is a folder:

```
my-plugin/
  plugin.yaml
  plugin.py
```

```yaml
# plugin.yaml
id: my-plugin                 # lowercase letters, digits, dashes
name: My plugin
version: "0.1.0"
floorbit: ">=0.1,<2"          # the Floorbit versions it works with
description: One line about what it does.
uses: [settings, actions, widgets, endpoints, hooks, http, storage]   # only what you need
settings:
  - {key: url, label: URL, type: url}
  - {key: token, label: API token, type: secret}
  - {key: mode, type: select, options: [fast, safe], default: safe}
actions:
  - {id: sync, label: Sync now, role: editor, dashboard: true,     # role: editor or admin (default admin)
     params: [{key: dry_run, type: bool, default: true}]}
  - {id: wipe, role: admin, danger: true}                           # asks before it runs
widgets:
  - {id: summary, label: Summary, size: wide, refresh: 60}          # role: viewer (default), editor or admin
endpoints:
  - {id: data, label: Raw data, role: editor}
hooks:
  - {events: [change], action: sync}                                # change, switch.status
```

```python
# plugin.py
from floorbit.plugins.base import Plugin as Base, PluginError

class Plugin(Base):
    def run_sync(self, params):
        api = self.ctx.http(self.settings['url'], headers={'Authorization': f"Bearer {self.settings['token']}"})
        items = api.get('/items').json()
        self.ctx.set_state('count', len(items))
        return {'message': f'{len(items)} items'}

    def run_wipe(self, params):
        raise PluginError('Not allowed today')        # shown to the person as is

    def widget_summary(self):
        return {'type': 'stat', 'value': self.ctx.state.get('count', 0), 'unit': 'items'}

    def endpoint_data(self, args):
        return {'count': self.ctx.state.get('count', 0)}

    def test(self):                                     # optional: the Test button
        return 'Connected'
```

### Areas (`uses:`)

| Area | Lets the plugin |
| --- | --- |
| `settings` | have settings (types: string, text, url, secret, bool, int, select, list) |
| `actions` | add actions, run with `POST /api/plugins/<id>/actions/<action>` |
| `widgets` | add dashboard tiles |
| `endpoints` | serve JSON at `GET /api/plugins/<id>/endpoints/<endpoint>` |
| `hooks` | run an action on `change` (any audited change: area, action, target, fields, user) or `switch.status` (a switch went offline or came back) |
| `http` | make outgoing requests with `self.ctx.http(...)` |
| `storage` | keep up to 64 KB of state with `self.ctx.set_state(key, value)` |

The loader refuses a plugin whose manifest uses an area it doesn't list, and code whose methods
don't match the manifest (a `run_x` with no action `x`, or an action with no `run_x`). A broken
plugin shows its error on Settings > Plugins and can't be turned on; it never stops Floorbit.

### What Floorbit does for you

- **Permissions:** actions need the role they name (editor or admin), widgets and endpoints need a
  signed-in account with their role. None of them is ever public, even with `AUTH_PUBLIC_READ` on.
  Changes posted from another site are refused, like every other change.
- **Audit:** every action run is logged with the plugin, the action, the account and the parameter
  *names*. Parameter checks happen before your code runs.
- **Settings from the environment:** each setting can also come from
  `FLOORBIT_PLUGIN_<ID>_<KEY>` (for example `FLOORBIT_PLUGIN_MY_PLUGIN_TOKEN`). A plugin can't pick
  another variable name, so it can't read `SECRET_KEY` or another integration's token that way.
- **Errors:** raise `PluginError("...")` for a message the person should see. Anything else is
  logged on Settings > Plugins > Log, and the person sees that the plugin failed.
- **HTTP:** `self.ctx.http()` sets a timeout (at most 60 s), verifies TLS unless the plugin's
  `verify_ssl` setting is off, and doesn't follow redirects.
- **Hooks** run in the background, so a slow plugin never slows a request.

### Widgets

Widgets are data; Floorbit draws them and never treats their text as HTML. Links must be paths on
this site.

| Type | Fields |
| --- | --- |
| `stat` | `value`, `unit`, `tone` (`ok`, `warn`, `err` or empty) |
| `status` | `items`: `label`, `state` (`up`, `down`, `warn`, `unknown`), `detail` |
| `list` | `items`: `label`, `value`, `tone` |
| `table` | `columns`: `key`, `label`; `rows` |
| `sparkline` | `points`, `value`, `unit`, `min`, `max` |

Every widget can also have `sub` (a line under it) and `link`.

### Developing

```sh
FLOORBIT_DEV_PLUGINS=~/src/floorbit-plugins flask --app app run
```

Each folder in there with a `plugin.yaml` loads as a development plugin. `tests/test_plugins.py`
shows how to test one with Floorbit's test client.
