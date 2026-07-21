"""1.1.0 hardening: opt-in per-record size cap + the verify_writes footgun made visible. Opt-in = no default change."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from inspeximus import Inspeximus, new_receipt_keypair


def test_max_text_truncates_and_stamps():
    m = Inspeximus(max_text=10)
    mid = m.remember("x" * 5000)
    rec = [r for r in m.items if r["id"] == mid][0]
    assert len(rec["text"]) == 10
    assert rec["meta"]["truncated_from"] == 5000


def test_max_text_default_is_unbounded():
    m = Inspeximus()                                  # default None -> legacy behaviour
    mid = m.remember("y" * 5000)
    rec = [r for r in m.items if r["id"] == mid][0]
    assert len(rec["text"]) == 5000 and "truncated_from" not in rec["meta"]


def test_max_text_leaves_short_text_alone():
    m = Inspeximus(max_text=100)
    mid = m.remember("short")
    rec = [r for r in m.items if r["id"] == mid][0]
    assert rec["text"] == "short" and "truncated_from" not in rec["meta"]


def test_verify_writes_warn_unpinned_is_opt_in():
    sk, pk = new_receipt_keypair()
    m = Inspeximus(receipts=True, receipt_key=sk, receipt_pubkey=pk)
    m.remember("a")
    # default: signed store passes (byte-identical legacy behaviour)
    ok, problems = m.verify_writes()
    assert ok and not problems
    # opt-in warning: signatures present but no expected_pubkey -> surfaced as a problem
    ok2, problems2 = m.verify_writes(warn_unpinned=True)
    assert not ok2 and any("expected_pubkey not pinned" in p for p in problems2)
    # pinning resolves it
    ok3, _ = m.verify_writes(expected_pubkey=pk, warn_unpinned=True)
    assert ok3


def test_governance_report_states_signature_trust_level():
    sk, pk = new_receipt_keypair()
    m = Inspeximus(receipts=True, receipt_key=sk, receipt_pubkey=pk)
    m.remember("x", source={"doc": "s"}); m.forget_subject("s", request_id="r")
    unpinned = m.governance_report()
    assert "self-referential" in unpinned["proof"]["signature_authenticity"]
    pinned = m.governance_report(expected_pubkey=pk)
    assert pinned["proof"]["signature_authenticity"] == "pinned to expected_pubkey"
