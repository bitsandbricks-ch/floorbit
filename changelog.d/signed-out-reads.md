### Security

- Signed out, only what the kiosk view draws can be read (floor plan, switches, seat blocks,
  occupancy, live events). Before, `AUTH_PUBLIC_READ` opened every read an account with
  `floorplan.view` has, including switch management IPs, incidents, the firewall per seat, the
  event report and the replay. The other big screens already sign in with a `kiosk` account.
- A switch's status read signed out leaves out its management IP.
- Live events no longer carry nicks, account names, IPs and MACs to readers without `seats.view`
  (signed out, kiosk, viewer). A check-in used to send all of them to anyone listening.
