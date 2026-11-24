"""Every crew page asks for the problems: one request reads the floor plan once (issue #1290)."""
import traceback

from floorbit import database, upgrades


def _parses(monkeypatch):
    """How often data.json is read whole (shared reads, parsed once per change, don't count)."""
    seen = []
    real = database.Sql.get_text

    def counting(self, key):
        if key.endswith("data.json") and not any(f.name == "read_shared" for f in traceback.extract_stack()):
            seen.append(key)
        return real(self, key)
    monkeypatch.setattr(database.Sql, "get_text", counting)
    return seen


def test_problems_read_the_floor_plan_once(client, monkeypatch):
    upgrades.run_at_start()                          # as at start: shared reads need the current shape
    client.get("/api/problems")                      # warm: shared reads parse once per change
    seen = _parses(monkeypatch)
    assert client.get("/api/problems").status_code == 200
    # The request's own read, the health wall's, the power circuits' and the incident list's.
    assert len(seen) <= 5, seen


def test_the_incident_list_reads_the_teams_once(client, monkeypatch):
    upgrades.run_at_start()
    client.get("/api/incidents/people")
    seen = _parses(monkeypatch)
    assert client.get("/api/incidents/people").status_code == 200
    assert len(seen) <= 1, seen
