### Fixed

- A background job that was still working on one event's data when another event became current saved that data into the new event, overwriting it. It now saves back to the event it read from.
