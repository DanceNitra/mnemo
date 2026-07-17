"""The mem0 drop-in: change ONE import, get echo-resistant correction.

    - from mem0 import Memory
    + from mnemo.mem0 import Memory

The rest of your code is unchanged. The difference: when a corrected fact's OLD value is later restated
(a user repeating a preference they forgot they changed, or one stray line in a long chat), mnemo keeps the
correction. A similarity store revives the stale value ~47% of the time (measured, n=30: mem0 2.0.11 = 0.53
echo-resistance; this = 1.00 — github.com/DanceNitra/ramr).

Run:  python examples/06_mem0_dropin.py
"""
from mnemo.mem0 import Memory


def main():
    m = Memory()   # in-memory; pass a path via from_config({"vector_store": {"config": {"path": "mem.json"}}})

    # Plain mem0-style calls — no keys, no config. The "<subject> is <value>" shape is auto-keyed.
    m.add("the deploy region is Frankfurt", user_id="ops")
    print("stored:", m.search("region", filters={"user_id": "ops"})["results"][0]["memory"])

    m.add("correction: the deploy region is Ohio", user_id="ops")   # a correction -> supersedes
    print("after correction:", m.search("region", filters={"user_id": "ops"})["results"][0]["memory"])

    # THE ECHO: someone restates the OLD value. It is the newest write, so a naive/similarity store lets it win.
    m.add("reminder: the deploy region is Frankfurt", user_id="ops")
    top = m.search("region", filters={"user_id": "ops"})["results"][0]["memory"]
    print("after the old value is restated:", top)
    print("  -> kept the correction?" , "OHIO" if "Ohio" in top else "FRANKFURT came back from the dead")

    # The lineage is inspectable (what corrected what).
    rid = m.search("region", filters={"user_id": "ops"})["results"][0]["id"]
    print("\nlineage:")
    for h in m.history(rid):
        print(f"  {h['object']:<12} [{h['status']}]")

    print("\nHonest scope: this is a drop-in for the storage + correction layer, not mem0's LLM fact-"
          "extraction. Recall is mnemo's (lexical unless you wire an embedder). The edge is integrity.")


if __name__ == "__main__":
    main()
