# The local agent

The agent for a hosted Floorbit (issue #2): what it does and how to run it is in
[docs/agent.md](../../docs/agent.md). This file is for whoever changes it, or moves it to its own
repository.

| File | What |
| --- | --- |
| `__init__.py` | The program: the call loop (`Agent`), what each call runs (`local_executor`), `check`, `main` |
| `syslog_relay.py` | Takes syslog on UDP and sends it on in batches, buffering while the host is away |
| `flows_relay.py` | Runs the flow collector and sends its summary |
| `__main__.py` | `python -m floorbit.agent` |

The hosted side is `floorbit/agent_link.py` (the tunnel, routing by hall, stats) and
`floorbit/blueprints/agent.py` (the `/api/agent/v1/` routes).

## What it takes from Floorbit

The agent is the same image as Floorbit, so it reuses Floorbit's code instead of copying it. These
are the only places it reaches into the rest of `floorbit/`; `tests/test_agent_boundary.py` fails
when another one appears, so a new dependency is a decision, not an accident.

| Import | Why |
| --- | --- |
| `create_app`, `ROOT` | the plugin registry and its settings (`LIBRENMS_URL`, `FLOORBIT_PLUGIN_*`), and the version |
| `sources` | the plugin registry: monitoring, inventory, health, DNS and Wi-Fi plugins |
| `plugins.base.PluginError` | the error plugins raise |
| `cables` | which plugins know cables |
| `dns` | `site()` and `MAX_PER_POLL`: lookups are cut to the site and capped on the agent |
| `wifi` | `clean_ap()` and `MAX_APS`: only counts leave the event network |
| `flows.collector` | the NetFlow and IPFIX collector, run on the agent |

In its own repository the agent would need these as a library (the plugins above all), or a
smaller plugin runner of its own. The protocol it speaks is in docs/agent.md, "The protocol", and
doesn't depend on any of them.
