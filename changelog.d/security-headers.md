### Security

- Every answer now carries `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` and a frame guard, so another site can't show Floorbit in a hidden frame to trick a signed-in crew member into clicks. Sites in `AUTH_TRUSTED_ORIGINS` may still frame it.
