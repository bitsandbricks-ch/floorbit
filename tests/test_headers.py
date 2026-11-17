"""Security headers on every answer (floorbit/headers.py)."""


def test_pages_and_api_answers_carry_the_guards(client):
    for path in ("/login", "/api/pages", "/static/css/brand/tokens.css"):
        h = client.get(path).headers
        assert h["X-Content-Type-Options"] == "nosniff", path
        assert h["Referrer-Policy"] == "same-origin", path
        assert h["Content-Security-Policy"] == "frame-ancestors 'self'", path
        assert h["X-Frame-Options"] == "SAMEORIGIN", path


def test_signed_out_answers_carry_them_too(anon_client):
    h = anon_client.get("/api/pages").headers
    assert h["X-Frame-Options"] == "SAMEORIGIN"


def test_trusted_origins_may_frame_floorbit(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module.app.extensions["auth"], "trusted_origins", ["https://event.example.com"])
    h = client.get("/login").headers
    assert h["Content-Security-Policy"] == "frame-ancestors 'self' https://event.example.com"
    # X-Frame-Options can't name another site, so it stays off and frame-ancestors decides.
    assert "X-Frame-Options" not in h


def test_an_answer_with_its_own_policy_keeps_it(client):
    # The uploaded logo is sandboxed; the frame guard must not replace that policy.
    svg = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciLz4="
    assert client.put("/api/settings", json={"theme.logo": svg}).status_code == 200
    resp = client.get("/brand/logo")
    assert resp.status_code == 200
    assert "sandbox" in resp.headers["Content-Security-Policy"]
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
