"""Tenant isolation + PII layer (1.6.0). Zero-dependency; run with `python -m pytest tests/test_tenant_pii.py`."""
import time

from mnemo import Mnemo, detect_pii, redact_pii


# ── hard tenant isolation ────────────────────────────────────────────────────

def test_recall_never_crosses_tenants():
    # one physical store, two tenant views sharing it (Mnemo.for_tenant)
    store = Mnemo()
    a = store.for_tenant("acme")
    b = store.for_tenant("globex")
    a.remember("acme deploy key is ACME-SECRET-123", key="deploy::key", object="ACME-SECRET-123")
    b.remember("globex deploy key is GLOBEX-SECRET-999", key="deploy::key", object="GLOBEX-SECRET-999")
    ra = a.recall("deploy key", k=10)
    rb = b.recall("deploy key", k=10)
    assert len(ra) == 1 and "ACME-SECRET-123" in ra[0]["text"]
    assert len(rb) == 1 and "GLOBEX-SECRET-999" in rb[0]["text"]
    assert all("GLOBEX" not in x["text"] for x in ra)
    assert all("ACME" not in x["text"] for x in rb)
    # one shared items list, no clobber
    assert len(store.items) == 2


def test_bound_constructor_own_file_isolation():
    # the simple model: Mnemo(tenant=...) with its own file is trivially isolated
    import tempfile, os
    d = tempfile.mkdtemp()
    a = Mnemo(path=os.path.join(d, "acme.json"), tenant="acme")
    a.remember("acme only")
    got = a.recall("acme", k=5)
    assert len(got) == 1 and got[0].get("text") == "acme only"


def test_same_key_does_not_supersede_across_tenants():
    store = Mnemo()
    a = store.for_tenant("t1")
    b = store.for_tenant("t2")
    a.remember("plan is pro", key="billing::plan", object="pro")
    b.remember("plan is free", key="billing::plan", object="free")   # must NOT retire t1's active row
    actives = [r for r in store.items if r.get("status") == "active"]
    assert len(actives) == 2
    # within a tenant, keyed supersession still works
    a.remember("plan is enterprise", key="billing::plan", object="enterprise")
    ra = a.recall("plan", k=10)
    assert len(ra) == 1 and "enterprise" in ra[0]["text"]
    rb = b.recall("plan", k=10)
    assert len(rb) == 1 and "free" in rb[0]["text"]           # t2 untouched


def test_unbound_store_is_admin_view():
    store = Mnemo()
    store.for_tenant("t1").remember("t1 fact alpha")
    store.for_tenant("t2").remember("t2 fact beta")
    seen = store.recall("fact", k=10)                         # unbound parent sees everything
    texts = " ".join(x["text"] for x in seen)
    assert "alpha" in texts and "beta" in texts


def test_forget_subject_is_tenant_scoped():
    store = Mnemo()
    a = store.for_tenant("t1")
    b = store.for_tenant("t2")
    a.remember("shared-subject data A", source={"doc": "user-42"})
    b.remember("shared-subject data B", source={"doc": "user-42"})
    res = a.forget_subject("user-42")     # only t1's row
    assert res["erased"] == 1
    assert len(store.items) == 1 and store.items[0].get("tenant") == "t2"


def test_consolidation_does_not_cross_tenants():
    # The dream pass (consolidate) links/dedups/supersedes; on a tenant view it must not touch other tenants.
    store = Mnemo()
    a = store.for_tenant("t1")
    b = store.for_tenant("t2")
    phrase = "restart the api gateway nightly at midnight utc per the runbook"
    a.remember("t1: " + phrase)
    b.remember("t2: " + phrase)            # near-duplicate across tenants -> would link if unscoped
    a.consolidate(dup_threshold=0.5)
    # no t1 row may link to a t2 row
    t2_ids = {r["id"] for r in store.items if r.get("tenant") == "t2"}
    for r in store.items:
        if r.get("tenant") == "t1":
            assert not (set(r.get("links") or []) & t2_ids)
    # and t2's row is untouched (still active, no foreign toggle pointer)
    t2row = [r for r in store.items if r.get("tenant") == "t2"][0]
    assert t2row["status"] == "active"


def test_unbound_consolidate_links_across_when_no_tenants():
    # severe-test control: without tenants, the SAME corpus DOES link (proves the guard above prevents a real leak)
    m = Mnemo()
    phrase = "restart the api gateway nightly at midnight utc per the runbook"
    m.remember("alpha: " + phrase)
    m.remember("beta: " + phrase)
    m.consolidate(dup_threshold=0.5)
    assert sum(len(r.get("links") or []) for r in m.items) > 0


def test_legacy_unbound_is_byte_identical():
    # No tenant anywhere -> no `tenant` key stamped, legacy supersession intact.
    m = Mnemo()
    m.remember("timeout setting is short", key="cfg::timeout", object="short")
    m.remember("timeout setting is long", key="cfg::timeout", object="long")
    got = m.recall("timeout setting", k=10)
    assert len(got) == 1 and got[0]["text"].endswith("long")
    assert all("tenant" not in r for r in m.items)


# ── PII detection + redaction ────────────────────────────────────────────────

def test_detect_pii_types():
    d = detect_pii("mail me at jane.doe@acme.io or call 555-123-4567, ssn 123-45-6789")
    assert "email" in d and "jane.doe@acme.io" in d["email"]
    assert "ssn" in d and "123-45-6789" in d["ssn"]
    assert "phone" in d


def test_ssn_not_eaten_by_phone():
    # specific pattern (SSN) must claim the span before the broad phone pattern
    d = detect_pii("ssn 123-45-6789")
    assert d.get("ssn") == ["123-45-6789"]
    assert "phone" not in d


def test_redact_pii_masks_and_counts():
    masked, counts = redact_pii("write to bob@x.com now")
    assert "bob@x.com" not in masked and "[EMAIL]" in masked
    assert counts.get("email") == 1


def test_remember_tags_pii_when_detect_on():
    m = Mnemo(pii_detect=True)
    mid = m.remember("customer email is carol@corp.com")
    rec = [r for r in m.items if r["id"] == mid][0]
    assert rec.get("pii") == ["email"]


def test_remember_pii_override():
    m = Mnemo()
    mid = m.remember("no obvious pii here", pii=["custom_id"])
    rec = [r for r in m.items if r["id"] == mid][0]
    assert rec.get("pii") == ["custom_id"]
    # pii=False suppresses even with detect on
    m2 = Mnemo(pii_detect=True)
    mid2 = m2.remember("email a@b.com", pii=False)
    rec2 = [r for r in m2.items if r["id"] == mid2][0]
    assert "pii" not in rec2


def test_recall_redact_pii_masks_return_not_store():
    m = Mnemo(pii_detect=True)
    m.remember("the account owner is dave@bank.com")
    got = m.recall("account owner", k=5, redact_pii=True)
    assert got and "dave@bank.com" not in got[0]["text"] and "[EMAIL]" in got[0]["text"]
    assert got[0].get("pii_masked", {}).get("email") == 1
    # stored record is untouched
    assert any("dave@bank.com" in r["text"] for r in m.items)


def test_pii_report_and_forget_pii():
    m = Mnemo(pii_detect=True)
    m.remember("email one: a@x.com")
    m.remember("email two: b@y.com")
    m.remember("no pii in this one at all")
    rep = m.pii_report()
    assert rep["records_with_pii"] == 2 and rep["by_type"]["email"] == 2
    res = m.forget_pii(types=["email"])
    assert res["erased"] == 2 and res["tombstones"] == 2
    assert m.pii_report()["records_with_pii"] == 0
    # non-PII record survives
    assert any("no pii" in r["text"] for r in m.items)


def test_forget_pii_is_tenant_scoped():
    store = Mnemo(pii_detect=True)
    a = store.for_tenant("t1")
    b = store.for_tenant("t2")
    a.remember("t1 email a@x.com")
    b.remember("t2 email b@y.com")
    res = a.forget_pii()
    assert res["erased"] == 1
    assert len(store.items) == 1 and store.items[0].get("tenant") == "t2"
    # t2's PII view is intact
    assert b.pii_report()["records_with_pii"] == 1


def test_tenant_view_pii_report_isolated():
    store = Mnemo(pii_detect=True)
    store.for_tenant("t1").remember("t1 a@x.com")
    store.for_tenant("t2").remember("t2 b@y.com and c@z.com")
    assert store.for_tenant("t1").pii_report()["records_with_pii"] == 1
    assert store.for_tenant("t2").pii_report()["by_type"]["email"] == 1  # one record, tagged email


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"\n{len(fns)} passed")
