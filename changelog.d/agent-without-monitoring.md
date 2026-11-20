### Fixed

- An agent with no monitoring plugin set up is no longer asked for switch data by every page. Before,
  each of those calls failed, the agent showed as "Online, with warnings" and Problems said "Local agent
  has not answered yet" while it was answering. Demo data now keeps showing the hall when such an agent is enrolled.
