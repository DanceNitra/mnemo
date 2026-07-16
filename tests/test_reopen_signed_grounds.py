"""Signed-grounds read-path reopen (marintkael round 3, r/RAG 2026-07-16): novelty-of-support is spoofable
because support strings ride the attacker-owned read path. When `support_authorities` (an allowlist of Ed25519
public keys held off the content path) is set, a novel support ground corroborates a reopen ONLY if it carries
a valid signature by an allowlisted authority over Mnemo.support_challenge_for(key, toward) — which binds the
CURRENT record id + tenant (anti-replay). Independence is then Sybil-resistance RELATIVE TO THE ALLOWLIST:
self-minted keys/strings count zero. Honest limits (gate-confirmed): distinct keys prove distinctness NOT
epistemic independence; attests SOURCE not TRUTH; the allowlist administrator is the steward. cryptography-gated."""
import pytest
mnemo = pytest.importorskip("mnemo")
crypto = pytest.importorskip("cryptography")
from mnemo import Mnemo, new_source_keypair, sign_support


def _store(tmp_path, authorities):
    return Mnemo(str(tmp_path / "m.json"), support_authorities=authorities)


def _ground(m, sk, pk, key, toward):
    return (pk, sign_support(sk, m.support_challenge_for(key, toward)))


def test_two_distinct_signed_authorities_reopen(tmp_path):
    sk1, pk1 = new_source_keypair(); sk2, pk2 = new_source_keypair()
    m = _store(tmp_path, [pk1, pk2])
    m.remember("the region is Frankfurt", key="a/region", object="Frankfurt")
    r1 = m.observe("Ohio", key="a/region", object="Ohio", support=[_ground(m, sk1, pk1, "a/region", "Ohio")])
    assert r1["reopened"] is False and r1["pending"] == 1
    r2 = m.observe("Ohio", key="a/region", object="Ohio", support=[_ground(m, sk2, pk2, "a/region", "Ohio")])
    assert r2["reopened"] is True and m.reopened()[0]["reason"] == "signed_support_contradiction"


def test_fabricated_string_grounds_do_not_corroborate(tmp_path):
    sk1, pk1 = new_source_keypair()
    m = _store(tmp_path, [pk1])
    m.remember("color is green", key="u/color", object="green")
    for g in ["ref:A", "ref:B", "ref:C", "ref:D"]:
        r = m.observe("blue", key="u/color", object="blue", support=[g])
        assert r["reopened"] is False
    assert m.reopened() == []


def test_self_minted_keypairs_count_zero(tmp_path):
    """The attacker mints their OWN keypairs (not allowlisted) and signs correctly — must count zero, so free
    key generation no longer manufactures 'independent' witnesses (Sybil resistance relative to the allowlist)."""
    _, pk1 = new_source_keypair()
    m = _store(tmp_path, [pk1])
    m.remember("y is 1", key="k/y", object="1")
    for _ in range(4):
        esk, epk = new_source_keypair()                       # a fresh, valid, but non-allowlisted key
        r = m.observe("2", key="k/y", object="2", support=[_ground(m, esk, epk, "k/y", "2")])
        assert r["reopened"] is False and r["pending"] == 0
    assert m.reopened() == []


def test_same_authority_twice_does_not_corroborate(tmp_path):
    sk1, pk1 = new_source_keypair()
    m = _store(tmp_path, [pk1, "otherkey"])
    m.remember("v is A", key="k/v", object="A")
    for _ in range(4):
        r = m.observe("B", key="k/v", object="B", support=[_ground(m, sk1, pk1, "k/v", "B")])
        assert r["reopened"] is False and r["pending"] == 1
    assert m.reopened() == []


def test_no_replay_across_value(tmp_path):
    sk1, pk1 = new_source_keypair()
    m = _store(tmp_path, [pk1])
    m.remember("region is Frankfurt", key="a/region", object="Frankfurt")
    sig_ohio = sign_support(sk1, m.support_challenge_for("a/region", "Ohio"))
    r = m.observe("Berlin", key="a/region", object="Berlin", support=[(pk1, sig_ohio)])   # bound to Ohio
    assert r["reopened"] is False and r["pending"] == 0


def test_no_replay_across_time_after_value_returns(tmp_path):
    """The gate's sharpest catch: a captured signature must not replay after the value legitimately changes and
    changes back, because the challenge binds the CURRENT record id."""
    sk1, pk1 = new_source_keypair(); sk2, pk2 = new_source_keypair()
    m = _store(tmp_path, [pk1, pk2])
    m.remember("cfg is X", key="k/cfg", object="X")
    sig_captured = sign_support(sk1, m.support_challenge_for("k/cfg", "Y"))   # captured while current record = X
    m.remember("cfg is Y", key="k/cfg", object="Y")                          # legitimate change X->Y
    m.remember("cfg is X", key="k/cfg", object="X")                          # ...and back to X (new record id)
    r = m.observe("Y", key="k/cfg", object="Y", support=[(pk1, sig_captured)])   # replay the stale signature
    assert r["reopened"] is False and r["pending"] == 0                      # bound to the OLD record id -> void


def test_empty_allowlist_is_fail_closed(tmp_path):
    """support_authorities=[] is signed mode with no trusted keys: nothing verifies, no fall-through to strings."""
    m = Mnemo(str(tmp_path / "m.json"), support_authorities=[])
    assert m.support_authorities == []
    m.remember("x is 1", key="k/x", object="1")
    m.observe("2", key="k/x", object="2", support=["ref:A"])
    r = m.observe("2", key="k/x", object="2", support=["ref:B"])
    assert r["reopened"] is False                                            # strings never satisfy a signed gate
    assert m.reopened() == []


def test_authorities_none_is_legacy_string_mode(tmp_path):
    m = Mnemo(str(tmp_path / "m.json"))
    assert m.support_authorities is None
    m.remember("region is Frankfurt", key="a/region", object="Frankfurt")
    m.observe("Ohio", key="a/region", object="Ohio", support="ground-1")
    r = m.observe("Ohio", key="a/region", object="Ohio", support="ground-2")
    assert r["reopened"] is True                                             # two distinct strings reopen (legacy)


def test_signed_value_obscuring_revert(tmp_path):
    sk1, pk1 = new_source_keypair(); sk2, pk2 = new_source_keypair()
    m = _store(tmp_path, [pk1, pk2])
    m.remember("plan is A", key="p/plan", object="A")
    m.remember("plan is B", key="p/plan", object="B")
    m.observe("go back", key="p/plan", object=None, support=[_ground(m, sk1, pk1, "p/plan", None)])
    r = m.observe("go back", key="p/plan", object=None, support=[_ground(m, sk2, pk2, "p/plan", None)])
    assert r["reopened"] is True and r["surfaced_prior"] == "A"
