### Added

- The SNMPv3 user devices send traps as is a credential of its own (**SNMP v3 trap user**), set on
  the defaults, a group, a tag or a device. Each agent runs a trap listener for each distinct trap
  user among its devices (162, then 1163 to 1170), and each device's Telemetry tab and Device setup
  say which port it sends to. Trap users without passphrases (`noAuthNoPriv`) work too.
