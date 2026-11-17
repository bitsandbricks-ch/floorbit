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
| `listen_udp(port, handler)`, `listen_http(port, handler)` | listeners that close when the plugin stops |
| `state_dir` | a folder of its own in the agent's state volume |

When its settings change the agent stops and starts the plugin again, unless `configure(settings)`
returns `True` (it took them as they are). `floorbit.plugins.agent.MemoryContext` is a context that
keeps everything in memory, for tests.

### The hosted part (`plugin.py`)

```python
class Plugin(Base):
    def agent_stats(self, agent, payload):       # agent: {"id", "name"}
        self.ctx.set_state('last', payload)

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
| Health | the agent's report every half minute, under `plugins` |

All of it goes over the agent's TLS connection with its key ([agent.md](agent.md)). Only plugins
that ship with Floorbit run on an agent; nothing is downloaded to it.
