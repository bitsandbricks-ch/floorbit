# Prometheus metrics

`GET /api/metrics` serves Floorbit's own counts in the Prometheus text format, so a NOC's Grafana
can graph the event next to everything else. It is off until an admin turns on **Settings >
Prometheus metrics** (or `METRICS_ENABLED=true`).

Everything is a count, per hall at most: no seat numbers, nicks, addresses or switch names.

| Metric | Labels | What |
| --- | --- | --- |
| `floorbit_seats` | `hall`, `state` | Seats online (port up), offline (port down) and unknown, as on the [Seats view](seats.md). |
| `floorbit_seats_with_problems` | `hall` | Seats with an open incident or port trouble. |
| `floorbit_seats_checked_in` | `hall` | Seats with a check-in (only with check-in on). |
| `floorbit_incidents` | `status` | Incidents: open, assigned, fixed. |
| `floorbit_switches` | `status` | Monitored switches by status. |
| `floorbit_attention_items` | `kind` | Needs-attention items by kind. |
| `floorbit_port_read_age_seconds` | | Seconds since the last switch port read. Alert when it grows. |
| `floorbit_info` | `version` | Always 1. |

## Scraping

Reading it needs `floorplan.view` like every other read. Make an API token under
**Settings > API** with the viewer role and **read only**, then:

```yaml
scrape_configs:
  - job_name: floorbit
    scrape_interval: 30s
    metrics_path: /api/metrics
    scheme: https
    authorization:
      credentials: fbt_xxxxxxxx_example
    static_configs:
      - targets: ['floor.example.com']
```

## Grafana dashboard and alerts

Two ready files to start from:

- [`grafana/floorbit-dashboard.json`](grafana/floorbit-dashboard.json): in Grafana, **Dashboards >
  New > Import**, upload the file and pick your Prometheus data source. It shows seats online, seats
  with problems, open incidents, switches offline, port read age and check-ins at the top, and their
  history below, with a **Hall** filter.
- [`grafana/floorbit-alerts.yml`](grafana/floorbit-alerts.yml): Prometheus alert rules. Add the file
  to `rule_files:` in `prometheus.yml`.

| Alert | Fires when |
| --- | --- |
| `FloorbitScrapeFailing` | Prometheus has had no Floorbit metrics for 5 minutes. |
| `FloorbitPortReadStale` | The last switch port read is more than 5 minutes old. |
| `FloorbitSwitchOffline` | A monitored switch is offline for a minute. |
| `FloorbitSeatsDropped` | More than 10 extra seats in a hall went offline within 5 minutes: usually an uplink or a switch, not players leaving. |
| `FloorbitOpenIncidents` | More than 10 incidents are open with nobody assigned for 10 minutes. |

The thresholds are starting points; tune them to the size of your event. A test checks that both
files only use metrics `/api/metrics` serves.
