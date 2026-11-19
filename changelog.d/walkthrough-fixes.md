### Fixed

- Seat check-in page: with no seat cards printed it says so, instead of "0 of 0 seat PINs used" next to PIN check-ins; the demo prints PINs for its seats.
- Seat mapping counts seats that no seat block has (from a seat source such as `seats.json`) apart, marks them "not on the plan" and can list only them, so its total matches the floor plan and the dashboards.
- Public network status page: a firewall down (its seats failed over), an internet line, DNS or DHCP down no longer shows "All systems running". The page says in plain words what players notice and lists the seats whose range moved to another firewall.
- Services page, service health panes and the Services widget no longer give different totals: the Services page also lists the DHCP servers and firewalls the service health wall watches, from one shared count (`/api/services/summary`).
