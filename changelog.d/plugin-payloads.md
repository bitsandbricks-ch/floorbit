### Fixed

- What a local agent of another version (or a broken one) sends for the LAN cache can no longer break the LAN cache page or its dashboard tiles for everyone: odd values are left out when they arrive. The same for meter readings on the Electrics page, and for the traffic summary behind the Traffic, Games and wall pages.
- A whole number of hundreds of digits in a request (no browser sends one) is refused with a message, instead of a server error where it became a decimal number, as on a power reading typed in by hand.
