### Security

- A saved NetBox or LibreNMS API token is only sent to the URL it was saved with. Changing the URL,
  on save or in "Test connection", asks for the token again, so someone who may change settings but
  never sees the token can't point the URL at their own server to receive it.
- An OIDC sign-in provider's issuer can only change within the same host once its client secret is
  set, for the same reason.
