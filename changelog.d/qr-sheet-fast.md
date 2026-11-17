### Fixed

- The seat cards and QR sheet loaded slowly in big halls: every load drew every QR code again (about 15 seconds for 4000 seats). Each code is now drawn once, so after the first load the sheet opens in a fraction of a second.
