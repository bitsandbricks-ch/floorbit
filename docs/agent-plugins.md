# Agent plugins

A hosted Floorbit can't see the event network. The [local agent](agent.md) can: it runs in the
hall and connects out. **Agent plugins** are Floorbit [plugins](plugins.md) with a part that runs on
the agent: reading a log file on the LAN cache, listening for what switches and firewalls push,
asking a device only the hall can reach. The hosted Floorbit keeps the other part: settings,
pages, widgets, actions and storage.

## For whoever runs the hall

Nothing to install: the agent's image has every plugin that ships with Floorbit. Turn a plugin on
under **Settings > Plugins** in the hosted Floorbit and set it up there; every connected agent
starts its agent part within a minute (at once when you turn it on). Turning it off stops it on
the agents too.

The **Local agents** page shows, per agent, each plugin it runs: whether it is fine, a few of its
numbers and its last errors. The same numbers are on the agent's `/metrics`
(`floorbit_agent_plugin_<name>{plugin="<id>"}`, and `floorbit_agent_plugin_up`).
`python -m floorbit_agent check` asks every plugin's own check too.

### Plugins without an agent part

LibreNMS, NetBox, Pi-hole, AdGuard Home, the health checks and the other built-in plugins that
answer for the hall (monitoring, inventory, health, DNS, Wi-Fi, ports) also follow the hosted
Floorbit: what is on there is turned on in the agent, with the settings saved there. The agent
does the same for a plugin with an agent part that also answers for the hall (telemetry is the
agent's monitoring source). It keeps those settings in memory only, so tokens never land on its disk. Its own environment
(`LIBRENMS_URL`, `FLOORBIT_PLUGIN_<ID>_<KEY>`, `FLOORBIT_AGENT_PLUGINS`) no longer sets plugins: an
agent that still has them sends them once and the hosted Floorbit takes them over where nothing is
set up yet ([agent.md](agent.md#settings-come-from-floorbit)).

### Updates

A new Floorbit release brings new versions of its plugins to the agents too, without a new agent
image. The release workflow signs every built-in plugin with a key that only its signing job sees,
and the hosted Floorbit's image carries the signed bundles. The hosted side offers each agent the
bundles of the plugins it runs, and the agent installs one only when:

- it verifies against a public key built into the agent's image (`floorbit/keys/plugins/`).
  The hosted Floorbit holds no key, so a stolen hosted login can't make a bundle an agent takes;
- it is newer than what the agent runs: never a downgrade, not even when the hosted side goes back
  to an older release;
- it needs nothing the agent's image lacks (`agent_api`), and it wasn't rolled back on this agent.

The hall decides how, in `agent.env`:

```sh
FLOORBIT_AGENT_PLUGIN_UPDATES=auto       # the default: install at once
FLOORBIT_AGENT_PLUGIN_UPDATES=approve    # wait: docker compose exec agent python -m floorbit_agent plugins approve lancache
FLOORBIT_AGENT_PLUGIN_UPDATES=off        # keep the plugins the image came with
```

`python -m floorbit_agent plugins` lists what runs and what waits. A plugin that doesn't start on
its new version, or reports an error in its first five minutes, goes back to the version it ran
before, and that version is never tried on this agent again. Every install, rollback and refusal
is in the audit log, and the Local agents page shows the version each agent runs.

A bundle holds the plugin's own files only. A plugin that needs a newer agent core (a higher
`AGENT_API` in `floorbit/plugins/agent.py`) waits, shown as "needs a newer agent image", until the
agent's image is updated.

For the maintainer: `python scripts/agent_bundles.py keygen` makes the key pair. The public key goes
into `floorbit/keys/plugins/` (and from there into the next agent image), the private key into
the `FLOORBIT_PLUGIN_SIGNING_KEY` secret of the `plugin-signing` environment. Until both are there,
releases have no bundles and agents keep their image's plugins.

### Two agents in one hall

With VRRP (docs/vrrp.md in floorbit-agent), `self.ctx.primary()` says whether this agent holds the
first VIP. Only the primary should poll devices and log in to them, so no device is asked twice and
no login is tried twice; a standby keeps its listeners up and takes over when it becomes primary.
Without VRRP every agent is its own primary.

A plugin action (`ctx.agent_action` without naming an agent) goes to one agent per hall: its
group's primary, so two agents in one hall never both clear the cache or bounce a port. Without
VRRP, or while a group has no single primary, it goes to every connected agent as before.

### Actions need the hall's yes

Some plugins can change things in the hall (the LAN cache plugin can clear the cache). The hosted
Floorbit only offers that to the roles the plugin names, and writes it in the audit log, like
every plugin action. On top of that the agent runs an action only when its own machine allows it:

```sh
# agent.env
FLOORBIT_AGENT_ALLOW_ACTIONS=lancache.clear_cache    # or lancache.*, or * for every action
```

Without it the hosted side gets "This agent does not allow ...". That way a stolen hosted login
can read what the agent reports but can't change anything in the hall.

### Failed logins

When a device refuses a plugin's login, the agent stops trying that device with that credential:
no account lockouts, no alarms on the AAA or TACACS server. The Local agents page shows it in red
with **Clear, try again** (needs the *run plugins* permission), the audit log has it, and the
device's own page shows it. Editing the credential counts as clearing it. Nothing is tried again on
its own, not even after the agent restarts.

### Which devices

A plugin that works on the inventory's devices (`agent: {targets: {credentials: [ssh]}}`) gets the
devices it is turned on for (on the device, a tag or a group) that have a credential of a kind it
can use. A device without credentials, or with the plugin off, is never asked. They arrive in
`settings["targets"]`; a hosted `agent_settings(settings)` hook sees them first and may merge them
with devices it keeps itself.

### Privacy

A plugin says, for everything it sends, whether it is **aggregate** (hall-wide numbers) or
**device** (about the event's own switches, firewalls, servers). Aggregate data is checked twice,
on the agent before it leaves the hall and on the hosted side when it arrives: if it holds an IP
address, a network or a MAC address anywhere, it is refused. Switch and port names, times and
versions pass. Plugins still follow the usual rules: DNS names only once 5 or more clients looked
them up, no per-client traffic.

## For plugin authors

Add `agent` under `uses:` and an `agent:` block to `plugin.yaml`:

```yaml
uses: [agent, settings, actions, widgets]
agent:
  module: agent.py               # the default
  sends:                         # kind: how private it is
    stats: {privacy: aggregate}
    devices: {privacy: device}
    summary: {privacy: device, latest: true}   # only the newest counts: one waits, not a backlog
  fetches: [seats]               # the agent part asks the hosted part (agent_get_seats)
  calls: [status]                # read-only questions from the hosted side
  actions: [clear_cache]         # changes; each is also an action under actions:
actions:
  - {id: clear_cache, role: admin, danger: true}
```

### The agent part (`agent.py`)

```python
from floorbit.plugins.agent import AgentPlugin as Base


class AgentPlugin(Base):
    def start(self):
        self.ctx.thread(self.watch)                    # stops with the plugin

    def watch(self):
        while not self.ctx.stopping.wait(30):
            counts = ...                               # read, count, keep it hall-wide
            self.ctx.counter('lines', 120)
            self.ctx.send('stats', counts)             # -> Plugin.agent_stats on the hosted side

    def check(self):
        return 'reading /logs/access.log'              # python -m floorbit_agent check

    def call_status(self, args):
        return {'disk_free': ...}

    def action_clear_cache(self, params):
        return {'message': 'Cleared'}
```

`self.ctx` gives:

| | |
| --- | --- |
| `settings` | the plugin's settings from the hosted Floorbit (secrets too) |
| `send(kind, payload)` | queue it for the hosted part; kept on the agent's disk (256 MB, 24 hours per plugin) until it went out, so an uplink outage loses nothing. Refused at once when it breaks the privacy rule or the kind isn't listed |
| `health(status, message)` | `ok`, `warning`, `error` or `off`, shown on the Local agents page |
| `error(message)` | logs it and keeps it with the last ten errors |
| `counter(name, n)`, `gauge(name, value)` | numbers for `/metrics` and the report |
| `log(message)` | the agent's log, prefixed with the plugin's id |
| `thread(fn)`, `stopping` | background work that ends when the plugin stops |
| `listen_udp(port, handler)`, `listen_http(port, handler, tls=False)` | listeners that close when the plugin stops; with `tls=True` HTTPS when the hall set `FLOORBIT_AGENT_TLS_CERT` and `FLOORBIT_AGENT_TLS_KEY` (`ctx.tls` says which) |
| `primary()` | True unless VRRP runs and another agent in the hall holds the first VIP (see Two agents in one hall). Cheap: ask it every few seconds |
| `fetch(kind)` | what the hosted part's `agent_get_<kind>(agent)` answers, for a kind under `fetches:`. `HostedSaidNo` when it answered no (turned off there), another `PluginError` while it is away (keep what you had) |
| `on_stop(fn)` | runs when the plugin stops |
| `state_dir` | a folder of its own in the agent's state volume |
| `may_login(device, credential, rev)`, `auth_failed(device, credential, rev, message)` | ask before each login; say when it was refused (see Failed logins) |

When its settings change the agent stops and starts the plugin again, unless `configure(settings)`
returns `True` (it took them as they are). `floorbit.plugins.agent.MemoryContext` is a context that
keeps everything in memory, for tests.

### The hosted part (`plugin.py`)

```python
class Plugin(Base):
    def agent_stats(self, agent, payload):       # agent: {"id", "name"}
        self.ctx.set_state('last', payload)      # PluginError: declined (409), not sent again

    def agent_get_seats(self, agent):            # what ctx.fetch('seats') gets on the agent
        return {'seat_of': ...}

    def run_clear_cache(self, params):           # role checked, audited
        answers = self.ctx.agent_action('clear_cache', params)
        return {'message': 'Asked the agents', 'answers': answers}

    def endpoint_status(self, args):
        return self.ctx.agent_call('status')     # [{agent, name, result | error}]
```

`self.ctx.agent_health()` has what each agent last reported about the plugin. When the agent part
needs settings that live elsewhere (Settings > Telemetry), define `agent_settings(self, settings)`
on the hosted part and return what the agent gets; call `floorbit.agent_plugins.reload_agents()`
after they change.

### How it travels

| Way | Over |
| --- | --- |
| Settings | `GET /api/agent/v1/plugins`, pulled every minute with an ETag, and when a `plugins_reload` call says they changed |
| Sends | `POST /api/agent/v1/plugins/<id>/<kind>` `{"payload"}`, gzipped |
| Calls and actions | the agent link, method `plugin` `[id, "call" \| "action", name, args]` |
| Health | the agent's report every half minute, under `plugins`; plugin versions under `updates` |
| Bundles | listed under `bundles` in the settings, fetched from `GET /api/agent/v1/bundles/<file>` |

All of it goes over the agent's TLS connection with its key ([agent.md](agent.md)). Only official
plugins run on an agent: the ones in its image, newer versions of them signed by Floorbit's
release, and [Marketplace](marketplace.md) plugins ([What a plugin can ship](plugin-spec.md)).
