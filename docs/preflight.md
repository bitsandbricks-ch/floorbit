# Pre-flight check

`/preflight` (Settings > Pre-flight check) is the go or no-go board for before the doors open.
Issue #35.

| Group | What it checks | Fails when |
|---|---|---|
| Switches reachable | every switch placed on the floor plan, against the monitoring source | the source says it is down, or it can't be found there |
| Uplinks up | on each placed switch, the ports whose description matches `STATS_UPLINK_PATTERN` (default `uplink\|trunk`) | an uplink is down. A switch with no port described as an uplink is shown as "Check". |
| DHCP, DNS and services | every check from the [health wall](health.md)'s plugins, asked now | a service is red or unknown. Amber shows as "Check". |

**Run all checks** runs every group. **Run again** on a group runs just that group after a fix,
and the other groups keep their last result. The board says **Ready for doors** once every group
has run and nothing failed.

The checks ask the monitoring source and the health plugins directly. They never move the status
monitor's or the health wall's state, so running them sends no alerts. Without a monitoring
source, the switch and uplink checks are skipped. Without a health plugin, the services group
says to turn on the DHCP and DNS checks.

**Print** opens a PDF of the result to sign: the verdict, each check with when and by whom it
ran, and lines for a signature and the time.

The last result of each group is kept in `data.json` under `preflight`. Anyone who can see the
floor plan can look at the board. Running checks needs **Work incidents** (techs, leads and
admins), and each run goes to the audit log.
