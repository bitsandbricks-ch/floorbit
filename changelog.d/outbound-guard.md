### Security

- Every request the server makes (NetBox, LibreNMS, sign-in providers, seat sources, webhooks, Loki, plugins) is checked against the address it connects to, after DNS: never link-local, `0.0.0.0` or multicast, so DNS rebinding can't reach the cloud metadata service. A hosted Floorbit can refuse more with `OUTBOUND_BLOCK_NETS` (loopback, its own network). See `docs/agent.md`.
