### Fixed

- With sign-in switched off (`AUTH_ENABLED=false`), the incident board, the plan's incident markers and My jobs answered "Unauthorized" to everyone. They now work, as one shared "Crew" account.
- Firewalls on an install without a monitoring source said the source "can't be read right now", as if something had broken. It now says no monitoring source is set up and where to add one.
