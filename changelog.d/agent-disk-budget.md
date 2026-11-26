### Added

- **One disk budget per agent**, set on the agent's page: raw flows, the buffer for while Floorbit
  is away and plugin files share it. When it is used up the oldest files are overwritten, so the
  agent keeps collecting. Left at 0 it takes half of what the agent's disk could hold. The agent's
  page shows what each kind uses and how many hours back it reaches (with an agent that reports it).

### Removed

- `FLOWS_RAW_MAX_MB` and the agent's *Buffer size (MB)* setting: the disk budget replaces both.
