### Added

- Roles and permissions: every request needs a permission (`floorplan.edit`, `seats.view`,
  `audit.read`, ...), and a role is a set of them. Built-in roles Admin, Lead, Tech, Viewer and
  Kiosk; admins add their own on **Settings › Roles and teams**. See `docs/auth.md`.
- Teams and sub-teams (Infra › Core, Access, Wi-Fi; Operations; Electrics to start with). An account
  can be in several teams with a role in each, which counts for the sub-teams too and only adds
  permissions inside those teams.
- `GET /api/seats/occupancy`: which seats are taken, without nicks or IPs, for viewers and kiosks.
- Changes to roles, teams and team members are in the audit log.

### Changed

- The Editor role is now called Lead, and leads can read the audit log. Existing editors become
  leads automatically.
- Seat data with nicks, IPs and MACs (`/api/seats/info`, the seat mapping, check-ins) needs the
  `seats.view` permission, so viewers and signed-out kiosk screens no longer see it.
- Plugin actions and widgets can name the permission they need (`permission:` in the manifest).
