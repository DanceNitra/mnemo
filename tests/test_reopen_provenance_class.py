"""Provenance-CLASS corroboration (marintkael's handed-back question, 1.9.5): distinct verified KEYS prove
distinctness, not epistemic independence — two keys wrapping the same upstream model/feed are two keys but one
source. So support_authorities can be a dict {pubkey: class_label}; the reopen threshold then counts DISTINCT
CLASSES, and keys sharing a class collapse to one. Honest limit: 'class' is a DECLARED grouping by whoever
curates the allowlist; the store enforces it but cannot verify two classes are causally independent."""
import pytest
inspeximus = pytest.importorskip("inspeximus")
crypto = pytest.importorskip("cryptography")
from inspeximus import Inspeximus, new_source_keypair, sign_support


def _ground(m, sk, pk, key, toward):
    return (pk, sign_support(sk, m.support_challenge_for(key, toward)))


def test_two_keys_same_class_do_not_corroborate(tmp_path):
    """Two allowlisted keys declared to share a provenance class = one source: never reaches k=2."""
    sk1, pk1 = new_source_keypair(); sk2, pk2 = new_source_keypair()
    m = Inspeximus(str(tmp_path / "m.json"), support_authorities={pk1: "gpt-wrapper", pk2: "gpt-wrapper"})
    m.remember("region is Frankfurt", key="a/region", object="Frankfurt")
    m.observe("Ohio", key="a/region", object="Ohio", support=[_ground(m, sk1, pk1, "a/region", "Ohio")])
    r = m.observe("Ohio", key="a/region", object="Ohio", support=[_ground(m, sk2, pk2, "a/region", "Ohio")])
    assert r["reopened"] is False and r["pending"] == 1        # both in one class -> one distinct source
    assert m.reopened() == []


def test_two_distinct_classes_reopen(tmp_path):
    sk1, pk1 = new_source_keypair(); sk2, pk2 = new_source_keypair()
    m = Inspeximus(str(tmp_path / "m.json"), support_authorities={pk1: "human-audit", pk2: "independent-dmrg"})
    m.remember("region is Frankfurt", key="a/region", object="Frankfurt")
    m.observe("Ohio", key="a/region", object="Ohio", support=[_ground(m, sk1, pk1, "a/region", "Ohio")])
    r = m.observe("Ohio", key="a/region", object="Ohio", support=[_ground(m, sk2, pk2, "a/region", "Ohio")])
    assert r["reopened"] is True                               # two distinct classes -> corroborated


def test_third_key_new_class_tips_when_first_two_shared(tmp_path):
    """One class contributes at most one vote; a genuinely distinct class is what finally tips k=2."""
    sk1, pk1 = new_source_keypair(); sk2, pk2 = new_source_keypair(); sk3, pk3 = new_source_keypair()
    m = Inspeximus(str(tmp_path / "m.json"),
              support_authorities={pk1: "feedA", pk2: "feedA", pk3: "feedB"})
    m.remember("v is X", key="k/v", object="X")
    m.observe("Y", key="k/v", object="Y", support=[_ground(m, sk1, pk1, "k/v", "Y")])
    r2 = m.observe("Y", key="k/v", object="Y", support=[_ground(m, sk2, pk2, "k/v", "Y")])   # same class
    assert r2["reopened"] is False and r2["pending"] == 1
    r3 = m.observe("Y", key="k/v", object="Y", support=[_ground(m, sk3, pk3, "k/v", "Y")])   # new class
    assert r3["reopened"] is True


def test_dict_mode_still_rejects_self_minted_and_strings(tmp_path):
    sk1, pk1 = new_source_keypair()
    m = Inspeximus(str(tmp_path / "m.json"), support_authorities={pk1: "trusted"})
    m.remember("x is 1", key="k/x", object="1")
    esk, epk = new_source_keypair()                            # attacker key, class unknown / not allowlisted
    r1 = m.observe("2", key="k/x", object="2", support=[_ground(m, esk, epk, "k/x", "2")])
    r2 = m.observe("2", key="k/x", object="2", support=["ref:A"])
    assert r1["reopened"] is False and r2["reopened"] is False and m.reopened() == []
