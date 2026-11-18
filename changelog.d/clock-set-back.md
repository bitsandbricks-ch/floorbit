### Fixed

- When the server's clock is set back (NTP correcting a box that booted ahead, a restored VM),
  Discord down alerts, sign-in and check-in PIN lockouts, rate limits and short caches no longer
  hold for as long as the clock went back: a switch going down still pages, and a sign-in
  lockout no longer lasts an hour.
