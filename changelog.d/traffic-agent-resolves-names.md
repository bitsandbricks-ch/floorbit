### Added

- Traffic names HTTPS downloads with Pi-hole too: when a seat looks up a name under an application's site and the resolver plugin gives no answer, the agent looks the name up itself. Every 10 minutes it also resolves the applications' sites and the game servers set up by host name, which now count as traffic rules. (#1630)
