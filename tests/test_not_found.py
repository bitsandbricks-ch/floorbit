"""Unknown addresses answer 404 in Floorbit's own look (floorbit/not_found.py)."""
import json
import re


def _boot(page):
    found = re.search(r'<script type="application/json" id="fb-page">(.*?)</script>', page.get_data(as_text=True))
    return json.loads(found.group(1)) if found else None


def test_a_mistyped_page_gets_the_apps_404(client):
    page = client.get("/no-such-page", headers={"Accept": "text/html"})
    assert page.status_code == 404
    assert _boot(page) == {"kind": "not-found"}


def test_the_api_answers_json(client):
    answer = client.get("/api/no-such-thing")
    assert answer.status_code == 404 and answer.get_json() == {"error": "Not found"}


def test_a_missing_file_gets_the_short_answer(client):
    answer = client.get("/static/no-such-file.js")
    assert answer.status_code == 404 and b"fb-page" not in answer.data


def test_a_page_whose_feature_is_off_gets_the_404_page(client):
    client.put("/api/settings/features", json={"power": False})
    page = client.get("/power", headers={"Accept": "text/html"})
    assert page.status_code == 404 and _boot(page) == {"kind": "not-found"}


def test_signed_out_people_still_go_to_sign_in(app_module):
    answer = app_module.app.test_client().get("/no-such-page", headers={"Accept": "text/html"})
    assert answer.status_code == 302 and "/login" in answer.headers["Location"]


def test_a_refusal_in_a_view_answers_json_the_page_can_show(app_module):
    # abort(403, description=...) used to give Flask's HTML page, so the board could only say "HTTP 403".
    app_module.app.extensions["auth"].users.add("vi", "viewer-password-1", role="viewer")
    viewer = app_module.app.test_client()
    viewer.post("/login", data={"username": "vi", "password": "viewer-password-1"})
    answer = viewer.post("/api/incidents", json={"seat": "A-1", "title": "No internet"})
    assert answer.status_code == 403
    assert answer.get_json() == {"error": 'Needs the "work incidents" permission, in your role or a team.'}
    german = viewer.post("/api/incidents", json={"seat": "A-1"}, headers={"Accept-Language": "de-CH"})
    assert german.get_json()["error"].startswith("Braucht das Recht")


def test_a_bare_abort_gets_a_short_text_and_keeps_its_headers(client):
    answer = client.delete("/api/auth/me")      # GET only: 405 with an Allow header
    assert answer.status_code == 405
    assert answer.get_json() == {"error": "This address does not take that method."}
    assert "GET" in answer.headers.get("Allow", "")
