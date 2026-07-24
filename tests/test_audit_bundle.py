"""Portable audit bundle: build a content-free, self-verifying record-keeping artifact and verify it OFFLINE
(no store, no receipt key). A post-export tamper must fail; witness co-signatures give the operator-adversarial
check."""
import sys, os, json, copy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from inspeximus.core import Inspeximus, _sha256_hex, _canon
from inspeximus.audit_bundle import build_bundle, verify_bundle, BUNDLE_KIND


def _populated():
    m = Inspeximus(path=None, receipts=True)
    m.remember("deploy channel is BLUE-9", key="deploy::channel", object="BLUE-9")
    m.remember("deploy channel is RED-2", key="deploy::channel", object="RED-2")      # supersedes
    m.remember("customer 42 email is a@b.com", key="cust42::email", object="a@b.com")
    m.forget(where=lambda r: r.get("key") == "cust42::email")                          # tombstone(s)
    return m


def test_build_and_verify_ok():
    b = build_bundle(_populated())
    assert b["kind"] == BUNDLE_KIND
    res = verify_bundle(b)
    assert res["ok"], res
    assert res["summary"]["writes"] >= 3 and res["summary"]["erasures"] >= 1, res["summary"]


def test_bundle_is_content_free():
    """No memory TEXT may appear in the exported artifact (only hashes + surrogate ids)."""
    b = build_bundle(_populated())
    blob = json.dumps(b)
    for secret in ("BLUE-9", "RED-2", "a@b.com", "deploy channel", "customer 42"):
        assert secret not in blob, f"content leaked into bundle: {secret!r}"


def test_tamper_bundle_hash_detected():
    b = build_bundle(_populated())
    b["generated_ts"] = (b.get("generated_ts") or 0) + 999          # alter a field after export
    res = verify_bundle(b)
    assert not res["ok"] and any("bundle_hash" in p for p in res["problems"]), res


def test_tamper_write_chain_detected():
    """Flip a write receipt's hash AND re-seal the bundle_hash -- the chain re-walk must still catch it."""
    b = build_bundle(_populated())
    b["write_chain"][0]["hash"] = "deadbeef" + b["write_chain"][0]["hash"][8:]
    b["bundle_hash"] = _sha256_hex(_canon({k: v for k, v in b.items() if k != "bundle_hash"}))  # re-seal
    res = verify_bundle(b)
    assert not res["ok"] and any("write chain" in p for p in res["problems"]), res


def test_dropped_tombstone_detected():
    """Hiding a real erasure by dropping its tombstone breaks the chain/count vs the anchor."""
    b = build_bundle(_populated())
    if b["tombstone_chain"]:
        b["tombstone_chain"] = b["tombstone_chain"][:-1]
        b["bundle_hash"] = _sha256_hex(_canon({k: v for k, v in b.items() if k != "bundle_hash"}))
        res = verify_bundle(b)
        assert not res["ok"] and any("tombstone" in p for p in res["problems"]), res


def test_witness_cosigned_operator_adversarial():
    from inspeximus.witness_pool import Witness
    w = Witness()
    m = _populated()
    b = build_bundle(m, sign=lambda digest: None)          # sign hook unused here; cosign the anchor via pool
    # attach a real witness co-signature to the anchor, the way collect_cosignatures would
    from inspeximus.core import witness_cosign
    sig = witness_cosign(w._secret, b["anchor"])
    b["anchor"]["cosignatures"] = [(w.public, sig)]
    b["bundle_hash"] = _sha256_hex(_canon({k: v for k, v in b.items() if k != "bundle_hash"}))
    res = verify_bundle(b, witnesses=[w.public], threshold=1)
    assert res["ok"] and res["summary"]["operator_adversarial"], res


def test_reject_non_bundle():
    assert verify_bundle({"hello": "world"})["ok"] is False


def test_cli_build_and_verify(tmp_path):
    """The operator/auditor contract over the shell: --receipts writes a chain, audit-build exports it,
    audit-verify PASSes offline (exit 0), and a post-export tamper FAILs (exit 1)."""
    import os, json as _json
    from inspeximus.cli import main
    store = str(tmp_path / "store.json")
    bundle = str(tmp_path / "bundle.json")
    os.environ["INSPEXIMUS_PATH"] = store
    try:
        assert main(["--receipts", "remember", "channel is BLUE", "--key", "ch", "--object", "BLUE"]) == 0
        assert main(["--receipts", "remember", "channel is RED", "--key", "ch", "--object", "RED"]) == 0
        assert main(["audit-build", "--out", bundle]) == 0
        assert main(["audit-verify", bundle]) == 0
        b = _json.load(open(bundle)); assert b["anchor"]["n_writes"] == 2, b["anchor"]
        b["generated_ts"] = (b.get("generated_ts") or 0) + 1                 # tamper
        _json.dump(b, open(bundle, "w"))
        assert main(["audit-verify", bundle]) == 1
    finally:
        os.environ.pop("INSPEXIMUS_PATH", None)


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
