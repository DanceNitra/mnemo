"""mnemo_rerank_hook_probe.py — recall(rerank=...) retrieve-then-rerank hook.

Verifies the plumbing (model-agnostic, mnemo imports no model): a caller-supplied `rerank(query, records)
-> list[float]` reorders the top candidates before truncation to k, and a broken reranker fails open (original
order, no crash). HONEST scope: the hook only helps as much as the reranker does — a model-READER reranker is
the measured multi-hop lever (LoCoMo ~0.30->~0.48); a generic query-relevance cross-encoder does NOT help
multi-hop (measured: it hurts, because 2nd-hop evidence isn't directly query-relevant)."""
import sys, pathlib, tempfile, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from mnemo import Mnemo


def _fresh():
    m = Mnemo(path=os.path.join(tempfile.mkdtemp(), "m.json"))
    for t in ["alpha fact", "beta fact", "gamma fact", "delta fact", "epsilon fact"]:
        m.remember(t, tags=["x"])
    return m


def run():
    ok = {}
    rank = {"alpha": 5, "beta": 4, "gamma": 3, "delta": 2, "epsilon": 1}

    # A ascending reranker -> alpha..epsilon
    asc = [h["text"].split()[0] for h in
           _fresh().recall("fact", k=5, rerank=lambda q, recs: [rank[r["text"].split()[0]] for r in recs])]
    ok["A rerank drives order (asc)"] = asc == ["alpha", "beta", "gamma", "delta", "epsilon"]

    # B opposite reranker -> reversed order (proves the hook, not a coincidence)
    desc = [h["text"].split()[0] for h in
            _fresh().recall("fact", k=5, rerank=lambda q, recs: [-rank[r["text"].split()[0]] for r in recs])]
    ok["B rerank drives order (desc)"] = desc == ["epsilon", "delta", "gamma", "beta", "alpha"]

    # C broken reranker -> fail-open (no crash, still k results)
    res = _fresh().recall("fact", k=5, rerank=lambda q, recs: 1 / 0)
    ok["C broken reranker fails open"] = len(res) == 5

    # D wrong-length scores -> ignored (fail-open, no crash)
    res2 = _fresh().recall("fact", k=5, rerank=lambda q, recs: [1.0])
    ok["D length-mismatch ignored"] = len(res2) == 5

    # E rerank_pool bounds the reranked window (records beyond pool keep base order tail)
    got = _fresh().recall("fact", k=5, rerank=lambda q, recs: list(range(len(recs))), rerank_pool=2)
    ok["E rerank_pool honored (no crash)"] = len(got) == 5

    print("=" * 60)
    print("recall(rerank=...) hook — retrieve-then-rerank plumbing")
    print("=" * 60)
    for k, v in ok.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print("-" * 60)
    print("RECEIPT:", "VALID - all checks hold" if all(ok.values()) else "INVALID - do not ship")
    return 0 if all(ok.values()) else 1


if __name__ == "__main__":
    raise SystemExit(run())
