"""Cross-store erasure: DeletionManifest + ErasureAuditor. Deterministic fake embedder (no network)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from inspeximus import Inspeximus
from inspeximus.deletion_manifest import DeletionManifest, ErasureTarget
from inspeximus.erasure_auditor import (ErasureAuditor, TextStoreProbe, VectorIndexProbe, KVCacheProbe)


def _fake_embed(text):
    """A deterministic bag-of-words vector over a fixed vocab — enough for NN-inversion tests, no network."""
    vocab = ["diabetes", "epilepsy", "cancer", "alice", "bob", "condition", "medical", "is", "the", "region"]
    t = text.lower()
    return [float(t.count(w)) for w in vocab] + [float(len(t) % 7)]


# ---- DeletionManifest ----
class _StoreT(ErasureTarget):
    name = "store"
    def __init__(self, m): self.m = m
    def erase(self, subject): return {"erased": self.m.forget_subject(subject)["erased"]}
    def still_recoverable(self, subject, values):
        a = " ".join(r.get("text","") for r in self.m.items if r.get("status")=="active").lower()
        return any(v.lower() in a for v in values)

class _LeakyIndex(ErasureTarget):
    name = "index"
    def __init__(self, purges): self.rows=[]; self.purges=purges
    def add(self, s, t): self.rows.append((s,t))
    def erase(self, subject):
        if self.purges: self.rows=[(s,t) for (s,t) in self.rows if s!=subject]
        return {"erased": 0 if not self.purges else 1}
    def still_recoverable(self, subject, values):
        b=" ".join(t for (s,t) in self.rows if s==subject).lower(); return any(v.lower() in b for v in values)


def test_manifest_reports_incomplete_when_a_store_leaks():
    m = Inspeximus(); m.remember("alice condition is diabetes", source={"doc":"alice"})
    idx = _LeakyIndex(purges=False); idx.add("alice", "alice condition is diabetes")
    man = DeletionManifest().register(_StoreT(m)).register(idx)
    r = man.execute("alice", values=["diabetes"])
    assert r["complete"] is False and r["residual_targets"] == ["index"]


def test_manifest_complete_and_tamper_evident():
    m = Inspeximus(); m.remember("bob condition is cancer", source={"doc":"bob"})
    idx = _LeakyIndex(purges=True); idx.add("bob", "bob condition is cancer")
    man = DeletionManifest().register(_StoreT(m)).register(idx)
    r = man.execute("bob", values=["cancer"])
    assert r["complete"] is True
    ok, _ = man.verify(r); assert ok
    r["entries"][0]["verified_absent"] = not r["entries"][0]["verified_absent"]   # tamper
    ok2, problems = man.verify(r); assert not ok2 and problems


# ---- ErasureAuditor ----
def test_auditor_flags_vector_log_cache_after_naive_delete():
    vindex = VectorIndexProbe("vector", _fake_embed)
    vindex.add("alice", "alice medical condition is diabetes")     # embedding survives
    aud = (ErasureAuditor()
           .register(TextStoreProbe("log", ["query alice condition -> diabetes"]))
           .register(vindex)
           .register(KVCacheProbe("cache", {"k": "alice condition diabetes"})))
    rep = aud.audit("alice", ["diabetes"], candidates=["diabetes", "epilepsy", "cancer"],
                    template="alice medical condition is {value}")
    assert rep["erasure_verified"] is False
    assert set(rep["leaking_stores"]) == {"log", "vector", "cache"}


def test_auditor_verifies_when_all_purged():
    aud = (ErasureAuditor()
           .register(TextStoreProbe("log", []))
           .register(KVCacheProbe("cache", {})))
    rep = aud.audit("alice", ["diabetes"])
    assert rep["erasure_verified"] is True and rep["leaking_stores"] == []


def test_forget_dry_run_previews_without_deleting():
    """The safety valve: dry_run=True returns a preview (with a text sample) and deletes NOTHING."""
    m = Inspeximus(receipts=True)
    for t in ["secret token abc", "public note", "secret key xyz", "another public"]:
        m.remember(t)
    n = len(m.items); t_before = len(m._tombstones)
    dry = m.forget(where=lambda r: "secret" in r["text"], dry_run=True)
    assert dry["dry_run"] and dry["would_forget"] == 2, dry
    assert {s["text"] for s in dry["sample"]} == {"secret token abc", "secret key xyz"}, dry["sample"]
    assert len(m.items) == n and len(m._tombstones) == t_before, "dry_run must not delete or tombstone"
    # then a real forget on the same selector actually deletes + tombstones
    real = m.forget(where=lambda r: "secret" in r["text"])
    assert real["forgotten"] == 2 and len(m.items) == n - 2 and len(m._tombstones) == t_before + 2


def test_cli_forget_dry_run(tmp_path):
    import os as _os
    from inspeximus.cli import main
    _os.environ["INSPEXIMUS_PATH"] = str(tmp_path / "s.json")
    try:
        assert main(["remember", "delete me please", "--key", "k"]) == 0
        assert main(["forget", "--contains", "delete", "--dry-run"]) == 0     # preview, exit 0
        from inspeximus import Inspeximus as _I
        assert any(r.get("status") == "active" for r in _I(path=str(tmp_path / "s.json")).items)  # nothing deleted
        assert main(["forget", "--contains", "delete"]) == 0                  # now really delete
    finally:
        _os.environ.pop("INSPEXIMUS_PATH", None)
