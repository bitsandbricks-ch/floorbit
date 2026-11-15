### Changed

- Hosted Floorbit, part 27: `floorbit/agent/` is gone. The agent now lives only in bitsandbricks-ch/floorbit-agent. The hosted side's end-to-end tests run that agent at the commit pinned in `AGENT_REF`, and a test checks that everything the agent imports from Floorbit still exists.
