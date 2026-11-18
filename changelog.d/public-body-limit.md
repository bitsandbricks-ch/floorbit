### Security

- Requests sent without signing in (check-in, help desk, setup) may carry at most 1 MB of JSON. A
  few oversized ones at once could push Floorbit's memory up by hundreds of MB. The answer is a
  clear "too much data" in English or German.
