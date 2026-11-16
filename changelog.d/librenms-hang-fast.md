### Fixed

- A LibreNMS that hangs no longer makes pages hang. The seat heatmap took a minute, Topology 35 s
  and Firewalls 15 s, because each question waited out its own timeout. Now, once LibreNMS doesn't
  answer, Floorbit stops asking it for 30 seconds, and the Firewalls page reads the status
  monitor's last device list instead of asking LibreNMS itself.
