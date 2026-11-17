### Security

- When Discord couldn't be reached, the error in the log, on the integrations status and in the
  "Send test message" answer named the whole webhook URL, token included, although the setting is
  write-only. The token part is now left out.
