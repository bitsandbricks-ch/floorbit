### Fixed

- A stopped, killed or frozen local agent no longer holds every page for 8 seconds until it counts as
  gone a minute later: a closed link counts at once, and an agent that holds a call without a word
  is pinged and given up within about 8 seconds; over the HTTPS long poll, one that stops asking for
  work is given up after 5 seconds. Pages then answer from the last known state.

### Changed

- The plugin **Test** button runs on the local agent for plugins that reach the event network.
- With several pods, agent calls and answers cross Redis sealed with the vault key, so switch logins
  never sit there in the clear.
