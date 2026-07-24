"""code_guard -- stop a coding agent from resurrecting an API a refactor already replaced. Runnable end-to-end.

The most common way agent memory fails in a coding loop: a refactor renamed/removed a function, but the model
re-emits the OLD call because the old signature is still all over its context. That is keyed supersession + an
echo check -- inspeximus's core competence -- shaped for the coding loop.

Run: python examples/08_code_guard.py
"""
from inspeximus.core import Inspeximus
from inspeximus.code_guard import deprecate_symbol, symbol_status, check_code


def main():
    mem = Inspeximus(path=None)

    # --- during/after a refactor, the agent records what changed (one line each) ---
    deprecate_symbol(mem, "db.query", "db.execute", reason="query() removed in 3.0; execute() returns a cursor")
    deprecate_symbol(mem, "LEGACY_TIMEOUT", "TIMEOUT_MS", reason="renamed + unit changed to ms")
    print("recorded 2 deprecations\n")

    # --- before emitting a single call, a one-shot verdict ---
    print("symbol_status('db.query')     ->", symbol_status(mem, "db.query"))
    print("symbol_status('db.execute')   ->", symbol_status(mem, "db.execute"), "\n")

    # --- the in-loop guard: scan a WHOLE generated snippet before returning it ---
    generated = (
        "def load(uid):\n"
        "    rows = db.query('select * from users where id=?', uid)   # resurrected!\n"
        "    deadline = LEGACY_TIMEOUT * 1000                          # resurrected!\n"
        "    return rows\n"
    )
    hits = check_code(mem, generated)
    print("check_code on the generated snippet:")
    for h in hits:
        print(f"  RESURRECTED `{h['symbol']}` x{h['occurrences']} -> use `{h['replacement']}` ({h['reason']})")
    assert len(hits) == 2, hits

    # --- after the agent rewrites using the replacements, it comes back clean ---
    fixed = (
        "def load(uid):\n"
        "    rows = db.execute('select * from users where id=?', uid)\n"
        "    deadline = TIMEOUT_MS\n"
        "    return rows\n"
    )
    print("\ncheck_code on the fixed snippet:", check_code(mem, fixed))
    assert check_code(mem, fixed) == []

    print("\nRESULT: the refactor's superseded signatures cannot silently reappear in generated code --\n"
          "        a deterministic table lookup, no LLM, no embedding similarity guess.")


if __name__ == "__main__":
    main()
