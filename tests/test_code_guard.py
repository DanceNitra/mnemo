"""code_guard: the coding-agent 'don't resurrect the old API' wedge, built on keyed supersession.
deprecate_symbol records a refactor; symbol_status verdicts one symbol; check_code scans a blob and flags
every deprecated symbol it resurrects (whole-identifier match, supersession-aware)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from inspeximus.core import Inspeximus
from inspeximus.code_guard import deprecate_symbol, symbol_status, check_code


def _store():
    return Inspeximus(path=None)


def test_symbol_status_active_when_unknown():
    s = _store()
    assert symbol_status(s, "totally_fine_fn")["verdict"] == "active"


def test_deprecate_then_superseded_with_replacement():
    s = _store()
    deprecate_symbol(s, "old_connect", "connect_v2", reason="old_connect took a dict; connect_v2 takes kwargs")
    r = symbol_status(s, "old_connect")
    assert r["verdict"] == "superseded" and r["replacement"] == "connect_v2", r
    assert "kwargs" in r["reason"], r


def test_deprecation_can_be_superseded_again():
    """Changed our mind about the replacement -> latest deprecation wins (keyed supersession)."""
    s = _store()
    deprecate_symbol(s, "old_fn", "mid_fn")
    deprecate_symbol(s, "old_fn", "final_fn", reason="mid_fn was itself removed")
    r = symbol_status(s, "old_fn")
    assert r["replacement"] == "final_fn", r


def test_check_code_flags_resurrected_symbol():
    s = _store()
    deprecate_symbol(s, "legacy_login", "login", reason="renamed in 2.0")
    code = "def handler():\n    session = legacy_login(user)\n    return legacy_login(user).token\n"
    hits = check_code(s, code)
    assert len(hits) == 1 and hits[0]["symbol"] == "legacy_login", hits
    assert hits[0]["replacement"] == "login" and hits[0]["occurrences"] == 2, hits


def test_check_code_whole_identifier_only():
    """Must not fire on a substring: `old` inside `threshold`/`old_but_kept` is not a resurrection of `old`."""
    s = _store()
    deprecate_symbol(s, "old", "fresh")
    clean = "threshold = 5\nold_but_kept = 1\nscaffold(old_but_kept)\n"     # no standalone `old`
    assert check_code(s, clean) == [], check_code(s, clean)
    dirty = "x = old\ny = obj.old\n"                                        # standalone + attribute access
    hits = check_code(s, dirty)
    assert len(hits) == 1 and hits[0]["occurrences"] == 2, hits


def test_check_code_clean_returns_empty():
    s = _store()
    deprecate_symbol(s, "removed_api", "new_api")
    assert check_code(s, "result = new_api(payload)\n") == []


def test_deprecate_rejects_bad_input():
    s = _store()
    for bad in [("", "x"), ("x", ""), ("same", "same")]:
        try:
            deprecate_symbol(s, *bad); assert False, f"should reject {bad}"
        except ValueError:
            pass


def test_dotted_symbol_deprecation():
    s = _store()
    deprecate_symbol(s, "Client.connect", "Client.open", reason="connect renamed to open")
    hits = check_code(s, "c = Client()\nc = Client.connect(url)\n")
    assert len(hits) == 1 and hits[0]["replacement"] == "Client.open", hits


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS {fn.__name__}"); p += 1
        except AssertionError as e:
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{p}/{len(fns)} passed")
    sys.exit(0 if p == len(fns) else 1)
