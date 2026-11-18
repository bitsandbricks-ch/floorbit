### Security

- The flow collector (on the local agent or the `flows` service) no longer hangs and runs out of
  memory on a crafted 40-byte NetFlow v9 or IPFIX packet, no longer stops listening for good on a
  packet whose template is cut short, and keeps at most 4,096 templates so made-up ones can't fill
  memory.

### Fixed

- The Traffic summary keeps being published when the server's clock is set back.
