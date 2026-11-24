### Fixed

- Cables: the page's buttons no longer run past a laptop screen. Patch a block, Import, Print labels
  and CSV are under More.
- Local agents: the note that no plugin has reported yet sits inside its card.
- Incidents: "Send to nearest tech" is offered only while someone is on duty, and the search box shows its whole hint.
- Seat check-in page: with no seat cards printed it says so, instead of "0 of 0 seat PINs used" next to PIN check-ins; the demo prints PINs for its seats.
- Seat mapping counts seats that no seat block has (from a seat source such as `seats.json`) apart, marks them "not on the plan" and can list only them, so its total matches the floor plan and the dashboards.
- Public network status page: a firewall down (its seats failed over), an internet line, DNS or DHCP down no longer shows "All systems running". The page says in plain words what players notice and lists the seats whose range moved to another firewall.
- Services page, service health panes and the Services widget no longer give different totals: the Services page also lists the DHCP servers and firewalls the service health wall watches, from one shared count (`/api/services/summary`).
- Topology: the diagram is drawn as a tree, each access switch under its own distribution switch and the firewalls under the core instead of in one row beside it. It opens big enough to read the names, takes the full width until you pick something, and the legend lists only the cable types it draws (#1050).
- The "Demo data" badge sits next to the logo (top centre on phones) instead of over the status footer and the last row of each page (#1041).
