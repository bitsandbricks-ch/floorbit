"""Security headers on every answer.

Kept small on purpose: no script-src policy yet, since the older Jinja pages still carry inline
scripts. What is here costs nothing and closes clickjacking and MIME sniffing.

Framing: crew pages may only be framed by Floorbit itself (the big-screen rotation in
/screen, frontend/src/pages/BigScreen.tsx, frames its own pages) and by the origins in ``AUTH_TRUSTED_ORIGINS``,
which already lists the sites an admin trusts, e.g. the event website showing the status wall.
"""


def frame_ancestors(trusted):
    return ' '.join(["'self'", *trusted])


def init_headers(app):
    def trusted():
        auth = app.extensions.get('auth')
        return list(getattr(auth, 'trusted_origins', []) or [])

    @app.after_request
    def security_headers(response):
        h = response.headers
        h.setdefault('X-Content-Type-Options', 'nosniff')
        # Signed links (the seat speed test's ?k=) carry a key in the query; keep it on this site.
        h.setdefault('Referrer-Policy', 'same-origin')
        origins = trusted()
        if 'Content-Security-Policy' not in h:
            h['Content-Security-Policy'] = f"frame-ancestors {frame_ancestors(origins)}"
        # Older browsers ignore frame-ancestors; X-Frame-Options can't name another site.
        if not origins:
            h.setdefault('X-Frame-Options', 'SAMEORIGIN')
        return response
