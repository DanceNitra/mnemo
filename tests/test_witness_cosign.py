"""Witness co-signing = the gossip layer that turns single-timeline tamper-evidence into SPLIT-VIEW
detection: a compromised operator cannot show divergent histories to different clients without getting
k independent witnesses to co-sign the fork, and honest witnesses refuse. Includes the split-view test."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from inspeximus.core import (Inspeximus, new_ed25519_keypair, witness_cosign,
                             _sha256_hex, _canon, _GENESIS)

def _sth(n_writes, writes_tip, n_tomb=0, tomb_tip=_GENESIS):
    """Build a signed-tree-head dict with the SAME sth_hash formula anchor() uses."""
    a = {"n_writes": n_writes, "writes_tip": writes_tip,
         "n_tombstones": n_tomb, "tombstones_tip": tomb_tip, "ts": 0.0}
    a["sth_hash"] = _sha256_hex(_canon({k: a[k] for k in
                    ("n_writes", "writes_tip", "n_tombstones", "tombstones_tip")}))
    return a

def test_keypair():
    sk, pk = new_ed25519_keypair()
    assert len(sk) == 64 and len(pk) == 64 and sk != pk

def test_kofn_happy_path():
    a = _sth(5, "aaa")
    W = [new_ed25519_keypair() for _ in range(3)]
    cosigs = [(pk, witness_cosign(sk, a)) for sk, pk in W]
    r = Inspeximus.verify_cosigned_anchor(a, cosigs, [pk for _, pk in W], threshold=2)
    assert r["ok"] and r["count"] == 3, r

def test_threshold_not_met():
    a = _sth(5, "aaa"); W = [new_ed25519_keypair() for _ in range(3)]
    cosigs = [(W[0][1], witness_cosign(W[0][0], a))]          # only 1 of 3 signs
    r = Inspeximus.verify_cosigned_anchor(a, cosigs, [pk for _, pk in W], threshold=2)
    assert not r["ok"] and r["count"] == 1, r

def test_non_allowlisted_ignored():
    a = _sth(5, "aaa"); good = new_ed25519_keypair(); rogue = new_ed25519_keypair()
    cosigs = [(rogue[1], witness_cosign(rogue[0], a))]        # a valid sig, but not on the allowlist
    r = Inspeximus.verify_cosigned_anchor(a, cosigs, [good[1]], threshold=1)
    assert not r["ok"] and r["count"] == 0, r

def test_forged_signature_rejected():
    a = _sth(5, "aaa"); W = new_ed25519_keypair()
    r = Inspeximus.verify_cosigned_anchor(a, [(W[1], "00" * 64)], [W[1]], threshold=1)
    assert not r["ok"] and r["count"] == 0, r

def test_class_collapses_sybil():
    a = _sth(5, "aaa"); w1 = new_ed25519_keypair(); w2 = new_ed25519_keypair()
    cosigs = [(w1[1], witness_cosign(w1[0], a)), (w2[1], witness_cosign(w2[0], a))]
    allow = {w1[1]: "org-X", w2[1]: "org-X"}                  # two keys, one declared class -> one vote
    r = Inspeximus.verify_cosigned_anchor(a, cosigs, allow, threshold=1)
    assert r["ok"] and r["count"] == 1, r                    # collapsed to a single class

def test_witness_refuses_rollback():
    prior = _sth(5, "aaa"); rolled = _sth(3, "ccc"); sk, _ = new_ed25519_keypair()
    try:
        witness_cosign(sk, rolled, prior_anchor=prior); assert False, "should refuse rollback"
    except ValueError as e:
        assert "rollback" in str(e), e

def test_witness_refuses_same_size_fork():
    prior = _sth(5, "aaa"); fork = _sth(5, "bbb"); sk, _ = new_ed25519_keypair()
    try:
        witness_cosign(sk, fork, prior_anchor=prior); assert False, "should refuse fork"
    except ValueError as e:
        assert "fork" in str(e) or "split-view" in str(e), e

def test_witness_allows_honest_extension():
    prior = _sth(5, "aaa"); grown = _sth(8, "ddd"); sk, _ = new_ed25519_keypair()
    sig = witness_cosign(sk, grown, prior_anchor=prior)      # bigger log, no local contradiction -> allowed
    assert len(sig) == 128

def test_split_view_detected():
    """THE split-view test: operator forks — two heads at the SAME size, DIFFERENT tip. A witness (tricked
    into signing without its prior, or dishonest) co-signed both; an auditor comparing the two co-signed
    heads gets cryptographic fork proof."""
    A = _sth(5, "aaa"); B = _sth(5, "bbb")                   # same n_writes, different tip = a fork
    W = new_ed25519_keypair()
    sigA = witness_cosign(W[0], A)                           # no prior -> the witness is tricked into signing
    sigB = witness_cosign(W[0], B)
    r = Inspeximus.detect_split_view(A, [(W[1], sigA)], B, [(W[1], sigB)], [W[1]])
    assert r["fork"] is True, r
    assert W[1] in r["evidence"], r
    assert "n_writes" in r["at"], r
    assert r["both_cosigned"] is True, r

def test_no_fork_on_identical_head():
    A = _sth(5, "aaa"); W = new_ed25519_keypair()
    sig = witness_cosign(W[0], A)
    r = Inspeximus.detect_split_view(A, [(W[1], sig)], A, [(W[1], sig)], [W[1]])
    assert r["fork"] is False and r["inconsistent"] is False, r

def test_no_common_witness_no_proof():
    """Two inconsistent heads but signed by DIFFERENT witnesses -> inconsistent, but no single-witness proof."""
    A = _sth(5, "aaa"); B = _sth(5, "bbb"); w1 = new_ed25519_keypair(); w2 = new_ed25519_keypair()
    r = Inspeximus.detect_split_view(A, [(w1[1], witness_cosign(w1[0], A))],
                                     B, [(w2[1], witness_cosign(w2[0], B))], [w1[1], w2[1]])
    assert r["inconsistent"] is True and r["fork"] is False and r["evidence"] == [], r

def test_real_store_anchor_cosign():
    m = Inspeximus(path=None, receipts=True)
    m.remember("the sky is blue", key="sky::color", object="blue")
    m.remember("water boils at 100C", key="water::boil", object="100")
    a = m.anchor()
    assert a.get("sth_hash"), a
    W = [new_ed25519_keypair() for _ in range(2)]
    cosigs = [(pk, witness_cosign(sk, a)) for sk, pk in W]
    r = Inspeximus.verify_cosigned_anchor(a, cosigs, [pk for _, pk in W], threshold=2)
    assert r["ok"] and r["count"] == 2, r

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS {fn.__name__}"); p += 1
        except AssertionError as e:
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{p}/{len(fns)} passed")
    sys.exit(0 if p == len(fns) else 1)
