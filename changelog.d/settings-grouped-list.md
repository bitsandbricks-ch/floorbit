### Changed

- Settings is one grouped list (Event, People, Alerts, Floorbit) instead of four tabs with about 25
  entries: related sections share an entry (Seats and check-in, Monitoring, Alerts and Discord), each
  has an icon, and the ones in the setup checklist show their state.
- Settings has one search box, in the top bar where the global one sits (press `/`); Ctrl K still
  opens "Go to".
- Public URL and the address on the seat QR codes are only an override under Server, Advanced.
  Without a Public URL, links in alerts use the address the crew last opened Floorbit at.

### Fixed

- The audit log only shows its Fields column when an entry names fields.
- The API, webhook and tenant help lines link to the docs instead of naming a file.
