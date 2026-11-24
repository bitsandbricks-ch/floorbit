### Added

- Own checks on the Services page: a ping, a TCP port, a UDP port or an HTTP(S) address (status codes, a text to find, certificate days), run by the local agent, with **Test** before saving.
- Tags on every service, plugin ones too, and **Group by** type, tag or state on the Services page.
- A details panel per service: its numbers, the "full in" forecast, tags, and muting alerts for an hour.
- DNS: categories, top sites, most blocked and new sites are sortable tables that page (top sites at 50 rows), so a long event shows every named site.

### Changed

- Services and Service health are one page: the plugins' services (DHCP, firewalls, ...) are listed under Services, and one **Check now** checks everything.
- Without a connected agent, services show grey ("not checked") instead of red, and the server never probes the event network itself, also not in demo mode.

### Removed

- The Service health page (`/health`); its contents are on the Services page.
