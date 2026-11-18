### Fixed

- With two or more Floorbit pods on one database, teams, seat blocks and other entries added at the
  same moment no longer get lost: each save merges with what the other pods saved meanwhile and is
  only written if nobody wrote in between. Two people adding the very first team at once both keep
  theirs too.
