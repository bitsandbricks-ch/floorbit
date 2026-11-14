### Added

- Network status page: `/status` tells attendees, without an account, whether the network is
  running, which halls, seat blocks and rows an outage hits, and the crew's updates; `/status.json`
  has the same for the event website or a bot. The state comes from the status monitor (a router
  or firewall down, or half the switches, is an outage) and the crew can set it by hand, for
  example to Maintenance. No switch names or IPs unless an admin turns them on. Off by default
  (Settings > Attendee pages). The crew's page is `/network-status`. See `docs/status-page.md`.
