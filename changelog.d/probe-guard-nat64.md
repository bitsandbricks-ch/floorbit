### Security

- Probes, game server queries and webhooks also refuse IPv6 addresses that carry a link-local IPv4 address inside (NAT64 `64:ff9b::`, 6to4 `2002::`), so `64:ff9b::a9fe:a9fe` no longer reaches the metadata service on a NAT64 network.
