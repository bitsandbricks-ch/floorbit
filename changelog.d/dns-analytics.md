### Added

- DNS analytics: what the hall looks up, from the event's resolver through a `dns` plugin. Lookups
  per hour, top sites, categories (gaming, streaming, social, updates), new sites and the most
  blocked ones. Hall-wide only: a site is named once 5 different seats looked it up within an
  hour, clients are never stored and only counts are kept, for a week. See `docs/dns.md`.
