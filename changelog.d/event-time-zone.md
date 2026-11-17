### Fixed

- The image ships the time zone files, so `TZ` in `.env` (for example `TZ=Europe/Zurich`) really sets the event's time zone for quiet hours, the forecast and the public status page. `.env.example`, the Kubernetes example and the install guide now name it.
