### Added

- Tournament brackets: single-elimination brackets on `/tournament/brackets`, made from a team
  list (byes for the top seeds) or imported from a tournament tool through a plugin's new
  `brackets` area. Winners move on by themselves; a match's seats link to the floor plan and its
  match zone. The public `/bracket` (and `/bracket.json`) shows teams, scores and live matches for
  the big screens, never seats; off until switched on in Settings. See `docs/tournament.md`.
