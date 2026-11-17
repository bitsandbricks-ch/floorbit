### Fixed

- The seat finder (`/find`) and the Discord `/report` and `/seat` commands find a seat however it
  is typed: `a3`, `A 3` and `A03` all mean `A-3`. Before, anything but the exact spelling said
  there was no such seat.
