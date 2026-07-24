"""Portable audit bundle -- hand a DPO/auditor ONE content-free file they verify OFFLINE. Runnable end-to-end.

EU AI Act Art.12 (record-keeping, enforceable 2 Aug 2026) + GDPR Art.17/30 ask an operator to PRODUCE a
tamper-evident log of what was recorded, what changed, and what was erased -- and let an independent party
verify it. inspeximus computes every piece; audit_bundle serialises them into one self-verifying artifact with
a standalone verifier that needs neither the live store nor the receipt key.

Run: python examples/09_audit_bundle.py
"""
from inspeximus.core import Inspeximus
from inspeximus.audit_bundle import build_bundle, verify_bundle


def main():
    # --- an operator's store, run with receipts on (the tamper-evident write/erasure chain) ---
    m = Inspeximus(path=None, receipts=True)
    m.remember("retention policy is 30 days", key="policy::retention", object="30d")
    m.remember("retention policy is 90 days", key="policy::retention", object="90d")     # a correction
    m.remember("user u_17 phone is +100", key="u17::phone", object="+100")
    m.forget(where=lambda r: r.get("key") == "u17::phone")                                # a right-to-erasure

    # --- export ONE portable, content-free artifact ---
    bundle = build_bundle(m)
    print(f"bundle: {bundle['anchor']['n_writes']} write receipts, "
          f"{bundle['anchor']['n_tombstones']} erasure tombstone(s), content-free\n")

    # --- the auditor verifies it OFFLINE: no store, no receipt key, just the file ---
    res = verify_bundle(bundle)
    for c in res["checks"]:
        print(f"  OK   {c}")
    print(f"\nVERDICT: {'PASS' if res['ok'] else 'FAIL'}  summary={res['summary']}")
    assert res["ok"]

    # --- any post-export tampering is caught (flip one committed hash, re-seal the outer hash) ---
    from inspeximus.core import _sha256_hex, _canon
    forged = dict(bundle)
    forged["write_chain"] = [dict(forged["write_chain"][0], hash="dead" + forged["write_chain"][0]["hash"][4:])] \
        + forged["write_chain"][1:]
    forged["bundle_hash"] = _sha256_hex(_canon({k: v for k, v in forged.items() if k != "bundle_hash"}))
    res2 = verify_bundle(forged)
    print(f"\nafter tampering a receipt + re-sealing: {'PASS' if res2['ok'] else 'FAIL'} "
          f"-> {res2['problems']}")
    assert not res2["ok"]

    print("\nRESULT: the operator hands over one content-free file; the auditor verifies the whole write +\n"
          "        erasure history from genesis, offline, and any alteration fails the check. Pass witnesses=\n"
          "        (a co-signed anchor) for the operator-adversarial guarantee.")


if __name__ == "__main__":
    main()
