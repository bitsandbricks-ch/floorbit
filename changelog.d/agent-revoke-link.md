### Security

- Revoking a local agent's key now also ends the WebSocket link it already has open, within a few
  seconds. Before, a revoked agent kept getting calls until it reconnected.
