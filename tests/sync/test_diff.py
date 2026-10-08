from __future__ import annotations

from vsa_commerce.sync.diff import diff_snapshots, flatten


def test_added_removed_changed():
    old = {"offerings": [{"id": "a", "price": 1, "old": True}]}
    new = {"offerings": [{"id": "a", "price": 2, "new": True}, {"id": "b", "price": 3}]}
    assert [str(c) for c in diff_snapshots(old, new)] == [
        "added offerings[a].new = True",
        "removed offerings[a].old (was True)",
        "changed offerings[a].price: 1 -> 2",
        "added offerings[b].id = 'b'",
        "added offerings[b].price = 3",
    ]


def test_reordering_is_not_a_change():
    a, b = {"id": "a", "x": 1}, {"id": "b", "x": 2}
    assert diff_snapshots({"offerings": [a, b]}, {"offerings": [b, a]}) == []


def test_fetch_time_is_not_a_change():
    old = {"offerings": [{"id": "a", "provenance": {"fetched_at": "2026-10-07"}}]}
    new = {"offerings": [{"id": "a", "provenance": {"fetched_at": "2026-10-08"}}]}
    assert [str(c) for c in diff_snapshots(old, new)] == []


def test_plain_lists_compare_as_values():
    assert flatten({"tags": ["a", "b"]}) == {"tags": ["a", "b"]}
    assert [str(c) for c in diff_snapshots({"tags": ["a"]}, {"tags": ["a", "b"]})] == [
        "changed tags: ['a'] -> ['a', 'b']"
    ]
