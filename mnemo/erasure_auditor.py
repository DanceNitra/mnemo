"""erasure_auditor.py — after you run a right-to-erasure deletion, does the data STAY deleted across the fan-out?

DSAR platforms (BigID, OneTrust, Transcend, DataGrail) orchestrate cross-system deletion and log that deletion
EXECUTED. The gap none of them close (confirmed by a compliance-engineer review, 2026-07-13): none re-attempts
ADVERSARIAL RECOVERY of the subject's data from the surviving stores — "deletion executed" is not "content no
longer reconstructible". A row can be gone while the embedding that encodes it survives in the index, a cache,
an offline snapshot, a retrieval log, or the chat history — and a retained embedding reconstructs the content
(Morris et al., "Text Embeddings Reveal (Almost) As Much As Text", EMNLP 2023; Ghost Vectors, arXiv 2606.18497,
recovers deleted clinical attributes from soft-deleted HNSW vectors).

This is a TOOL, not a research claim: register every place a subject's data can live as a StoreProbe; after your
app has run its deletion, `audit()` runs a per-store adversarial recovery attempt and reports where the data is
STILL RECOVERABLE. Honest by construction — it reports survivors, never a false "erased"; `erasure_verified` is
True only if NO registered store recovered anything. It cannot prove physical destruction, cannot cover stores
you did not register, and the vector-recovery check is a LOWER BOUND on the leak (full inversion is stronger).
Prior art credited above; the fix, when a store leaks, is hard-delete+reindex or crypto-shredding (destroy the
key, not the row — EDPB 05/2019; NIST SP 800-88 cryptographic erase).

Zero external deps for the framework; the VectorIndexProbe needs an embedder you pass in (e.g. local nomic).
"""
from __future__ import annotations
import re


class StoreProbe:
    """One place a subject's data can live. Implement recover(): adversarially try to get the subject's sensitive
    `values` back out of THIS store after the app's deletion, and report whether any survived."""
    name = "unnamed-store"
    kind = "generic"

    def recover(self, subject: str, values) -> dict:
        raise NotImplementedError


class TextStoreProbe(StoreProbe):
    """A text-bearing store the app may forget to purge: retrieval logs, prompt logs, chat history, a doc store.
    Recovery = the subject's value still appears verbatim (substring/word-boundary) in the retained text."""
    kind = "text"

    def __init__(self, name: str, texts):
        self.name = name
        self._get = texts if callable(texts) else (lambda: list(texts))

    def recover(self, subject, values):
        blob = " \n ".join(self._get() or []).lower()
        hits = [v for v in values if re.search(r"(?<![a-z0-9])" + re.escape(v.lower()) + r"(?![a-z0-9])", blob)]
        return {"recoverable": bool(hits), "method": "verbatim-substring", "recovered": hits}


class VectorIndexProbe(StoreProbe):
    """The wedge DSAR tools miss: an app vector index where a "deleted" row's EMBEDDING may survive (soft-delete,
    snapshot, replica). Recovery is ADVERSARIAL — not 'is the row present' but 'can the content be reconstructed
    from the surviving vectors': embed candidate value-templates and check whether the nearest retained vector
    reconstructs the subject's true value (a closed-set lower bound on embedding inversion, Morris 2023)."""
    kind = "vector"

    def __init__(self, name: str, embed, sim=None):
        self.name = name
        self.embed = embed
        self.sim = sim or _cosine
        self._vectors = []           # list of (subject, text, vector) still physically in the index

    def add(self, subject, text):
        self._vectors.append((subject, text, self.embed(text)))

    def purge(self, subject):        # what a correct hard-delete would do
        self._vectors = [(s, t, v) for (s, t, v) in self._vectors if s != subject]

    def recover(self, subject, values, template="{subject} :: {value}", candidates=None):
        if not self._vectors:
            return {"recoverable": False, "method": "nn-inversion", "recovered": []}
        recovered = []
        for v in values:
            cands = list(candidates) if candidates else [v]      # attacker's candidate set (>= the true value)
            if v not in cands:
                cands.append(v)
            qv = {c: self.embed(template.format(subject=subject, value=c)) for c in cands}
            best = max(self._vectors, key=lambda row: max(self.sim(row[2], qv[c]) for c in cands))
            # which candidate does the surviving vector most resemble?
            top = max(cands, key=lambda c: self.sim(best[2], qv[c]))
            if top == v:
                recovered.append(v)
        return {"recoverable": bool(recovered), "method": "nn-inversion (lower bound)", "recovered": recovered}


class KVCacheProbe(StoreProbe):
    """An embedding-API response cache or a Redis retrieval cache keyed by content — a store deletions routinely
    miss. Recovery = the subject's value is still present in a cached value."""
    kind = "cache"

    def __init__(self, name: str, cache):
        self.name = name
        self._get = cache if callable(cache) else (lambda: dict(cache))

    def recover(self, subject, values):
        blob = " ".join(str(x) for x in (self._get() or {}).values()).lower()
        hits = [v for v in values if v.lower() in blob]
        return {"recoverable": bool(hits), "method": "cache-value-scan", "recovered": hits}


class ErasureAuditor:
    def __init__(self):
        self._probes: list[StoreProbe] = []

    def register(self, probe: StoreProbe) -> "ErasureAuditor":
        self._probes.append(probe)
        return self

    def audit(self, subject: str, values, **probe_kwargs) -> dict:
        """After the app has run its deletion, adversarially probe every registered store for the subject's
        `values`. Returns a report; erasure_verified is True only if NO store recovered anything."""
        results = []
        for p in self._probes:
            try:
                if isinstance(p, VectorIndexProbe):
                    r = p.recover(subject, values, **{k: v for k, v in probe_kwargs.items()
                                                      if k in ("template", "candidates")})
                else:
                    r = p.recover(subject, values)
                err = None
            except Exception as e:
                r, err = {"recoverable": True, "method": "error", "recovered": []}, str(e)[:160]
            results.append({"store": p.name, "kind": p.kind, "recoverable": bool(r["recoverable"]),
                            "method": r["method"], "recovered": r.get("recovered", []), "error": err})
        leaks = [x["store"] for x in results if x["recoverable"]]
        return {
            "subject": subject,
            "stores_audited": [p.name for p in self._probes],
            "results": results,
            "erasure_verified": len(leaks) == 0,
            "leaking_stores": leaks,
            "scope": ("Audits ONLY the registered stores. 'erasure_verified' means no registered store still had "
                      "the data recoverable at audit time; it is NOT a proof of physical destruction, does not "
                      "cover unregistered stores or backups, and the vector check is a LOWER BOUND on embedding "
                      "inversion (Morris 2023). When a store leaks, hard-delete+reindex or crypto-shred the key."),
        }


def _cosine(a, b):
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-9)
