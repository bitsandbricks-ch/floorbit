### Fixed

- A seat's switch port is the seat mapping; its IP and MAC are optional extras. The traffic heatmap,
  the incident report's network snapshot and the find-a-player search now read a seat's mapped port
  directly and only fall back to its IP or MAC when no port is mapped, so a seat with a port and no
  IP is no longer "not found".
- Port actions and incident snapshots for a seat known only by its MAC found nothing: they looked
  for the MAC under the wrong name.
