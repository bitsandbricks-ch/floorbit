### Added

- Several Floorbit pods can run behind one address with `FLOORBIT_CLUSTER=redis`, Postgres and shared Redis. Live updates reach every pod's browsers, local agent calls reach the pod the agent is connected to, and one leader pod sends the automatic alerts, webhooks and timeline entries so each goes out once. See `docs/kubernetes.md`.
