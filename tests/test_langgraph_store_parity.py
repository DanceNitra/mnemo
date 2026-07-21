# -*- coding: utf-8 -*-
"""Where a drop-in claim is easy to make and hard to keep.

Each of these encodes a bug that shipped and was caught by running LangGraph's own verification
routes rather than by reading the adapter.
"""
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

pytest.importorskip("langgraph")
from langgraph.store.memory import InMemoryStore              # noqa: E402
from inspeximus.integrations.langgraph import InspeximusStore  # noqa: E402


def _seed(store):
    store.put(("org", "acme", "team"), "k", {"v": 1})
    store.put(("org", "globex"), "k", {"v": 2})
    store.put(("notes",), "k", {"v": 3})
    store.put(("org", "acme", "other"), "k", {"v": 4})
    return store


@pytest.mark.parametrize("query", [
    lambda s: s.list_namespaces(),
    lambda s: s.list_namespaces(prefix=("org",)),
    lambda s: s.list_namespaces(prefix=("org", "acme")),
    lambda s: s.list_namespaces(suffix=("team",)),
    lambda s: s.list_namespaces(prefix=("org", "*", "team")),
    lambda s: s.list_namespaces(max_depth=2),
    lambda s: s.list_namespaces(limit=2),
    lambda s: s.list_namespaces(offset=1),
])
def test_list_namespaces_matches_the_reference(tmp_path, query):
    """prefix, suffix, wildcards and max_depth were ignored outright; limit returned a different
    subset because the result was unsorted."""
    ref = query(_seed(InMemoryStore()))
    ours = query(_seed(InspeximusStore(path=str(tmp_path / "s.jsonl"))))
    assert [tuple(x) for x in ref] == [tuple(x) for x in ours]


def test_deleting_the_last_key_leaves_the_namespace_listed_like_the_reference(tmp_path):
    ref, ours = InMemoryStore(), InspeximusStore(path=str(tmp_path / "d.jsonl"))
    for s in (ref, ours):
        s.put(("user", "42"), "secret", {"code": "ALPHA-SECRET"})
        s.delete(("user", "42"), "secret")
    assert [tuple(x) for x in ref.list_namespaces()] == [tuple(x) for x in ours.list_namespaces()]


def test_the_namespace_marker_carries_no_value_and_never_surfaces(tmp_path):
    """Matching the reference must not smuggle the deleted value back in."""
    ours = InspeximusStore(path=str(tmp_path / "d.jsonl"))
    ours.put(("user", "42"), "secret", {"code": "ALPHA-SECRET"})
    ours.delete(("user", "42"), "secret")
    ours.store._save(force=True)
    blob = " ".join(p.read_text(encoding="utf-8", errors="replace")
                    for p in tmp_path.rglob("*") if p.is_file())
    assert "ALPHA-SECRET" not in blob
    assert ours.get(("user", "42"), "secret") is None
    assert ours.search(("user",)) == []


def test_pruning_is_available_for_callers_who_want_the_name_gone_too(tmp_path):
    """A namespace can itself be an identifier, so the stricter behaviour exists -- opt-in."""
    pruned = InspeximusStore(path=str(tmp_path / "p.jsonl"), prune_empty_namespaces=True)
    pruned.put(("user", "42"), "secret", {"code": "X"})
    pruned.delete(("user", "42"), "secret")
    assert list(pruned.list_namespaces()) == []
