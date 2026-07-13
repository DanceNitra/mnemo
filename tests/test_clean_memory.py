"""1.3.0: clean-memory write-admission gate + inspector (admit / why_recalled / memory_report)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mnemo import Mnemo


def test_admit_stores_new_fact():
    m = Mnemo()
    r = m.admit("the database region is us-east")
    assert r["admitted"] is True and r["id"] and r["reason"] == "admitted"
    assert len(m.items) == 1


def test_admit_rejects_near_duplicate():
    m = Mnemo()
    a = m.admit("the database region is us-east")
    b = m.admit("the database region is us-east")          # exact repeat -> duplicate
    assert b["admitted"] is False and b["reason"] == "duplicate"
    assert b["duplicate_of"] == a["id"] and b["similarity"] >= 0.92
    assert len(m.items) == 1                                # NO 2nd copy stored


def test_admit_no_808_copies():
    m = Mnemo()
    for _ in range(50):
        m.admit("user prefers Telegram")
    active = [r for r in m.items if r.get("status") == "active"]
    assert len(active) == 1                                 # not 50 copies


def test_admit_rejects_junk():
    m = Mnemo()
    assert m.admit("")["reason"] == "empty"
    assert m.admit("ok")["reason"] == "too_short"
    assert m.admit("No sources were provided for this claim.")["reason"] == "non_content"
    assert m.admit("As an AI language model, I cannot help with that.")["reason"] == "non_content"
    assert len(m.items) == 0


def test_admit_value_update_is_not_duplicate():
    m = Mnemo()
    m.admit("the price is 100 dollars")
    r = m.admit("the price is 250 dollars")                 # value clash -> admitted, not a dup
    assert r["admitted"] is True
    assert len([x for x in m.items]) == 2


def test_admit_quality_opt_out():
    m = Mnemo()
    r = m.admit("ok", quality=False)                        # quality gate off -> short text allowed
    assert r["admitted"] is True


def test_why_recalled_breakdown():
    m = Mnemo()
    m.admit("the capital of France is Paris")
    m.admit("the Eiffel Tower is in Paris")
    rows = m.why_recalled("what city is the capital of France")
    assert isinstance(rows, list) and rows
    top = rows[0]
    for key in ("id", "semantic", "lexical", "effective_value", "good", "bad", "rank"):
        assert key in top
    assert top["rank"] == 1


def test_why_recalled_single_id():
    m = Mnemo()
    mid = m.admit("the capital of France is Paris")["id"]
    b = m.why_recalled("capital of France", id=mid)
    assert b["id"] == mid and b["surfaced"] is True and b["rank"] == 1
    assert m.why_recalled("x", id="nonexistent")["found"] is False


def test_memory_report():
    m = Mnemo()
    facts = ["the capital of France is Paris", "water boils at one hundred celsius",
             "the stock ticker for Apple is AAPL", "photosynthesis happens in chloroplasts",
             "mount Everest is the tallest mountain"]
    for f in facts:
        assert m.admit(f)["admitted"] is True             # lexically distinct -> all admitted
    for _ in range(10):
        m.admit("user prefers Telegram messaging")        # only one survives admit
    rep = m.memory_report()
    assert rep["active"] == 6 and rep["total"] == 6
    assert "episodic" in rep["by_type"]
    assert rep["redundant_estimate"] == 0                  # admit already de-duplicated
