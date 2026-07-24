"""Coding-agent guard -- stop an agent from resurrecting an API/symbol a refactor already replaced.

The single most common way an agent-memory failure shows up in a coding loop: a refactor renamed or removed a
function, but the model re-emits the OLD call because the old signature is still all over its context (and, in
a naive memory, still in the store). "The refactor superseded the old API signature; don't resurrect it" is
exactly keyed supersession + an echo check -- inspeximus's core competence -- shaped for the coding loop so an
agent never has to know the keying convention.

Built entirely on the proven deterministic core (`remember` keyed supersession + `_current_active`) -- NO new
storage, NO LLM, NO embeddings, so a symbol's status is a table lookup, not a similarity guess:

  - `deprecate_symbol(store, old, new, reason)` -- record a refactor: symbol `old` is now `new`. A later
    `deprecate_symbol(old, newer)` supersedes the replacement (you changed your mind), the same way any keyed
    value supersedes.
  - `symbol_status(store, name)` -- one-shot verdict for a single symbol an agent is about to emit.
  - `check_code(store, code)` -- scan a whole generated snippet and flag every deprecated symbol it resurrects
    (the echo-guard for code). Lexical whole-identifier match, not an AST parse -- deterministic and honest
    about that.

The value is the SHAPE, not new cryptography: a coding agent calls `check_code(generated)` in its loop and
gets back a deterministic "you used `old_fn`, it was replaced by `new_fn` (reason) -- do not resurrect it."
"""
from __future__ import annotations
import re

_PREFIX = "code::symbol::"                      # keyspace for symbol deprecations


def _key(name: str) -> str:
    return _PREFIX + str(name).strip()


def _reason_from(rec: dict) -> str:
    t = rec.get("text") or ""
    return t.split(": ", 1)[1] if ": " in t else ""


def deprecate_symbol(store, old: str, new: str, reason: str = "") -> dict:
    """Record that code symbol `old` was replaced by `new` (a keyed supersession -- deterministic, no LLM).
    `old`/`new` are identifiers as they appear in code (`old_fn`, `Client.connect`, `LEGACY_FLAG`). A later
    deprecation of the same `old` supersedes the replacement. Returns the recorded deprecation."""
    old = str(old).strip()
    new = str(new).strip()
    if not old or not new:
        raise ValueError("deprecate_symbol needs both `old` and `new` symbol names")
    if old == new:
        raise ValueError("`old` and `new` are the same symbol -- nothing to deprecate")
    text = f"{old} was replaced by {new}" + (f": {reason}" if reason else "")
    store.remember(text, key=_key(old), object=new, mtype="semantic")
    return {"symbol": old, "replacement": new, "reason": reason}


def symbol_status(store, name: str) -> dict:
    """Deterministic verdict for one code symbol. Returns {'symbol','verdict','replacement','reason'}:
       - 'superseded' -> a refactor replaced it; `replacement` is what to use instead (do not resurrect `name`).
       - 'active'     -> no recorded deprecation for this symbol (safe to use as far as memory knows).
    'active' is absence-of-evidence, not a guarantee the symbol exists -- it only means no refactor was recorded."""
    rec = store._current_active(_key(name))
    if rec is None:
        return {"symbol": str(name).strip(), "verdict": "active", "replacement": None, "reason": ""}
    return {"symbol": str(name).strip(), "verdict": "superseded",
            "replacement": rec.get("object"), "reason": _reason_from(rec)}


def _deprecations(store) -> dict:
    """{symbol -> current active deprecation record} for every recorded refactor in this tenant."""
    tv = getattr(store, "tenant", None)
    out = {}
    for r in store.items:
        k = r.get("key") or ""
        if (r.get("status") == "active" and k.startswith(_PREFIX)
                and (tv is None or r.get("tenant") == tv)):
            out[k[len(_PREFIX):]] = r
    return out


def check_code(store, code: str) -> list:
    """Scan a code blob for any symbol a refactor already deprecated -- the 'don't resurrect the old API' guard.
    Whole-identifier match (so `foo` matches `foo(` and `x.foo` but never `foobar`, `foo_bar` or `threshold`);
    a lexical token match, NOT an AST parse (it will also flag a mention in a string/comment -- deterministic and
    documented, not silently clever). Returns a list of {symbol, replacement, reason, occurrences} for every
    deprecated symbol the code resurrects, most-used first. Empty list = clean."""
    code = code or ""
    hits = []
    for sym, rec in _deprecations(store).items():
        if not sym:
            continue
        pat = r"(?<![A-Za-z0-9_])" + re.escape(sym) + r"(?![A-Za-z0-9_])"
        n = len(re.findall(pat, code))
        if n:
            hits.append({"symbol": sym, "replacement": rec.get("object"),
                         "reason": _reason_from(rec), "occurrences": n})
    hits.sort(key=lambda h: -h["occurrences"])
    return hits
