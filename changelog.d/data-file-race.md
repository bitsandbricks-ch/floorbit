### Fixed

- Pages and the API could answer with an error now and then while data.json was being saved
  (it is written in place for the Docker bind mount, so a request could read half a file). Every
  reader and writer now goes through one lock, and a reader in another worker waits and reads again.
  The settings store no longer briefly forgets saved settings in the same situation.
