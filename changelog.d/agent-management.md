### Added

- Local agents: rename an agent, give it a new key (the old one keeps working until the agent uses
  the new one, 24 hours at most), and choose plugins an agent leaves to another one. Each agent
  shows its plugin versions, updates waiting for it and its last rollouts.
- Failover between agents: the Local agents page groups agents by hall and shows the primary and
  standby, the addresses each holds, active/active or active/passive, and what needs a look (a
  backup offline, two primaries, agents without VRRP). Only the primary polls devices and logs in,
  and a standby's traffic summary no longer replaces the primary's.
- The Local agents page also shows this Floorbit's own instances, which one leads, and whether the
  database and Redis answer.
