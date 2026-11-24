### Fixed

- When the syslog port was free for UDP but taken for TCP, Floorbit could hang on shutdown. It now gives the port back and reports the error.
