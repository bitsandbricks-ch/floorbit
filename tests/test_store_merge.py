"""Merging a save with what others saved since the caller loaded the document (store._merge3)."""
from floorbit.store import _merge3


def test_both_add_a_key():
    assert _merge3({"a": 1}, {"a": 1, "b": 2}, {"a": 1, "c": 3}) == {"a": 1, "b": 2, "c": 3}


def test_both_add_the_first_entry_of_a_missing_object():
    merged = _merge3({}, {"teams": {"x": {"id": "x"}}}, {"teams": {"y": {"id": "y"}}})
    assert set(merged["teams"]) == {"x", "y"}


def test_lists_of_objects_with_ids_merge_item_by_item():
    base = {"blocks": [{"id": 1, "n": "a"}]}
    current = {"blocks": [{"id": 1, "n": "a"}, {"id": 2, "n": "b"}]}
    mine = {"blocks": [{"id": 1, "n": "A"}, {"id": 3, "n": "c"}]}
    assert _merge3(base, current, mine) == {"blocks": [{"id": 1, "n": "A"}, {"id": 2, "n": "b"}, {"id": 3, "n": "c"}]}


def test_a_removal_by_either_side_stays_removed():
    base = {"blocks": [{"id": 1}, {"id": 2}]}
    assert _merge3(base, {"blocks": [{"id": 1}]}, base) == {"blocks": [{"id": 1}]}
    assert _merge3(base, {"blocks": [{"id": 1}, {"id": 2}, {"id": 3}]}, {"blocks": [{"id": 2}]}) == {
        "blocks": [{"id": 2}, {"id": 3}]}
    assert _merge3({"a": 1, "b": 2}, {"a": 1, "b": 2, "c": 3}, {"a": 1}) == {"a": 1, "c": 3}


def test_the_later_save_wins_on_the_same_value():
    assert _merge3({"n": 1}, {"n": 2}, {"n": 3}) == {"n": 3}


def test_plain_lists_are_not_merged():
    assert _merge3({"l": [1]}, {"l": [1, 2]}, {"l": [1, 3]}) == {"l": [1, 3]}


def test_untouched_by_me_keeps_theirs():
    assert _merge3({"n": 1, "m": 1}, {"n": 2, "m": 1}, {"n": 1, "m": 1}) == {"n": 2, "m": 1}
