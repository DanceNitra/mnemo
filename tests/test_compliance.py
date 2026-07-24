"""Agent-memory compliance overlay: article-labelled EVIDENCE with LIVE per-store counts, honest scope +
non-certification disclaimer in every output, and per-control status that reflects what the store exercised."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from inspeximus.core import Inspeximus
from inspeximus.compliance import compliance_report, render_html


def _store():
    m = Inspeximus(path=None, receipts=True)
    m.remember("retention is 90 days", key="policy::ret", object="90d")
    m.remember("retention is 30 days", key="policy::ret", object="30d")   # a correction
    m.remember("u7 phone +100", key="u7::phone", object="+100")
    m.forget(where=lambda r: r.get("key") == "u7::phone")                 # an erasure
    return m


def test_report_has_live_evidence():
    rep = compliance_report(_store())
    assert rep["summary"]["writes"] == 3 and rep["summary"]["erasures"] == 1, rep["summary"]
    assert rep["summary"]["superseded"] == 1, rep["summary"]
    arts = {c["article"] for c in rep["controls"]}
    assert {"Art. 12", "Art. 15", "Art. 17", "Art. 30"} <= arts, arts
    # Art.12 (record-keeping) must show live write receipts as evidence
    art12 = next(c for c in rep["controls"] if c["article"] == "Art. 12")
    assert art12["status"] == "evidence" and art12["live_count"] == 3, art12


def test_disclaimer_and_scope_always_present():
    rep = compliance_report(_store())
    assert "not a certification" in rep["disclaimer"].lower()
    assert "AGENT-MEMORY slice only" in rep["scope"]
    html = render_html(rep)
    assert "not a certification" in html.lower() and "AGENT-MEMORY slice only" in html


def test_needs_receipts_when_disabled():
    """Without receipts, the record-keeping controls must honestly say so, not claim evidence."""
    m = Inspeximus(path=None, receipts=False)
    m.remember("x", key="k", object="1")
    rep = compliance_report(m)
    art12 = next(c for c in rep["controls"] if c["article"] == "Art. 12")
    assert art12["status"] == "needs_receipts", art12


def test_no_evidence_is_available_not_faked():
    """A store that never erased must NOT claim Art.17 erasure evidence."""
    m = Inspeximus(path=None, receipts=True)
    m.remember("x", key="k", object="1")
    rep = compliance_report(m)
    art17 = next(c for c in rep["controls"] if c["article"] == "Art. 17")
    assert art17["status"] == "available" and not art17["live_count"], art17


def test_html_is_self_contained():
    html = render_html(compliance_report(_store()))
    assert html.strip().startswith("<!doctype")
    assert "http://" not in html and "https://" not in html and "<script" not in html    # no external assets/JS


def test_check_passes_healthy_store():
    from inspeximus.compliance import compliance_check
    r = compliance_check(_store())
    assert r["ok"] and not r["violations"], r


def test_check_flags_no_receipts():
    from inspeximus.compliance import compliance_check
    m = Inspeximus(path=None, receipts=False)
    m.remember("x", key="k", object="1")
    r = compliance_check(m)
    assert not r["ok"] and any(v["code"] == "receipts_disabled" for v in r["violations"]), r


def test_check_flags_pii_over_retention():
    """A PII record older than the retention window is a storage-limitation violation (GDPR 5(1)(e))."""
    from inspeximus.compliance import compliance_check
    m = Inspeximus(path=None, receipts=True)
    m.remember("contact me at a@b.com", key="c::email", object="a@b.com", pii=["email"])
    old = m.items[-1]["ts"]                                    # stamp is 'now'; pretend we check 100 days later
    r = compliance_check(m, max_pii_age_days=30, now_ts=old + 100 * 86400)
    assert not r["ok"] and any(v["code"] == "pii_over_retention" for v in r["violations"]), r
    # fresh window -> no violation
    assert compliance_check(m, max_pii_age_days=30, now_ts=old + 1)["ok"]


def test_check_flags_non_append_only():
    from inspeximus.compliance import compliance_check
    m = Inspeximus(path=None, receipts=True)
    m.remember("a", key="k", object="1")
    anchor = m.anchor()
    m.remember("b", key="k", object="2")                      # honest extension -> consistent
    assert compliance_check(m, prior_anchor=anchor)["ok"]
    forged = dict(anchor, writes_tip="deadbeef" + str(anchor["writes_tip"])[8:])   # a tip that never existed
    r = compliance_check(m, prior_anchor=forged)
    assert not r["ok"] and any(v["code"] == "not_append_only" for v in r["violations"]), r


def test_retention_dry_run_does_not_erase():
    from inspeximus.compliance import retention_sweep
    m = Inspeximus(path=None, receipts=True)
    m.remember("contact a@b.com", key="c::email", object="a@b.com", pii=["email"])
    ts = m.items[-1]["ts"]
    res = retention_sweep(m, 30, now_ts=ts + 100 * 86400, apply=False)
    assert res["eligible"] == 1 and not res["applied"], res
    assert sum(1 for r in m.items if r.get("status") == "active" and r.get("pii")) == 1   # untouched


def test_retention_apply_erases_with_tombstone():
    from inspeximus.compliance import retention_sweep, compliance_check
    m = Inspeximus(path=None, receipts=True)
    m.remember("contact a@b.com", key="c::email", object="a@b.com", pii=["email"])
    ts = m.items[-1]["ts"]
    n_before = len(m._tombstones)
    res = retention_sweep(m, 30, now_ts=ts + 100 * 86400, apply=True)
    assert res["applied"] and res["erased"] == 1, res
    assert len(m._tombstones) == n_before + 1, "erasure must leave a tombstone (auditable)"
    assert compliance_check(m, max_pii_age_days=30, now_ts=ts + 100 * 86400)["ok"], "check must pass after sweep"


def test_retention_spares_fresh_records():
    from inspeximus.compliance import retention_sweep
    m = Inspeximus(path=None, receipts=True)
    m.remember("fresh a@b.com", key="c::email", object="a@b.com", pii=["email"])
    ts = m.items[-1]["ts"]
    res = retention_sweep(m, 30, now_ts=ts + 1, apply=True)      # 1 second old, window 30 days
    assert res["eligible"] == 0 and res["erased"] == 0, res


def test_cli_retention_dry_run_then_apply(tmp_path):
    import os as _os
    from inspeximus.cli import main
    _os.environ["INSPEXIMUS_PATH"] = str(tmp_path / "s.json")
    try:
        assert main(["--receipts", "remember", "old note", "--key", "k", "--object", "v"]) == 0
        assert main(["retention", "--max-age-days", "0", "--all"]) == 0          # dry-run (exit 0, no erase)
        assert main(["retention", "--max-age-days", "0", "--all", "--apply"]) == 0
        # after apply, the store has no active records
        from inspeximus import Inspeximus as _I
        m = _I(path=str(tmp_path / "s.json"), receipts=True)
        assert not any(r.get("status") == "active" for r in m.items)
    finally:
        _os.environ.pop("INSPEXIMUS_PATH", None)


def test_cli_check_exit_codes(tmp_path):
    import os as _os
    from inspeximus.cli import main
    _os.environ["INSPEXIMUS_PATH"] = str(tmp_path / "s.json")
    try:
        assert main(["--receipts", "remember", "x", "--key", "k", "--object", "1"]) == 0
        assert main(["compliance", "--check"]) == 0                       # healthy -> exit 0
        _os.environ["INSPEXIMUS_PATH"] = str(tmp_path / "bad.json")
        assert main(["remember", "y", "--key", "k", "--object", "1"]) == 0   # written WITHOUT receipts
        assert main(["compliance", "--check"]) == 1                       # regressed -> exit 1
    finally:
        _os.environ.pop("INSPEXIMUS_PATH", None)


def test_cli_compliance(tmp_path):
    import os as _os
    from inspeximus.cli import main
    _os.environ["INSPEXIMUS_PATH"] = str(tmp_path / "s.json")
    out = str(tmp_path / "report.html")
    try:
        assert main(["--receipts", "remember", "x", "--key", "k", "--object", "1"]) == 0
        assert main(["compliance", "--out", out]) == 0
        assert _os.path.exists(out) and "AGENT-MEMORY slice only" in open(out, encoding="utf-8").read()
    finally:
        _os.environ.pop("INSPEXIMUS_PATH", None)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = 0
    for fn in fns:
        try:
            (fn(__import__("tempfile").mkdtemp.__self__.mkdtemp and __import__("pathlib").Path(__import__("tempfile").mkdtemp()))
             if fn.__name__ == "test_cli_compliance" else fn())
            print(f"  PASS {fn.__name__}"); p += 1
        except AssertionError as e:
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{p}/{len(fns)} passed")
    sys.exit(0 if p == len(fns) else 1)
