### Added

- Doors-open load test: `scripts/load_checkin.py` runs Floorbit under gunicorn and a real agent,
  sends a burst of check-ins and every device asking the captive portal, then stops Floorbit to show
  the agent answering alone. Results and charts in `docs/sizing.md`.
- Port lookups for check-ins are rate-limited (**Port lookups per second**, `CHECKIN_VERIFY_RATE`),
  oldest first, so a burst at doors-open drains instead of flooding LibreNMS.

### Changed

- The captive portal (DHCP option 114) is off until **Captive portal (DHCP option 114)** is turned on
  in the check-in settings (`CAPTIVE_ENABLED`).
- The check-in page's seat hint no longer waits for a LibreNMS lookup; a miss is looked up in the
  background.
