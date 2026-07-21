"""Core inspeximus behaviour — the load-bearing contract. Cloud-free, deterministic."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from inspeximus import Inspeximus


def test_remember_and_recall():
    m = Inspeximus()
    m.remember("the sky is blue")
    hits = m.recall("sky", k=3, mode="lexical")
    assert any("sky is blue" in h["text"] for h in hits)


def test_keyed_supersession_hides_stale_value():
    m = Inspeximus()
    m.remember("the region is us-east", key="cfg::region", object="us-east")
    m.remember("the region is eu-west", key="cfg::region", object="eu-west")
    hits = m.recall("region", k=6, mode="lexical")
    texts = " ".join(h["text"] for h in hits)
    assert "eu-west" in texts and "us-east" not in texts   # a corrected fact stops being recalled


def test_revert_restores_previous_value():
    m = Inspeximus()
    m.remember("v1", key="k", object="v1")
    m.remember("v2", key="k", object="v2")
    m.revert("k")
    cur = [r for r in m.items if r.get("key") == "k" and r.get("status") == "active"]
    assert cur and cur[0]["object"] == "v1"


def test_echo_guard_blocks_resurrection():
    m = Inspeximus(); m.echo_guard = True
    m.remember("region is us-east", key="k", object="us-east")
    m.remember("region is eu-west", key="k", object="eu-west")
    m.remember("region is us-east", key="k", object="us-east")   # echo of the retired value
    active = [r for r in m.items if r.get("key") == "k" and r.get("status") == "active"]
    assert len(active) == 1 and active[0]["object"] == "eu-west"


def test_forget_subject_erases_lineage():
    m = Inspeximus()
    root = m.remember("alice lives in brno", source={"doc": "alice"})
    m.remember("summary of alice", derived_from=[root], source={"doc": "alice"})
    res = m.forget_subject("alice")
    assert res["erased"] >= 1
    assert not any(r.get("status") == "active" and "alice" in (r.get("text") or "").lower() for r in m.items)


def test_verify_writes_clean_and_tamper():
    m = Inspeximus(receipts=True)
    m.remember("a"); m.remember("b")
    ok, problems = m.verify_writes()
    assert ok and not problems
    m.items[0]["text"] = "TAMPERED"                    # out-of-band edit
    ok2, problems2 = m.verify_writes()
    assert not ok2 and problems2


def test_consolidate_only_adds():
    m = Inspeximus()
    for i in range(20):
        m.remember(f"note {i} about topic alpha", value=1.0)
    before = len(m.items)
    m.consolidate()
    assert len(m.items) >= before                      # consolidation only adds a derived layer
