### Fixed

- A firewall port that both SNMP and the firewall's own Telegraf report showed up twice, which broke the port picker on the ISP line form ("Duplicate options are not supported"). It is one port again, and port pickers list each port once (#972).
