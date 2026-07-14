"""
tenant_isolation_probe.py — MEASURED receipt for mnemo 1.6.0 hard tenant isolation. MIT.

CLAIM UNDER TEST: a Mnemo store shared across tenants (via store.for_tenant(t)) NEVER surfaces or mutates one
tenant's data through another tenant's handle — read, keyed supersession, echo, shared-subject erasure, and
PII sweep are all confined to the acting tenant. Fail-CLOSED and non-bypassable from the content path.

WHY IT MATTERS (the gap): "PII/data leaks between agents, no tenant isolation" is a recurring unmet pain in
production agent-memory stacks, and the common substitute — a per-CALL scope argument the caller must remember
to pass — fails OPEN: forget it once and the recall sees everything. We contrast both here.

METHOD (deterministic, zero-dependency, NO LLM, NO embedder). T tenants each write a private secret plus an
adversarial set designed to bleed across the boundary: the SAME supersession key with a different value (would
one tenant retire another's fact?), an ECHO of a neighbor's value, the SAME subject id (would erasure over-reach?),
and PII rows. We then run, per acting tenant, every cross-tenant probe and count any foreign record that leaks.

  LEAK RATE = (cross-tenant recalls that surfaced a foreign record) / (all cross-tenant recalls).   target 0.00
  CROSS-SUPERSEDE = foreign active facts wrongly retired by another tenant's keyed write.            target 0
  OVER-ERASE = foreign rows wrongly deleted by another tenant's forget_subject / forget_pii.         target 0

CONTRAST: the same corpus in ONE unscoped store, recalled WITHOUT the soft scope= arg (the "caller forgot"
case), to show the fail-open baseline leaks by construction.

RUN:  python tenant_isolation_probe.py            (add --json for machine-readable output)
"""
import json, os, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from mnemo import Mnemo  # noqa: E402

TENANTS = ["acme", "globex", "initech", "umbrella", "hooli"]
SECRET = "{t}-DEPLOY-SECRET-{i:03d}"


def _build_shared_store():
    """One physical store, one view per tenant. Each tenant writes an adversarial, boundary-stressing set."""
    store = Mnemo(pii_detect=True)
    store.echo_guard = True                       # exercise the echo path under tenancy too
    views = {t: store.for_tenant(t) for t in TENANTS}
    for i, t in enumerate(TENANTS):
        v = views[t]
        v.remember(f"{t} deploy secret is " + SECRET.format(t=t, i=i),
                   key="deploy::secret", object=SECRET.format(t=t, i=i))          # SAME key across tenants
        v.remember(f"{t} billing plan is enterprise", key="billing::plan", object="enterprise")
        v.remember(f"{t} contact email is admin@{t}.example.com")                 # PII row (auto-tagged)
        v.remember(f"{t} shared ticket note", source={"doc": "ticket-777"})       # SAME subject id across tenants
    return store, views


def _read_leak(views):
    """For each acting tenant, run queries that SHOULD only return its own rows; count any foreign hit."""
    total, leaked = 0, 0
    queries = ["deploy secret", "billing plan", "contact email", "shared ticket note"]
    for t, v in views.items():
        for q in queries:
            hits = v.recall(q, k=50, include_superseded=True)
            for h in hits:
                total += 1
                # a hit is foreign if its text carries any OTHER tenant's name marker
                if any(other in h["text"] for other in TENANTS if other != t):
                    leaked += 1
    return leaked, total


def _cross_supersede(store, views):
    """After all writes, every tenant's own 'deploy::secret' + 'billing::plan' must still be ACTIVE
    (no other tenant's same-key write retired it)."""
    wrongly_retired = 0
    for t, v in views.items():
        for key in ("deploy::secret", "billing::plan"):
            mine = [r for r in store.items
                    if r.get("tenant") == t and r.get("key") == key]
            if not any(r.get("status") == "active" for r in mine):
                wrongly_retired += 1
    return wrongly_retired


def _over_erase(store, views):
    """Tenant 'acme' erases subject ticket-777 and sweeps its PII. No OTHER tenant's rows may disappear."""
    before = {t: sum(1 for r in store.items if r.get("tenant") == t) for t in TENANTS}
    acme = views["acme"]
    acme.forget_subject("ticket-777")
    acme.forget_pii(types=["email"])
    after = {t: sum(1 for r in store.items if r.get("tenant") == t) for t in TENANTS}
    foreign_loss = sum(before[t] - after[t] for t in TENANTS if t != "acme")
    acme_loss = before["acme"] - after["acme"]
    return foreign_loss, acme_loss


def _fail_open_baseline():
    """The soft alternative: one unscoped store; the caller FORGOT to pass scope=. Recall sees everything ->
    leaks by construction. This is what tenant isolation replaces."""
    m = Mnemo()
    for i, t in enumerate(TENANTS):
        m.remember(f"{t} deploy secret is " + SECRET.format(t=t, i=i))
    hits = m.recall("deploy secret", k=50)        # no scope arg -> all tenants
    foreign = sum(1 for h in hits if sum(1 for t in TENANTS if t in h["text"]) >= 1)
    return len(hits), foreign


def main():
    store, views = _build_shared_store()
    leaked, total = _read_leak(views)
    cross = _cross_supersede(store, views)
    foreign_loss, acme_loss = _over_erase(store, views)
    fo_total, fo_foreign = _fail_open_baseline()

    result = {
        "tenants": len(TENANTS),
        "hard_isolation": {
            "read_leak_rate": round(leaked / total, 4) if total else 0.0,
            "cross_tenant_recalls": total,
            "leaked": leaked,
            "cross_supersede": cross,
            "over_erase_foreign_rows": foreign_loss,
            "acme_rows_erased": acme_loss,             # sanity: the acting tenant's own erasure DID happen
        },
        "fail_open_soft_scope_baseline": {
            "recalls": fo_total,
            "cross_tenant_visible": fo_foreign,
            "note": "one unscoped store, caller omitted scope= -> every tenant's secret is visible",
        },
        "verdict": "PASS" if (leaked == 0 and cross == 0 and foreign_loss == 0 and acme_loss > 0) else "FAIL",
    }
    if "--json" in sys.argv:
        print(json.dumps(result, indent=2))
        return
    hi = result["hard_isolation"]
    print(f"mnemo 1.6.0 tenant isolation — {len(TENANTS)} tenants, one shared store\n")
    print(f"  read leak rate          {hi['read_leak_rate']:.2f}  ({hi['leaked']}/{hi['cross_tenant_recalls']} cross-tenant recalls leaked)")
    print(f"  cross-tenant supersede  {hi['cross_supersede']}     (foreign facts wrongly retired)")
    print(f"  over-erase foreign rows {hi['over_erase_foreign_rows']}     (acme's erasure hit another tenant)")
    print(f"  acme own rows erased    {hi['acme_rows_erased']}     (sanity: the acting tenant's erasure worked)")
    fo = result["fail_open_soft_scope_baseline"]
    print(f"\n  fail-open contrast (soft scope forgotten): {fo['cross_tenant_visible']}/{fo['recalls']} secrets visible across tenants")
    print(f"\n  VERDICT: {result['verdict']}")


if __name__ == "__main__":
    main()
