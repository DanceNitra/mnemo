"""graph_layer_probe.py — deterministic knowledge graph over keyed (subject::relation, object) triples, zero-LLM.

graph() derives entities + edges from mnemo's existing keyed-supersession triples; subgraph() does multi-hop
traversal. No LLM entity-extraction, no graph DB — the 'graph memory' checkbox done mnemo's deterministic way.
Asserts (each can FAIL):
  1. graph() surfaces edges subject-[relation]->object from keyed memories, with the right nodes.
  2. a SUPERSEDED fact drops out of the active graph (graph reflects CURRENT truth).
  3. subgraph(entity, hops=1) returns the entity's direct connections only.
  4. subgraph(entity, hops=2) reaches a 2-hop-away entity that hops=1 does not.
  5. free-text / unkeyed memories do NOT pollute the graph (only triples are edges).
"""
import sys
sys.path.insert(0, ".")
from mnemo import Mnemo

FAILS = []
def check(n, c):
    print(f"  [{'OK ' if c else 'XXX'}] {n}")
    if not c: FAILS.append(n)

m = Mnemo(path=None)
# a small graph: Alice -works_at-> Acme ; Acme -located_in-> Berlin ; Berlin -country-> Germany
m.remember("Alice works at Acme", key="Alice::works_at", object="Acme")
m.remember("Acme is located in Berlin", key="Acme::located_in", object="Berlin")
m.remember("Berlin is in Germany", key="Berlin::country", object="Germany")
m.remember("just a free-text note about lunch")                 # unkeyed -> not an edge
m.remember("Alice likes coffee", key="Alice::likes", object="tea")   # will be superseded
m.remember("Alice likes coffee now", key="Alice::likes", object="coffee")  # supersedes -> tea drops out

g = m.graph()
edges = {(e["subject"], e["relation"], e["object"]) for e in g["edges"]}
check("1 graph() surfaces the (subject,relation,object) edges + nodes",
      ("Alice", "works_at", "Acme") in edges and "Acme" in g["nodes"] and "Germany" in g["nodes"])
check("2 superseded fact drops out (current=coffee, not tea)",
      ("Alice", "likes", "coffee") in edges and ("Alice", "likes", "tea") not in edges)
check("5 unkeyed free-text note is NOT an edge", all("lunch" not in e["text"] for e in g["edges"]))

sg1 = m.subgraph("Alice", hops=1)
check("3 subgraph(hops=1) = direct connections (Acme yes, Germany no)",
      "Acme" in sg1["nodes"] and "Germany" not in sg1["nodes"])

sg2 = m.subgraph("Alice", hops=2)
check("4 subgraph(hops=2) reaches 2-hop entity (Berlin) that hops=1 misses",
      "Berlin" in sg2["nodes"] and "Berlin" not in sg1["nodes"])

print(f"\n  nodes={g['nodes']}\n  edges={len(g['edges'])}")
print(f"{'ALL PASS' if not FAILS else 'FAILED: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
