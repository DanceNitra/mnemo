"""Regression test for the LangGraph BaseStore adapter (mnemo.integrations.langgraph.MnemoStore). The 6
framework adapters were probe-verified but not in the pytest suite, so an API drift (langgraph or mnemo) could
break a documented integration silently. This pins the store contract + mnemo's differentiator (queryable
history the built-in InMemoryStore discards). Skips cleanly if langgraph isn't installed."""
import pytest
pytest.importorskip("langgraph")
from mnemo.integrations.langgraph import MnemoStore


def _store():
    return MnemoStore()   # in-memory mnemo


def test_put_get_roundtrip():
    s = _store()
    s.put(("user", "42"), "region", {"value": "Frankfurt"})
    item = s.get(("user", "42"), "region")
    assert item is not None and item.value == {"value": "Frankfurt"}
    assert item.namespace == ("user", "42") and item.key == "region"


def test_same_key_supersedes_no_resurrection():
    """The differentiator: a second put on the same key overwrites (like InMemoryStore), but get never returns
    the old value afterwards."""
    s = _store()
    s.put(("u",), "tz", {"tz": "UTC"})
    s.put(("u",), "tz", {"tz": "PST"})
    assert s.get(("u",), "tz").value == {"tz": "PST"}


def test_history_keeps_what_inmemorystore_discards():
    s = _store()
    s.put(("u",), "tz", {"tz": "UTC"})
    s.put(("u",), "tz", {"tz": "PST"})
    assert s.history(("u",), "tz") == [{"tz": "UTC"}, {"tz": "PST"}]


def test_delete_is_value_none():
    s = _store()
    s.put(("u",), "k", {"v": 1})
    s.put(("u",), "k", None)                      # LangGraph delete convention
    assert s.get(("u",), "k") is None


def test_search_by_query_scoped_to_namespace():
    s = _store()
    s.put(("team", "a"), "cache region", {"value": "osaka"})
    s.put(("team", "b"), "cache region", {"value": "malmo"})
    hits = s.search(("team", "a"), query="cache region")
    assert all(h.namespace == ("team", "a") for h in hits)
    assert any(h.value == {"value": "osaka"} for h in hits)


def test_search_without_query_lists_namespace():
    s = _store()
    s.put(("u",), "a", {"v": 1}); s.put(("u",), "b", {"v": 2})
    keys = {h.key for h in s.search(("u",))}
    assert {"a", "b"} <= keys


def test_list_namespaces():
    s = _store()
    s.put(("user", "1"), "k", {"v": 1}); s.put(("user", "2"), "k", {"v": 2})
    ns = s.list_namespaces()
    assert ("user", "1") in ns and ("user", "2") in ns


def test_get_missing_returns_none():
    assert _store().get(("nope",), "nope") is None
