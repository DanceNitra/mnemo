"""The mem0-compatible drop-in: same API surface, plus deterministic echo-resistant correction — the thing
a similarity store (mem0 0.53) gets wrong and this store (1.00) doesn't. See mnemo/mem0_compat.py."""
from mnemo.mem0 import Memory


def _val(results):
    return " ".join(r["memory"] for r in results["results"])


def test_echo_resistance_in_plain_mem0_style_code():
    """The headline: plain mem0-style add() calls, no keys, no config — a correction survives the OLD value
    being restated. A similarity store revives it ~47% of the time; this must keep the correction."""
    m = Memory()
    m.add("the region is Frankfurt", user_id="u")
    m.add("correction: the region is Ohio", user_id="u")   # auto-keyed to "the region is" -> supersede
    m.add("reminder: the region is Frankfurt", user_id="u")  # ECHO: old value restated (newest write)
    hits = m.search("region", filters={"user_id": "u"}, limit=3)["results"]
    top = hits[0]["memory"].lower()
    assert "ohio" in top and "frankfurt" not in top, f"echo revived the stale value: {top!r}"


def test_explicit_key_via_metadata():
    m = Memory()
    m.add("she prefers window seats", user_id="a", metadata={"mnemo_key": "a/seat", "mnemo_object": "window"})
    m.add("actually she prefers aisle now", user_id="a", metadata={"mnemo_key": "a/seat", "mnemo_object": "aisle"})
    m.add("book her a window seat", user_id="a", metadata={"mnemo_key": "a/seat", "mnemo_object": "window"})  # echo
    got = _val(m.search("she prefers", filters={"user_id": "a"}, limit=3)).lower()
    assert "aisle" in got and "window" not in got  # the correction held under an explicit key despite the echo


def test_add_returns_mem0_shape_with_event():
    m = Memory()
    r1 = m.add("the plan is Starter", user_id="u")
    assert set(r1["results"][0]) >= {"id", "memory", "event"}
    assert r1["results"][0]["event"] == "ADD"
    r2 = m.add("the plan is Pro", user_id="u")               # same key -> a correction
    assert r2["results"][0]["event"] == "UPDATE"


def test_search_result_shape():
    m = Memory()
    m.add("the timezone is UTC", user_id="u")
    r = m.search("timezone", filters={"user_id": "u"})["results"][0]
    assert set(r) >= {"id", "memory", "metadata"}
    assert r["user_id"] == "u"


def test_multi_user_isolation():
    m = Memory()
    m.add("the region is Frankfurt", user_id="alice")
    m.add("the region is Tokyo", user_id="bob")
    a = _val(m.search("region", filters={"user_id": "alice"}))
    b = _val(m.search("region", filters={"user_id": "bob"}))
    assert "Frankfurt" in a and "Tokyo" not in a
    assert "Tokyo" in b and "Frankfurt" not in b


def test_get_all_and_delete_all():
    m = Memory()
    m.add("fact one is here", user_id="u")
    m.add("fact two is here", user_id="u")
    assert len(m.get_all(user_id="u")["results"]) == 2
    m.delete_all(user_id="u")
    assert m.get_all(user_id="u")["results"] == []


def test_history_shows_the_correction_lineage():
    m = Memory()
    r = m.add("the color is blue", user_id="u")
    m.add("the color is green", user_id="u")
    hist = m.history(r["results"][0]["id"])
    objs = [h["object"] for h in hist]
    assert "blue" in objs and "green" in objs           # both the corrected and current value are in the lineage


def test_from_config_and_reset():
    m = Memory.from_config({"vector_store": {"config": {"path": None}}})
    m.add("the status is open", user_id="u")
    m.reset()
    assert m.get_all(user_id="u")["results"] == []


def test_unkeyable_text_stored_as_plain_memory():
    """Text with no 'X is Y' shape can't be auto-keyed — it must still store + retrieve (like mem0 no-infer),
    just without supersession."""
    m = Memory()
    m.add("remember to water the plants on Tuesdays", user_id="u")
    got = _val(m.search("water plants", filters={"user_id": "u"}))
    assert "plants" in got
