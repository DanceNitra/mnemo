"""Witness pool: k-of-n co-signing made usable — a Witness refuses forks (persistently), collect_cosignatures
gathers signatures and surfaces refusals as split-view alarms, and it composes with verify_cosigned_anchor /
detect_split_view."""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from inspeximus.core import Inspeximus, _sha256_hex, _canon, _GENESIS
from inspeximus.witness_pool import Witness, collect_cosignatures

def _sth(n_writes, writes_tip, n_tomb=0, tomb_tip=_GENESIS):
    a = {"n_writes": n_writes, "writes_tip": writes_tip, "n_tombstones": n_tomb, "tombstones_tip": tomb_tip, "ts": 0.0}
    a["sth_hash"] = _sha256_hex(_canon({k: a[k] for k in ("n_writes","writes_tip","n_tombstones","tombstones_tip")}))
    return a

def test_kofn_happy_path():
    a = _sth(5, "aaa")
    W = [Witness() for _ in range(3)]
    out = collect_cosignatures("store1", a, W)
    assert len(out["cosignatures"]) == 3 and out["refused"] == [], out
    r = Inspeximus.verify_cosigned_anchor(a, out["cosignatures"], [w.public for w in W], threshold=2)
    assert r["ok"] and r["count"] == 3, r

def test_witness_refuses_fork():
    """A witness that co-signed head A refuses a same-size different-tip head B (the fork)."""
    A = _sth(5, "aaa"); B = _sth(5, "bbb")
    w = Witness()
    w.cosign("s", A)                                   # signs A
    out = collect_cosignatures("s", B, [w])            # asked to sign the fork B
    assert out["cosignatures"] == [] and len(out["refused"]) == 1, out
    assert "fork" in out["refused"][0]["reason"] or "split-view" in out["refused"][0]["reason"], out

def test_witness_refuses_rollback():
    prior = _sth(5, "aaa"); rolled = _sth(3, "ccc")
    w = Witness(); w.cosign("s", prior)
    out = collect_cosignatures("s", rolled, [w])
    assert out["cosignatures"] == [] and "rollback" in out["refused"][0]["reason"], out

def test_allows_honest_extension():
    w = Witness()
    w.cosign("s", _sth(5, "aaa"))
    out = collect_cosignatures("s", _sth(8, "ddd"), [w])   # bigger log, no local contradiction
    assert len(out["cosignatures"]) == 1 and out["refused"] == [], out

def test_persistence_survives_restart():
    """The fork-memory must survive a witness restart (else an operator restarts it and forks past it)."""
    with tempfile.TemporaryDirectory() as d:
        sp = os.path.join(d, "wit.json")
        sk, _ = __import__("inspeximus.core", fromlist=["new_ed25519_keypair"]).new_ed25519_keypair()
        w1 = Witness(secret_hex=sk, state_path=sp); w1.cosign("s", _sth(5, "aaa"))
        w2 = Witness(secret_hex=sk, state_path=sp)                 # "restart": same key, reload state
        assert w2.last_head("s") is not None, "state not reloaded"
        out = collect_cosignatures("s", _sth(5, "bbb"), [w2])     # fork after restart
        assert out["cosignatures"] == [] and out["refused"], "restarted witness must still refuse the fork"

def test_split_view_proof_from_pool():
    """A tricked/dishonest witness that signed two inconsistent heads -> detect_split_view proves the fork."""
    A = _sth(5, "aaa"); B = _sth(5, "bbb"); w = Witness()
    _, sigA = w.cosign("s", A)
    # bypass the witness's own guard (simulate a dishonest witness with no memory) by signing B fresh
    from inspeximus.core import witness_cosign
    sigB = witness_cosign(w._secret, B)
    r = Inspeximus.detect_split_view(A, [(w.public, sigA)], B, [(w.public, sigB)], [w.public])
    assert r["fork"] is True and w.public in r["evidence"], r

def test_secret_roundtrip_public():
    from inspeximus.core import new_ed25519_keypair
    sk, pk = new_ed25519_keypair()
    w = Witness(secret_hex=sk)
    assert w.public == pk, "derived public must match the minted public"

def test_http_witness_roundtrip():
    """Reference witness HTTP server: cosign over HTTP, and a fork gets a 409 refusal surfaced as an alarm."""
    import threading, socket, time
    from http.server import ThreadingHTTPServer
    from inspeximus.witness_server import _make_handler
    from inspeximus.witness_pool import http_witness
    w = Witness()
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(w))
    t = threading.Thread(target=httpd.serve_forever, daemon=True); t.start()
    time.sleep(0.2)
    try:
        url = f"http://127.0.0.1:{port}"
        A = _sth(5, "aaa"); B = _sth(5, "bbb")
        out = collect_cosignatures("s", A, [http_witness(url)])          # honest cosign over HTTP
        assert len(out["cosignatures"]) == 1 and out["cosignatures"][0][0] == w.public, out
        r = Inspeximus.verify_cosigned_anchor(A, out["cosignatures"], [w.public], threshold=1)
        assert r["ok"], r
        out2 = collect_cosignatures("s", B, [http_witness(url)])          # fork -> remote refuses (409)
        assert out2["cosignatures"] == [] and out2["refused"], out2
        assert "refused" in out2["refused"][0]["reason"].lower(), out2
    finally:
        httpd.shutdown()

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
