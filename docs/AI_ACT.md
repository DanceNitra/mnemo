# The EU AI Act compliance-evidence layer for AI-agent memory

When the EU AI Act's high-risk obligations start to apply on **2 Aug 2026** (for Annex III systems), a provider
has to *produce* three things about what its AI agent **remembers**: a tamper-evident record of what was logged
(Art. 12 / 19), evidence that the memory is kept accurate and resists tampering (Art. 15), and provable erasure
on request (GDPR Art. 17). Agent-memory libraries ship none of it.

**inspeximus is, to our knowledge, the only open agent-memory library that ships verifiable erasure (with a
receipt) and tamper-evident record-keeping as reusable evidence for the agent-memory slice of the EU AI Act** —
a gap absent from every agent-memory product we scanned. It is a single zero-dependency file plus an MCP server;
the compliance surface is a drop-in overlay, not a rebuild.

## The gap (scanned competitor docs, 2026-07)

| Product | Verifiable erasure (with receipt)? | Tamper-evident record-keeping? | EU AI Act framing? |
|---|---|---|---|
| mem0 | plain `delete()` — no receipt | none found | none found |
| Zep | delete + retention/legal-hold — no *verifiable* erasure | SOC2 + audit logs (not cryptographically tamper-evident) | none found |
| Graphiti | "invalidated, **not deleted**" | provenance/bitemporal (not tamper-evident) | none found |
| Letta, cognee, Memobase, LangMem, Redis, Pinecone | plain `forget()`/`delete()` — no receipt | none found | none found |
| **inspeximus** | **`forget_subject` + signed content-free tombstone + `erasure_certificate`** | **hash-linked receipts + signed anchor, verified offline** | **`inspeximus compliance` article-labelled overlay** |

*(“the only one **we've found**” — a scan of nine libraries, not an exhaustive proof of a universal negative;
Zep does have a genuine SOC2/HIPAA compliance surface, just not verifiable erasure or tamper-evident logs or
AI-Act alignment.)*

## What it gives the memory slice

- **Art. 12 & 19 — record-keeping / logs kept ≥ 6 months.** Every write is a hash-linked, timestamped receipt;
  `anchor()` signs a tree head over the whole history; `inspeximus audit-build` exports a **content-free** bundle
  an auditor re-verifies from genesis **offline** (`audit-verify`) — no live store, no key.
- **Art. 15 — accuracy, robustness, cybersecurity.** Keyed supersession serves the corrected value and resists
  the stale one resurfacing (`echo_guard`); the influence gate and witness co-signing resist memory-poisoning
  and operator-side tampering (`detect_split_view`).
- **GDPR Art. 17 — right to erasure.** `forget_subject` hard-deletes the subject *plus its derived lineage* and
  emits a signed, content-free tombstone; `erasure_certificate` is the portable proof-of-deletion.

## One command turns a store into a DPO-facing report

```bash
inspeximus --receipts remember "retention policy is 90 days" --key policy::retention --object 90d
inspeximus compliance --out report.html     # article-labelled evidence, LIVE counts from the store
inspeximus audit-build --out bundle.json    # hand the auditor the bundle...
inspeximus audit-verify bundle.json         # ...they verify it offline: exit 0 = PASS
```

`report.html` lists each control (Art. 12/15/19, GDPR 17/30/5(1)(d)) with the obligation, the inspeximus
evidence, and a **live count from your store** — marked `evidence` (exercised), `available` (shipped, not
exercised here), or `needs receipts`.

### Keep it enforced — the continuous compliance gate

A one-time report drifts. `inspeximus compliance --check` is a **CI gate** that exits non-zero the moment the
posture regresses — tamper-evident logging turned off, the receipt chain failing integrity, history that is no
longer an append-only extension of a pinned anchor, or PII kept past its retention window:

```bash
inspeximus compliance --check --max-pii-age-days 90 --prior-anchor last_anchor.json   # exit 1 on any violation
```

Drop it into CI or a pre-commit hook (`id: inspeximus-compliance-check`) so the agent-memory record-keeping
duties stay met between audits, not just on audit day.

And when the gate flags PII past its window, **enforce** it — the same erasure, receipted:

```bash
inspeximus retention --max-age-days 90            # DRY-RUN: what would be erased (GDPR Art. 5(1)(e))
inspeximus retention --max-age-days 90 --apply    # erase it, each deletion leaving an auditable tombstone
```

Dry-run by default; `--apply` hard-deletes past-retention records and writes a signed tombstone per record, so
the storage-limitation enforcement is itself part of the audit trail.

## The honest boundary (this is why you can trust it)

This is the **agent-memory slice only** — the records, corrections and erasures in *this* store. It produces
**evidence, not a certification.** The EU AI Act imposes far more than any memory library can satisfy (risk
management, data governance, human oversight, conformity assessment); those are the deployer's job. The
obligations bind the **controller / provider / deployer**, not the library. inspeximus gives the accountable
party the receipts, provenance, and provable erasure they use to *demonstrate* the memory-record duties — and
says so, in every report it prints. The Art. 17 erasure guarantee is only as complete as the encryption and
copy-control of the underlying store.

Full control mapping (NIST 800-53r5 / 218A / 600-1 / 88, OWASP LLM Top 10 / ASI, GDPR, EU AI Act):
[docs/COMPLIANCE.md](COMPLIANCE.md).

---

### Sources (article text verified against primary EU texts)

Article quotations were verified verbatim against the EU Publications Office consolidated texts (the primary OJ
manifestation): **Regulation (EU) 2024/1689** (AI Act) — EUR-Lex ELI `https://eur-lex.europa.eu/eli/reg/2024/1689/oj`
— and **Regulation (EU) 2016/679** (GDPR) — `https://eur-lex.europa.eu/eli/reg/2016/679/oj`. Enforcement dates
per AI Act Art. 113: general application 2 Aug 2026; Chapters I–II from 2 Feb 2025; GPAI/governance/penalty
provisions from 2 Aug 2025 (except Art. 101); Art. 6(1) (Annex I route) from 2 Aug 2027. Annex III high-risk
systems are classified under Art. 6(2) and fall under the 2 Aug 2026 date.
