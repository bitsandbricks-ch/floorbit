### Added

- Sign in with your own OpenID Connect providers (Authentik, Keycloak, Microsoft Entra ID, Google,
  ...), set up under **Settings › Sign-in providers**. Authorization code flow with PKCE, `state` and
  `nonce`; the ID token's signature, issuer, audience, expiry and nonce are checked. Groups from a
  claim map to roles; without a mapping only linked accounts can sign in. Client secrets come only
  from `OIDC_<ID>_CLIENT_SECRET` or a Docker secret file. See `docs/auth.md`.
- Settings › Users can link an account to a sign-in provider ("Link sign-in").
