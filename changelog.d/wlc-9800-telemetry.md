### Added

- The Wi-Fi view shows a Cisco Catalyst 9800 wireless controller's access points from its own
  model-driven telemetry: each AP up or down, and per radio the channel, width, channel utilization
  and clients, every 30 seconds. **Device setup** on the controller's Telemetry tab shows the
  subscriptions to paste. Client lists are never asked for or stored.
- Cisco AireOS wireless controllers (5520, 3504, 8540) feed the Wi-Fi view the same way over SNMP,
  every minute, also while LibreNMS polls the switches.
