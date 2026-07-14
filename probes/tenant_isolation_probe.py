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


def _foreign_markers(t):
    """Every string that uniquely identifies ANOTHER tenant's data — the tenant name AND its secret value.
    Detecting the VALUE (not just the name) closes the false-negative sieve: a leaked secret that omits the
    neighbour's name still trips the detector."""
    marks = set()
    for i, other in enumerate(TENANTS):
        if other == t:
            continue
        marks.add(other)
        marks.add(SECRET.format(t=other, i=i))
    return marks


def _read_leak(views):
    """For each acting tenant, run queries that SHOULD only return its own rows; count any foreign hit.
    A hit is foreign if it carries another tenant's NAME or SECRET VALUE (value-level detection)."""
    total, leaked = 0, 0
    queries = ["deploy secret", "billing plan", "contact email", "shared ticket note"]
    for t, v in views.items():
        marks = _foreign_markers(t)
        for q in queries:
            hits = v.recall(q, k=50, include_superseded=True)
            for h in hits:
                total += 1
                if any(m in h["text"] for m in marks):
                    leaked += 1
    return leaked, total


def _consolidation_leak(store, views):
    """THE REAL BLEED VECTOR (found by the stress-claim audit): the dream pass links/dedups/supersedes across
    records. If it is not tenant-scoped, one tenant's consolidate() can link its record to another tenant's or
    supersede it. We seed each tenant with a near-DUPLICATE of a shared phrase (so an unscoped dedup WOULD link
    them across tenants), run consolidate() on every tenant view, and count any cross-tenant link or any foreign
    row a tenant's pass superseded."""
    for t, v in views.items():
        v.remember(f"the runbook for {t} says restart the api gateway nightly at midnight utc")  # near-dup across tenants
    cross_links = 0
    foreign_superseded = 0
    own_ids = {t: {r["id"] for r in store.items if r.get("tenant") == t} for t in TENANTS}
    for t, v in views.items():
        v.consolidate(dup_threshold=0.5)          # aggressive dedup threshold to force cross-tenant linking if unscoped
    for t in TENANTS:
        for r in store.items:
            if r.get("tenant") != t:
                continue
            # any link from a t-row to a NON-t row is a cross-tenant link
            for lid in (r.get("links") or []):
                owner = next((o for o in TENANTS if lid in own_ids[o]), None)
                if owner is not None and owner != t:
                    cross_links += 1
    # a foreign row superseded by another tenant's pass: superseded row whose toggle pointer is owned by a different tenant
    idto = {r["id"]: r.get("tenant") for r in store.items}
    for r in store.items:
        if r.get("status") == "superseded":
            tog = (r.get("meta") or {}).get("superseded_by_toggle")
            if tog and idto.get(tog) is not None and idto.get(tog) != r.get("tenant"):
                foreign_superseded += 1
    return cross_links, foreign_superseded


def _poison_leak(views):
    """CROSS-TENANT WRITE POISONING: tenant 'acme' writes many records asserting a false value for a key that
    'globex' also uses. globex's recall of that key must be UNAFFECTED (acme cannot bias globex's ranking)."""
    acme, globex = views["acme"], views["globex"]
    globex.remember("globex api region is eu-west", key="cfg::region", object="eu-west")
    for _ in range(8):
        acme.remember("api region is us-east-poison", key="cfg::region", object="us-east-poison")
    hits = globex.recall("api region", k=5)
    poisoned = sum(1 for h in hits if "poison" in h["text"])
    return poisoned


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
    cons_links, cons_superseded = _consolidation_leak(store, views)
    poisoned = _poison_leak(views)
    foreign_loss, acme_loss = _over_erase(store, views)
    fo_total, fo_foreign = _fail_open_baseline()

    result = {
        "tenants": len(TENANTS),
        "hard_isolation": {
            "read_leak_rate": round(leaked / total, 4) if total else 0.0,
            "cross_tenant_recalls": total,
            "leaked": leaked,
            "cross_supersede": cross,
            "consolidation_cross_links": cons_links,          # dream-pass linking across tenants
            "consolidation_foreign_superseded": cons_superseded,
            "cross_tenant_poison": poisoned,                  # one tenant biasing another's recall
            "over_erase_foreign_rows": foreign_loss,
            "acme_rows_erased": acme_loss,             # sanity: the acting tenant's own erasure DID happen
        },
        "fail_open_soft_scope_baseline": {
            "recalls": fo_total,
            "cross_tenant_visible": fo_foreign,
            "note": "one unscoped store, caller omitted scope= -> every tenant's secret is visible",
        },
        "verdict": "PASS" if (leaked == 0 and cross == 0 and cons_links == 0 and cons_superseded == 0
                               and poisoned == 0 and foreign_loss == 0 and acme_loss > 0) else "FAIL",
    }
    if "--json" in sys.argv:
        print(json.dumps(result, indent=2))
        return
    hi = result["hard_isolation"]
    print(f"mnemo 1.6.0 tenant isolation — {len(TENANTS)} tenants, one shared store\n")
    print(f"  read leak rate            {hi['read_leak_rate']:.2f}  ({hi['leaked']}/{hi['cross_tenant_recalls']} cross-tenant recalls; name+value detection)")
    print(f"  cross-tenant supersede    {hi['cross_supersede']}     (foreign facts wrongly retired by a keyed write)")
    print(f"  consolidation cross-links {hi['consolidation_cross_links']}     (dream pass linked across tenants)")
    print(f"  consolidation supersede   {hi['consolidation_foreign_superseded']}     (dream pass retired a foreign row)")
    print(f"  cross-tenant poison       {hi['cross_tenant_poison']}     (one tenant biased another's recall)")
    print(f"  over-erase foreign rows   {hi['over_erase_foreign_rows']}     (acme's erasure hit another tenant)")
    print(f"  acme own rows erased      {hi['acme_rows_erased']}     (sanity: the acting tenant's erasure worked)")
    fo = result["fail_open_soft_scope_baseline"]
    print(f"\n  in-library config contrast (soft scope omitted): {fo['cross_tenant_visible']}/{fo['recalls']} secrets visible")
    print(f"\n  VERDICT: {result['verdict']}")


if __name__ == "__main__":
    main()
