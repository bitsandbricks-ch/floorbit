### Changed

- The `latest` image (and the `master-…` tags) are pushed only after CI has passed on that commit, so a master that cannot start never reaches a deployment that follows `latest`.
