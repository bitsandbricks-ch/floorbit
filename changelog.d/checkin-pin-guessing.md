### Security

- Check-in counts wrong seat PINs per PC: after 10 in ten minutes (`CHECKIN_PIN_TRIES`) that PC waits before it may try again, so a script can't find seat cards by guessing.
- A check-in from outside `CHECKIN_ALLOWED_NETWORKS` is refused before its PIN is looked at, so PINs can't be tested from outside the event network.
