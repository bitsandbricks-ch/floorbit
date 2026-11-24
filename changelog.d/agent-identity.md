### Security

- Local agents sign every request with a key of their own, made on the agent and pinned in Floorbit
  at its first hello (a client certificate from the agents CA). A copied agent key alone no longer
  gets in. The agent's page shows the pinned key and can reset it. Update agents together with
  Floorbit: an agent that doesn't sign is refused.
- The sample Kubernetes manifest serves HTTPS and redirects plain HTTP.
