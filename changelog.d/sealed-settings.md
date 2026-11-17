### Security

- Secret settings are now encrypted at rest, like switch logins: the NetBox and LibreNMS tokens,
  sign-in client secrets and plugins' secret settings. Values saved earlier are encrypted the next
  time settings are saved, and `python -m floorbit.vault rotate` moves them to a new key.
  ([Switch logins](docs/credentials.md#secret-settings))
