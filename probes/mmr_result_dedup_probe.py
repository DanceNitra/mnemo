"""mmr_result_dedup_probe.py — recall(mmr=...) returns DIVERSE results, not k near-duplicates.

The buyer's most-requested unbuilt lever (mem0/hindsight explicitly declined it): a top-k that isn't dominated by
near-identical memories. recall(mmr=lambda) applies greedy Maximal Marginal Relevance over the top pool —
next = argmax [ lambda*rel - (1-lambda)*max sim(d, chosen) ] — diversity by record vectors, falling back to
token-Jaccard so LEXICAL recall dedups too. Deterministic, zero-LLM. Asserts (each able to FAIL):
  1. plain recall (no mmr) returns k NEAR-DUPLICATES (a distinct-but-relevant memory is buried) — so the test is real.
  2. recall(mmr=0.3) SURFACES the distinct memory into top-k (diversity works).
  3. mmr=1.0 is a NO-OP (pure relevance == plain order).
  4. mmr preserves the result count (k) and never crashes.
"""
import sys
sys.path.insert(0, ".")
from inspeximus import Inspeximus

FAILS = []
def check(n, c):
    print(f"  [{'OK ' if c else 'XXX'}] {n}")
    if not c: FAILS.append(n)

def fresh():
    m = Inspeximus(path=None)                       # lexical (no embedder) -> token-Jaccard diversity, no GPU
    # a CLUSTER of near-duplicate "capital" facts + ONE distinct-but-relevant Paris fact
    m.remember("Paris is the capital of France.", key="a1")
    m.remember("The capital of France is the city of Paris.", key="a2")
    m.remember("France's capital city is Paris.", key="a3")
    m.remember("Paris serves as the capital of the French Republic.", key="a4")
    m.remember("Paris is served by Charles de Gaulle airport.", key="b")   # distinct Paris fact
    return m

Q = "tell me about Paris the capital of France"

plain = [h["text"] for h in fresh().recall(Q, k=3)]
n_capital_plain = sum("capital" in t for t in plain)
check("1 plain recall returns near-duplicates (>=3 'capital' dupes, airport buried)",
      n_capital_plain >= 3 and not any("airport" in t for t in plain))

div = [h["text"] for h in fresh().recall(Q, k=3, mmr=0.3)]
check("2 mmr=0.3 surfaces the DISTINCT memory (airport) into top-3", any("airport" in t for t in div))
check("2b mmr top-3 has fewer 'capital' dupes than plain", sum("capital" in t for t in div) < n_capital_plain)

noop = [h["text"] for h in fresh().recall(Q, k=3, mmr=1.0)]
check("3 mmr=1.0 is a no-op (== plain relevance order)", noop == plain)

full = fresh().recall(Q, k=3, mmr=0.5)
check("4 mmr preserves the result count (k=3)", len(full) == 3)

print(f"\n  plain : {plain}")
print(f"  mmr0.3: {div}")
print(f"\n{'ALL PASS' if not FAILS else 'FAILED: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
