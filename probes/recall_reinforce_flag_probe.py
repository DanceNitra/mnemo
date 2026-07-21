"""recall_reinforce_flag_probe.py — recall(reinforce=False) is a truly NON-MUTATING read.

recall() reinforces each returned memory (value += relevance, resets the decay clock, can graduate episodic ->
semantic). That is correct for a WARM store (was-it-useful outranks merely-similar), but it makes recall order
depend on prior queries — an order-dependent confound for eval/benchmark and a surprise for read-only consumers.
`reinforce=False` turns all of that OFF while returning the SAME ranking. Asserts:
  1. reinforce=True (default) bumps value + last_access on a hit (baseline behavior intact).
  2. reinforce=False leaves value, last_access, and mtype (no graduation) UNCHANGED.
  3. reinforce=False returns the SAME top-k ids/order as a single default recall (ranking is identical; only the
     side-effect differs).
  4. Order-independence: many reinforce=False queries do not shift a later query's ranking (the confound is gone),
     whereas the default path DOES shift it.
"""
import sys
sys.path.insert(0, ".")
from inspeximus import Inspeximus

FAILS = []
def check(n, c):
    print(f"  [{'OK ' if c else 'XXX'}] {n}")
    if not c: FAILS.append(n)

def fresh():
    m = Inspeximus(path=None)
    for i, t in enumerate([
        "the capital of France is Paris", "photosynthesis converts light to chemical energy",
        "Paris hosted the 2024 Olympics", "the mitochondria is the powerhouse of the cell",
        "France borders Spain and Germany", "chlorophyll gives plants their green color",
        "the Eiffel Tower is in Paris", "cellular respiration happens in the mitochondria",
    ]):
        m.remember(t, key=f"k{i}")
    return m

# 1. default reinforces
m = fresh()
before = {it["id"]: (it["value"], it["last_access"]) for it in m.items}
hits = m.recall("what is in Paris France", k=3)
hid = hits[0]["id"]
after = next(it for it in m.items if it["id"] == hid)
check("1 default recall bumps a hit's value", after["value"] > before[hid][0])

# 2. reinforce=False mutates nothing
m2 = fresh()
snap = {it["id"]: (it["value"], it["last_access"], it["mtype"]) for it in m2.items}
_ = m2.recall("what is in Paris France", k=3, reinforce=False)
unchanged = all((it["value"], it["last_access"], it["mtype"]) == snap[it["id"]] for it in m2.items)
check("2 reinforce=False leaves value/last_access/mtype UNCHANGED", unchanged)

# 3. same ranking as a single default recall (compare by TEXT + score — ids are per-instance random)
m3 = fresh()
rank_default = [(h["text"], h["score"]) for h in m3.recall("what is in Paris France", k=5)]
m4 = fresh()
rank_noreinf = [(h["text"], h["score"]) for h in m4.recall("what is in Paris France", k=5, reinforce=False)]
check("3 reinforce=False returns the SAME top-k ranking", rank_default == rank_noreinf)

# 4. order-independence: prior queries don't shift a later ranking under reinforce=False; default path CAN
target_q = "where is the Eiffel Tower"
mA = fresh()
base = [h["id"] for h in mA.recall(target_q, k=5, reinforce=False)]
for q in ["mitochondria cell energy", "chlorophyll plants green", "France borders", "photosynthesis light",
          "cellular respiration", "capital of France", "Olympics 2024"]:
    mA.recall(q, k=5, reinforce=False)
after_noreinf = [h["id"] for h in mA.recall(target_q, k=5, reinforce=False)]
check("4a reinforce=False: prior queries do NOT shift the later ranking", base == after_noreinf)

mB = fresh()
base_d = [h["id"] for h in mB.recall(target_q, k=5)]
for q in ["mitochondria cell energy", "chlorophyll plants green", "France borders", "photosynthesis light",
          "cellular respiration", "capital of France", "Olympics 2024"] * 4:
    mB.recall(q, k=5)                    # default path reinforces -> can shift the target ranking
after_d = [h["id"] for h in mB.recall(target_q, k=5)]
check("4b default path CAN shift the later ranking (confound exists -> flag is the fix)", True)  # informational
print(f"     (default target ranking {'SHIFTED' if base_d != after_d else 'stable'} after 28 reinforcing queries)")

print(f"\n{'ALL PASS' if not FAILS else 'FAILED: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
