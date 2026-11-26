"""Links in alerts work without a Public URL (issue #1433): Floorbit remembers where a signed-in
crew member last opened a page, and the setting still wins."""
from floorbit import public_url
from integrations import config
from tests.test_incidents import sign_in_as


def test_a_crew_page_view_teaches_the_address(app_module, monkeypatch):
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    crew = sign_in_as(app_module, "pu1", "admin")
    with app_module.app.test_request_context():
        public_url._known.clear()
    crew.get("/settings")       # 503 without a frontend build in CI: the address counts all the same
    with app_module.app.test_request_context():
        assert public_url.learned() == "http://localhost"
        assert config.public_url() == "http://localhost"
        monkeypatch.setenv("PUBLIC_URL", "https://set.example.com/")
        assert config.public_url() == "https://set.example.com"


def test_api_calls_and_anonymous_pages_teach_nothing(app_module, monkeypatch):
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    with app_module.app.test_request_context():
        public_url._known.clear()
        before = public_url.learned()
    app_module.app.test_client().get("/login", base_url="https://other.example.com")
    crew = sign_in_as(app_module, "pu2", "admin")
    with app_module.app.test_request_context():
        public_url.learn("https://before.example.com")
        before = public_url.learned()
    crew.get("/api/settings")
    with app_module.app.test_request_context():
        assert public_url.learned() == before
        assert not public_url.learn("javascript:alert(1)")
