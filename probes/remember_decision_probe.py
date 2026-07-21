"""remember_decision_probe.py — decisions as first-class, correctable, revertible memory.

A raw event log (commands, file-states) captures MECHANICS but not CONCLUSIONS, so it can't answer "what did we
decide / choose / send, and why". remember_decision() stores the decision + rationale (`because`) + situation
(`context`) as a durable memory, and — with a `topic` — gives it deterministic keyed supersession: a new decision
on the same topic retires the old one, recall returns the CURRENT decision, and revert() restores the prior one.
This is inspeximus's integrity moat (supersession + revert + audit, no LLM, no similarity guess) applied to DECISIONS,
which an LLM-extracted fact store (mem0/Zep) does not provide. Asserts:
  1. a decision is stored + recallable, carrying its rationale in meta.
  2. a new decision on the same topic SUPERSEDES the old (exactly one active per topic; recall = current).
  3. revert(decision::<topic>) restores the prior decision.
"""
import sys
sys.path.insert(0, ".")
from inspeximus import Inspeximus

FAILS = []
def check(n, c):
    print(f"  [{'OK ' if c else 'XXX'}] {n}")
    if not c: FAILS.append(n)

m = Inspeximus(path=None)
mid = m.remember_decision("drop the mem0 comparison from the release copy",
                          because="mem0 ran the same nomic embedder without prefixes = confounded",
                          topic="release::mem0-cmp", tags=["inspeximus"])
rec = next((r for r in m.items if r["id"] == mid), {})
hit = (m.recall("mem0 comparison decision", k=1) or [{}])[0]
check("1 decision stored + recallable", "DECISION:" in (hit.get("text") or ""))
check("1b rationale kept in meta", (rec.get("meta") or {}).get("rationale", "").startswith("mem0 ran"))
check("1c tagged decision + durable (procedural)", "decision" in (rec.get("tags") or []) and rec.get("mtype") == "procedural")

m.remember_decision("keep a caveated mem0 comparison", because="owner wants the context", topic="release::mem0-cmp")
active = [r for r in m.items if r.get("key") == "decision::release::mem0-cmp" and r.get("status") == "active"]
cur = (m.recall("mem0 comparison decision", k=1) or [{}])[0].get("text", "")
check("2 new decision supersedes (exactly one active on topic)", len(active) == 1)
check("2b recall returns the CURRENT decision", "keep a caveated" in cur)

rv = m.revert("decision::release::mem0-cmp")
after = (m.recall("mem0 comparison decision", k=1) or [{}])[0].get("text", "")
check("3 revert restores the prior decision", rv.get("ok") and "drop the mem0 comparison" in after)

# no-topic decision still works (no supersession, just a durable decision memory)
m.remember_decision("always write conclusions to memory as we go", because="log != memory")
check("4 topic-less decision stored", any("conclusions to memory" in (r.get("text") or "") for r in m.items))

print(f"\n{'ALL PASS' if not FAILS else 'FAILED: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
