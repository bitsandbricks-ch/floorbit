### Added

- Applications: rule sources. Add rules files by URL and Floorbit fetches them on a schedule (every 24 hours unless set), on top of the lists it ships. A failed fetch keeps the last good copy, a source higher in the list wins, and a freeze switch stops fetching during the event (#1503).
