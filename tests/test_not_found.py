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
