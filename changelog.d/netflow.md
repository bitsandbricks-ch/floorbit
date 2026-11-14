### Added

- **Traffic** page (`/traffic`): what the hall's traffic is made of, from NetFlow v5, v9 or IPFIX.
  Gaming, streaming, downloads, updates and web for the hall and per seat block, the services most
  seats use, and anomalies (P2P floods, DDoS-like bursts, seats answering DHCP or DNS). Aggregate
  only: a service is named once 5 different seats used it, per seat there is only volume and the
  kind of traffic (for `seats.view`), raw flows are deleted after 7 days. The collector is an
  optional container (`docker compose --profile flows up -d`, udp/2055). Services come from
  built-in port rules and the event's own address rules (`FLOWS_SERVICES`). See `docs/flows.md`.
