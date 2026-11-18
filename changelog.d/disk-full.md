### Fixed

- A full disk or a read-only state folder no longer turns every save into an "Internal Server Error"
  with a traceback in the log: the change is refused with a clear message (in English or German),
  the log says it once, and nothing saved earlier is lost.
- Seat check-in answers a clear "no" instead of a server error when a value of the wrong type is sent.
