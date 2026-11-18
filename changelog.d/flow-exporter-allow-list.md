### Security

- The Traffic collector can take flows from listed exporters only (`FLOWS_ALLOW`, addresses and
  networks). Packets from anyone else, such as a seat PC sending made-up flows, are dropped and
  counted. Unset, every sender counts as before.
