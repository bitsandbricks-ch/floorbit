### Fixed

- A game server that answers its status ping with something odd (a list, text where a number
  belongs, a message of the day nested very deep) shows as down or with what could be read, instead
  of stopping the check of every other game server.
- An RCON port that keeps sending without ever answering the login no longer holds the console
  forever.
