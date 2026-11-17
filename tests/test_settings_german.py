"""Every setting on the Settings page has its German label, help and section text (Mike: German
everywhere). Core settings keep theirs in settings.json, integrations and built-in plugins in
integrationSettings.json; the page falls back to English for anything missing."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "frontend" / "src" / "i18n" / "de-CH"
# Plugins other people write bring their own texts; only the ones shipped with Floorbit are checked.
BUILTIN = {p.name for p in (ROOT / "floorbit" / "builtin_plugins").iterdir() if (p / "plugin.yaml").exists()}


def _german():
    out = {"fields": {}, "sections": {}}
    for name in ("settings.json", "integrationSettings.json"):
        texts = json.loads((I18N / name).read_text(encoding="utf-8"))
        for part in out:
            for key, value in (texts.get(part) or {}).items():
                out[part].setdefault(key, {}).update(value)
    return out


def test_every_setting_has_german(client):
    page = client.get("/api/settings").get_json()
    german = _german()
    def ours(name, sep):
        return not name.startswith("plugin" + sep) or name[7:].split(".")[0] in BUILTIN

    missing = [s["id"] for s in page["sections"] if ours(s["id"], "-")
               and not {"title", "desc"} <= set(german["sections"].get(s["id"], {}))]
    for field in page["fields"]:
        if not ours(field["key"], "."):
            continue
        have = german["fields"].get(field["key"].replace(".", "_"), {})
        wanted = {"label"} | ({"help"} if field.get("help") else set())
        if not wanted <= set(have):
            missing.append(field["key"])
    assert missing == []
