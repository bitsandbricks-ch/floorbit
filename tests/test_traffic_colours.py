"""One colour per traffic kind on every chart (#1408)."""
import pathlib
import re

from floorbit.dashboard_core import traffic_mix_widget
from floorbit.flows.classify import CATEGORIES, CATEGORY_COLOURS
from floorbit.plugins.widgets import check_widget

CSS = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src" / "styles" / "pages.css"


def test_the_traffic_page_uses_the_same_colours():
    css = dict(re.findall(r"\.cat-([a-z]+) \{ background: (#[0-9a-f]{6}); \}", CSS.read_text()))
    assert set(CATEGORY_COLOURS) == set(CATEGORIES)
    assert {c: css.get(c) for c in CATEGORIES} == CATEGORY_COLOURS


def test_traffic_by_kind_names_each_kind_with_its_colour_and_a_short_value():
    w = traffic_mix_widget("en", {"mix_hour": {"gaming": 3_000_000_000, "web": 1_000_000_000}})
    assert [(i["label"], i["colour"]) for i in w["items"]] == [("Gaming", "#16a34a"), ("Web", "#0891b2")]
    assert w["items"][0]["value"] == "3.0 GB" and w["sub"] == "Last hour: 4.0 GB"
    checked = check_widget(w, {"id": "x", "label": "x"})
    assert [i["colour"] for i in checked["items"]] == ["#16a34a", "#0891b2"]


def test_only_plain_colours_pass():
    raw = {"type": "list", "items": [{"label": "a", "value": "1", "colour": "red;background:url(x)"},
                                     {"label": "b", "value": "2", "colour": "var(--bnb-accent)"}]}
    items = check_widget(raw, {"id": "x", "label": "x"})["items"]
    assert "colour" not in items[0] and items[1]["colour"] == "var(--bnb-accent)"
