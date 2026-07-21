"""forget_subject x DeletionManifest integration (1.8.0): registered app-side erasure targets are cascaded
and the returned manifest is honest by construction (complete only if EVERY store verified absent, leaking
stores NAMED). Motivated by the measured gap: an app-side vector-index copy survives every store's native
delete (erasure_fanout_probe 8/8) unless the fan-out is registered and erased with it."""
import os
import tempfile

import pytest

from inspeximus import Inspeximus
from inspeximus.deletion_manifest import DeletionManifest, ErasureTarget

SECRET = "type-1 diabetes"
SUBJECT = "user:alice"


class FakeIndex(ErasureTarget):
    """A stand-in for the app's external vector index: id -> payload text."""
    name = "app-vector-index"

    def __init__(self, leaky=False):
        self.rows = {}
        self.leaky = leaky

    def add(self, rid, text, subject):
        self.rows[rid] = {"text": text, "subject": subject}

    def erase(self, subject):
        if self.leaky:                      # simulates an unwired/broken purge
            return {"erased": 0}
        gone = [k for k, v in self.rows.items() if v["subject"] == subject]
        for k in gone:
            del self.rows[k]
        return {"erased": len(gone)}

    def still_recoverable(self, subject, values):
        blob = " ".join(v["text"] for v in self.rows.values()).lower()
        return any(x.lower() in blob for x in values if x)


@pytest.fixture()
def store(tmp_path):
    m = Inspeximus(path=str(tmp_path / "m.json"))
    m.remember(f"Alice's medical condition is {SECRET}.", key="alice::medical",
               object=SECRET, source={"doc": SUBJECT})
    m.remember("Bob likes tea.", key="bob::pref", source={"doc": "user:bob"})
    return m


def test_no_targets_keeps_old_contract(store):
    out = store.forget_subject(SUBJECT, request_id="r1")
    assert out["erased"] == 1 and "manifest" not in out


def test_wired_target_completes_and_chain_verifies(store):
    idx = FakeIndex()
    idx.add("v1", f"chunk: Alice's medical condition is {SECRET}.", SUBJECT)
    idx.add("v2", "chunk: Bob likes tea.", "user:bob")
    store.register_erasure_target(idx)
    out = store.forget_subject(SUBJECT, request_id="r2", basis="GDPR Art.17 request")
    man = out["manifest"]
    assert man["complete"] is True
    assert man["residual_targets"] == []
    assert [e["target"] for e in man["entries"]] == ["inspeximus-store", "app-vector-index"]
    assert all(e["verified_absent"] for e in man["entries"])
    ok, problems = DeletionManifest().verify(man)
    assert ok, problems
    # the unrelated subject's data is untouched
    assert "v2" in idx.rows


def test_leaky_target_is_named_not_hidden(store):
    idx = FakeIndex(leaky=True)
    idx.add("v1", f"chunk: Alice's medical condition is {SECRET}.", SUBJECT)
    store.register_erasure_target(idx)
    out = store.forget_subject(SUBJECT, request_id="r3")
    man = out["manifest"]
    assert man["complete"] is False
    assert man["residual_targets"] == ["app-vector-index"]
    # the store itself is clean even when the fan-out leaks
    self_entry = next(e for e in man["entries"] if e["target"] == "inspeximus-store")
    assert self_entry["verified_absent"] is True
    ok, _ = DeletionManifest().verify(man)
    assert ok


def test_values_are_captured_automatically(store):
    """No `values=` passed: the erased records' own text/object strings drive the residue check."""
    idx = FakeIndex(leaky=True)
    idx.add("v1", f"the patient has {SECRET}", SUBJECT)
    store.register_erasure_target(idx)
    man = store.forget_subject(SUBJECT)["manifest"]
    assert man["complete"] is False            # only detectable if captured values include the secret


def test_erroring_target_recorded_as_incomplete(store):
    class Boom(ErasureTarget):
        name = "boom"

        def erase(self, s):
            raise RuntimeError("connection refused")

        def still_recoverable(self, s, v):
            return False

    store.register_erasure_target(Boom())
    man = store.forget_subject(SUBJECT)["manifest"]
    assert man["complete"] is False and "boom" in man["residual_targets"]
    boom = next(e for e in man["entries"] if e["target"] == "boom")
    assert boom["error"] and "connection refused" in boom["error"]


def test_tenant_view_passthrough(tmp_path):
    m = Inspeximus(path=str(tmp_path / "t.json"))
    t = m.for_tenant("acme")
    t.remember(f"Alice's condition is {SECRET}.", key="a::c", object=SECRET, source={"doc": SUBJECT})
    m.register_erasure_target(FakeIndex())
    out = t.forget_subject(SUBJECT)
    assert out["erased"] == 1
