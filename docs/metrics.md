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
