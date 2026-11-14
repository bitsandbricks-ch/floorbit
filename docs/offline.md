# Offline mode

Floorbit keeps working when the monitoring source drops out: the uplink is down, LibreNMS is
restarting, or its token expired.

## What still works

- **The floor plan, the inventory and the seat mapping.** They live in Floorbit's own
  `data.json`, so editing and viewing never needed NetBox or LibreNMS. A NetBox outage only means
  the next sync fails; the inventory keeps every device.
- **Switch status, port details, IP lookups and check-in ARP lookups** answer from the **last good
  data**: the last answer the monitoring source gave for that switch, port or address.

## What you see

- The floor plan's top bar says **Offline since 14:32, data from 14:31**.
- Switches showing last known data are greyed out.
- Each answer from the API carries:
  - `stale: true`
  - `as_of`: when the data was fetched
  - `offline_since`
- `GET /api/monitoring/health` says whether the source is answering, since when it isn't, and the
  plugin's error message.

## Alerts

The status monitor marks the outage as soon as a poll fails.

- **During the outage**, switch status isn't compared, so nothing is announced. Discord gets
  **one** message: "LibreNMS is unreachable".
- **When the source answers again**, Discord gets one "LibreNMS is back" message with how long it
  was down. The monitor then starts from a fresh baseline: switches that changed while it was blind
  are shown, not announced all at once. Changes after that are announced as usual.

## Where the last good data is kept

- **With Redis:** in Redis, shared by every worker, for 7 days.
- **Without Redis:** in memory, and written to `monitoring-cache.json` next to `data.json` (or
  `MONITORING_CACHE_FILE`) at most once a minute, so a restart during an outage still has data to
  show.

This works for any monitoring plugin, not only LibreNMS.
