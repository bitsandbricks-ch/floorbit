### Added

- A small line in the page footer (and under the floor plan's side panel) shows which Floorbit runs
  here: the release, the commit (linked to GitHub), the build date and, for admins, the connected
  agents' versions. The image bakes them in at build time; `GET /api/version` returns them too.
