# Metrics

Where Floorbit's numbers come from, where they are kept, and who reads them. There are four kinds,
each with its own path.

| Kind | Made by | Kept in | Read by |
| --- | --- | --- | --- |
| Device and port series | Telemetry on the agent ([how-telemetry.md](how-telemetry.md)) | Lite database or VictoriaMetrics | Device graphs, `/api/telemetry/series`, Grafana |
| Hall stats | The port watch on Floorbit | Memory + the event's `stats.json` document | Traffic overview, dashboards, replay |
| Floorbit's own counts | `/api/metrics` at scrape time | Nowhere: worked out per scrape | A NOC's Prometheus and Grafana |
| Agent numbers | The agent's report and `/metrics` | Telemetry storage (`agent:<id>`) | The agent's Graphs tab, Prometheus |

```mermaid
flowchart LR
  subgraph agent["Local agent"]
    st["Telemetry state"] -- "every 60 s<br/>snapshot()" --> s1["series"]
    am["Agent counters"] --> rep["report every 30 s"]
    am --> amet["agent /metrics"]
  end
  subgraph fb["Floorbit"]
    s1 -- "send 'series'" --> sto["telemetry/storage.py"]
    rep -- "link or POST /report" --> ah["agent_history.py:<br/>counters to rates per minute"]
    ah --> sto
    sto --> vm[("VictoriaMetrics<br/>fb_port_*, fb_device_*, fb_agent_*")]
    sto --> lite[("Lite: floorbit_telemetry table<br/>1 min for 6 h, 15 min for 2 days")]
    pw["Port watch every 120 s<br/>(device_ports of placed,<br/>online switches)"] --> stats["stats.py: bandwidth, online seats,<br/>ports, uplinks, top talkers"]
    stats --> sj[("Event's stats.json<br/>24 h of samples + peak")]
    pm["/api/metrics (off until turned on):<br/>counts per hall: seats, incidents,<br/>switches, attention, port read age"]
  end
  sto --> graphs["Device and port graphs"]
  vm --> graf["Grafana"]
  sj --> dash["Traffic overview, dashboards, replay"]
  prom["Prometheus"] -- "scrape, read-only API token" --> pm
  prom -- scrape --> amet
```

Rules that hold on every path:

- **Aggregate only** where people could be named: `/api/metrics` is per hall at most, with no seat,
  nick, address or switch name ([metrics.md](metrics.md)). Telemetry series are per device and port;
  MAC tables and ARP are never stored as series.
- **Redis is not used** for any of it.
- **Lite or VictoriaMetrics, not both.** With `FLOORBIT_VICTORIAMETRICS_URL` set, the series go there
  and the lite table isn't written.
