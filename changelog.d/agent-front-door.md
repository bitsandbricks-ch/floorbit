### Added

- The local agent can serve Floorbit's pages on the event network (`FLOORBIT_AGENT_FRONT_DOOR`), so a
  hosted Floorbit sees each attendee's own address instead of the hall's NAT address: check-in finds
  the seat's port, the sign-in lockout and limits are per PC again, and the seat speed test measures
  the hall's network up to the agent. Typing `CHECKIN_ADDRESS` at the agent opens check-in.
