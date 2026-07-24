"""ComplianceMixin — expose the EU AI Act agent-memory evidence operations on the SAME object a framework uses
as memory.

An integration store (LangGraph `InspeximusStore`, CrewAI `InspeximusStorage`, ...) holds an inspeximus store
in `self.store`. Mixing this in means the operator gets the compliance surface without reaching past the
framework adapter: build the article-labelled report, run the CI gate, export/verify the audit bundle, or
enforce retention — all on the memory the agent is already writing to. Pure delegation to the free
`inspeximus.compliance` / `inspeximus.audit_bundle` APIs; adds nothing to the write path.

Enable `receipts=True` on the store for the record-keeping chain (Art. 12/19) these reports evidence.
"""
from __future__ import annotations


class ComplianceMixin:
    """Requires `self.store` to be an `inspeximus.Inspeximus`. Read-only except `retention(apply=True)`.

    Deliberately declares NO class-level `store` annotation. Several adapters are pydantic models
    (LangChain `BaseRetriever`, LlamaIndex `BaseMemoryBlock`, ...); pydantic collects annotations from
    plain mixin bases too, so a `store: Any` here would be promoted to a model FIELD and would SHADOW an
    adapter that exposes `store` as a `@property` — `self.store` would then return the property object
    instead of the store. Measured, not assumed (see tests/test_governance_mixin.py).
    """

    def compliance_report(self, expected_pubkey: str | None = None) -> dict:
        """Article-labelled EVIDENCE report (AI Act Art. 12/15/19; GDPR 17/30/5(1)(d)) with live counts."""
        from inspeximus.compliance import compliance_report
        return compliance_report(self.store, expected_pubkey=expected_pubkey)

    def write_compliance_report(self, out_path: str, expected_pubkey: str | None = None) -> str:
        """Render the report to a self-contained DPO-facing HTML file. Returns the path."""
        from inspeximus.compliance import compliance_report, render_html
        html = render_html(compliance_report(self.store, expected_pubkey=expected_pubkey))
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        return out_path

    def compliance_check(self, require_receipts: bool = True, max_pii_age_days: float | None = None,
                         prior_anchor: dict | None = None) -> dict:
        """CI gate: {ok, violations, checked}. ok=False means the AI-Act memory posture regressed."""
        from inspeximus.compliance import compliance_check
        return compliance_check(self.store, require_receipts=require_receipts,
                                max_pii_age_days=max_pii_age_days, prior_anchor=prior_anchor)

    def retention(self, max_age_days: float, pii_only: bool = True, apply: bool = False,
                  now_ts: float | None = None) -> dict:
        """Storage-limitation enforcement (GDPR Art. 5(1)(e)). DRY-RUN unless apply=True; each erasure leaves a
        signed tombstone. `now_ts` evaluates the window as of a given time (defaults to now)."""
        from inspeximus.compliance import retention_sweep
        return retention_sweep(self.store, max_age_days, pii_only=pii_only, apply=apply, now_ts=now_ts)

    def audit_bundle(self, expected_pubkey: str | None = None) -> dict:
        """Content-free, portable audit bundle the auditor verifies offline (see verify_audit_bundle)."""
        from inspeximus.audit_bundle import build_bundle
        return build_bundle(self.store, expected_pubkey=expected_pubkey)

    @staticmethod
    def verify_audit_bundle(bundle: dict, witnesses: list | None = None, threshold: int = 1) -> dict:
        """Verify a bundle from audit_bundle() offline — needs only the bundle, no store, no key."""
        from inspeximus.audit_bundle import verify_bundle
        return verify_bundle(bundle, witnesses=witnesses, threshold=threshold)
