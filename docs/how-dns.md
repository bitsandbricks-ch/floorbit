# DNS

From the event resolver's query log to the [DNS page](dns.md), and what never leaves the hall.

Code: [`floorbit/dns.py`](../floorbit/dns.py) (the counting), `dns_feeds` in the agent
(`floorbit_agent/__init__.py`), the Marketplace plugins for
[AdGuard Home](https://github.com/bitsandbricks-ch/floorbit-plugin-adguard-home) and
[Pi-hole](https://github.com/bitsandbricks-ch/floorbit-plugin-pihole).

```mermaid
sequenceDiagram
  autonumber
  participant W as DNS watch (Floorbit)
  participant A as Agent
  participant P as DNS plugin on the agent
  participant R as Resolver (AdGuard Home, Pi-hole)
  loop every DNS_INTERVAL (60 s)
    W->>A: call dns_feeds(since = newest ts seen)
    A->>P: dns_queries(since)
    P->>R: read the query log over HTTP
    R-->>P: ts, domain, client, blocked
    P-->>A: up to 50,000 lookups
    Note over A: Made safe before it leaves the hall:<br/>client = keyed hash (key only in the agent's memory)<br/>domain cut to the site, local names dropped
    A-->>W: per plugin: its lookups, or its error
    W->>W: keep the newest ts per plugin<br/>(nothing counted twice)
  end
```

What Floorbit does with the lookups:

```mermaid
flowchart TD
  in["Lookups: ts, site, hashed client, blocked"] --> hour["The open hour, in memory:<br/>per site, lookups and a set of client hashes"]
  hour --> close{"Hour over?"}
  close -- no --> hour
  close -- yes --> rule{"Site looked up by at least<br/>DNS_MIN_SEATS (5) clients?"}
  rule -- yes --> named["Kept by name: count, category"]
  rule -- no --> anon["Counted in the totals<br/>without a name"]
  named --> file[("dns.json, closed hours<br/>DNS_RETENTION_HOURS (168)")]
  anon --> file
  file --> page["DNS page: top sites, categories,<br/>blocked share, new sites"]
```

When the hour closes, only counts stay: the client hashes are dropped. Nothing is per seat or per
person ([dns.md](dns.md#privacy)).

Resolver health is a separate path: the [Services page](how-servers.md) asks each resolver for a
name every 30 s and shows how long it took.
