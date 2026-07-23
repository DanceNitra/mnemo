"""selection_integrity: surface an attacker who injects authentic-looking UNTRUSTED writes that reroute
which TRUSTED facts reach the top-k (Selection Integrity, arXiv 2606.12290). Flags displacement; no rewrite."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from inspeximus.core import Inspeximus, new_ed25519_keypair, attest

def _trusted_store():
    sk, pk = new_ed25519_keypair()
    m = Inspeximus(path=None)
    m.trust_seeds.add("key:" + pk)
    sig = attest("User's bank PIN is 1234", sk)
    m.remember("User's bank PIN is 1234", key="bank::pin", object="1234",
               attestation={"pubkey": pk, "sig": sig}, value=1.0)
    return m

def test_no_trust_root_says_unknown_not_safe():
    m = Inspeximus(path=None)
    m.remember("the bank pin matters")
    r = m.selection_integrity("bank pin", k=3)
    assert r["stable"] is None and "note" in r, r          # unknown (blind), NOT True/"safe"

def test_stable_when_no_untrusted_displacement():
    m = _trusted_store()
    r = m.selection_integrity("bank pin", k=3)
    assert r["stable"] is True and r["displaced"] == [], r

def test_untrusted_injection_displaces_trusted_fact():
    """High-value UNTRUSTED decoys steer the top-k so the trusted fact is pushed out -> flagged displaced."""
    m = _trusted_store()
    for i in range(8):
        m.remember(f"bank pin security reminder note number {i}", value=9.0)   # untrusted, out-ranks by value
    r = m.selection_integrity("bank pin", k=3)
    assert r["stable"] is False, r
    assert any("1234" in d["text"] for d in r["displaced"]), r          # the trusted fact was displaced
    assert len(r["untrusted_in_topk"]) >= 1, r                          # untrusted decoys occupy slots

def test_read_only():
    m = _trusted_store()
    before = len(m.items)
    m.selection_integrity("bank pin", k=3)
    assert len(m.items) == before, "selection_integrity must not write"

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
