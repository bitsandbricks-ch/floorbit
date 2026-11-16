### Security

- The server's own probes check an IPv4-mapped IPv6 address (`::ffff:169.254.169.254`) as the IPv4 address it reaches, so it is held to `PROBE_NETS` and the link-local block on every Python release.
