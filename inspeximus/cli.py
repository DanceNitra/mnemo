"""inspeximus CLI — script the memory layer from the shell, no Python or MCP server needed.

    inspeximus remember "the deploy channel is BLUE-9" --key deploy-channel
    inspeximus remember "the deploy channel is RED-2"  --key deploy-channel   # supersedes
    inspeximus recall  "what is the deploy channel?"                          # -> RED-2 (current-truth)
    inspeximus revert  deploy-channel                                         # roll back to BLUE-9
    inspeximus list -n 10                                                     # recent active memories
    inspeximus forget --key deploy-channel                                    # or --id <id> / --contains <substr>
    inspeximus stats

Store path: --path, else $INSPEXIMUS_PATH, else ./inspeximus_memory.json (same default as the MCP server, so the CLI
and `inspeximus-mcp` share one store). Recall is lexical by default; set $INSPEXIMUS_EMBED_URL (+ $INSPEXIMUS_EMBED_MODEL) to
any OpenAI-compatible /embeddings endpoint (e.g. local Ollama) for semantic recall. Zero dependencies."""
from __future__ import annotations
import argparse

from . import install as _install
import json
import os
import sys


def _embedder():
    """Optional embedder (urllib, zero-dep) — enabled only if INSPEXIMUS_EMBED_URL is set. Fail-open."""
    url = os.environ.get("INSPEXIMUS_EMBED_URL", "").strip()
    if not url:
        return None
    import urllib.request
    model = os.environ.get("INSPEXIMUS_EMBED_MODEL", "text-embedding-3-small").strip()
    key = os.environ.get("INSPEXIMUS_EMBED_KEY", "").strip()

    def embed(text: str):
        body = json.dumps({"model": model, "input": text}).encode()
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["data"][0]["embedding"]

    return embed


def _store(path, persist_vectors: bool = False, receipts: bool = False):
    from inspeximus import Inspeximus
    p = path or os.environ.get("INSPEXIMUS_PATH") or "inspeximus_memory.json"
    # persist_vectors stays OFF by default (vectors are a re-derivable cache; writing them balloons the store
    # file on every command). `reembed` opts in — persisting is the entire point of that command.
    # receipts (OPT-IN): builds the tamper-evident write/erasure chain (persisted to <path>.receipts.json) that
    # `audit-build` exports; reload needs it on too, so audit-build/governance force it regardless of the flag.
    return Inspeximus(path=p, embed=_embedder(), persist_vectors=persist_vectors, receipts=receipts)


def _out(obj, as_json):
    """Print JSON and return True (handled) when as_json; else return False so a caller's
    `_out(...) or print(human_line)` prints the human line."""
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return True
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(prog="inspeximus", description="inspeximus — the self-correcting memory layer (CLI).")
    ap.add_argument("--path", help="store file (default: $INSPEXIMUS_PATH or ./inspeximus_memory.json)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--receipts", action="store_true",
                    help="enable the tamper-evident write/erasure chain (needed to later `audit-build`)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("remember", help="store a memory (a --key makes it correctable/supersedable)")
    r.add_argument("text")
    r.add_argument("--key", help="supersession key (e.g. subject::relation) — a new value retires the old")
    r.add_argument("--object", dest="object", help="the value/object for this key")
    r.add_argument("--tags", help="comma-separated tags")
    r.add_argument("--type", dest="mtype", choices=["episodic", "semantic", "procedural"], help="memory type")

    q = sub.add_parser("recall", help="retrieve current-truth memories (superseded values hidden)")
    q.add_argument("query")
    q.add_argument("-k", type=int, default=6, help="how many to return")

    v = sub.add_parser("revert", help="roll a key back to the value it superseded")
    v.add_argument("key")

    f = sub.add_parser("forget", help="hard-delete memories (by --key, --id, or --contains)")
    f.add_argument("--key")
    f.add_argument("--id")
    f.add_argument("--contains", help="delete every memory whose text contains this substring")

    ls = sub.add_parser("list", help="list recent active memories")
    ls.add_argument("-n", type=int, default=10)

    sub.add_parser("stats", help="store summary")

    br = sub.add_parser("browse", help="render a self-contained offline HTML memory browser")
    br.add_argument("--out", default="inspeximus_browser.html", help="output HTML file")
    br.add_argument("--open", action="store_true", help="open it in the default browser after writing")

    dc = sub.add_parser("decision", help="store a DECISION (what you chose + why), topic-keyed + supersedable")
    dc.add_argument("decision")
    dc.add_argument("--because", help="rationale")
    dc.add_argument("--topic", help="topic slug -> a new decision on it supersedes the old")

    sub.add_parser("contradictions", help="list mutually-incompatible memories (flagged, not auto-resolved)")
    sub.add_parser("governance", help="governance/erasure/tamper-evidence snapshot")

    co = sub.add_parser("consolidate", help="run the dedup/consolidation pass (optionally prune to --keep)")
    co.add_argument("--keep", type=int, default=None)

    wy = sub.add_parser("why", help="explain why memories were recalled for a query (per-channel breakdown)")
    wy.add_argument("query")

    di = sub.add_parser("distill", help="LLM-distill a transcript into memories (needs INSPEXIMUS_LLM_URL)")
    di.add_argument("--file", help="read text from a file (else stdin)")

    re_ = sub.add_parser("reembed", help="rebuild embeddings for records that have none (after an embed-recipe "
                                         "change dropped them); needs an embedder configured")
    re_.add_argument("--all", action="store_true", help="re-embed EVERY record, not just the ones missing a vector")
    re_.add_argument("--batch", type=int, default=None, help="cap how many records this run re-embeds")

    dep = sub.add_parser("deprecate", help="record a refactor: code symbol OLD was replaced by NEW "
                                           "(coding-agent guard; keyed supersession)")
    dep.add_argument("old", help="the removed/renamed symbol as it appears in code (e.g. db.query)")
    dep.add_argument("new", help="what to use instead (e.g. db.execute)")
    dep.add_argument("--reason", help="one-line why (shown when the old symbol is flagged)")

    ck = sub.add_parser("check-code", help="scan files for any deprecated symbol they RESURRECT and exit "
                                           "non-zero if any (drop into CI / pre-commit)")
    ck.add_argument("paths", nargs="+", help="source files to scan")

    cp_ = sub.add_parser("compliance", help="article-labelled agent-memory compliance EVIDENCE report "
                                            "(EU AI Act Art.12/15/19 + GDPR Art.17/30) — HTML or JSON")
    cp_.add_argument("--out", default=None, help="write a self-contained HTML report here")
    cp_.add_argument("--expected-pubkey", default=None, help="pin the integrity check to this key")

    ab = sub.add_parser("audit-build", help="export a portable, content-free audit bundle "
                                            "(EU AI Act Art.12 / GDPR record-keeping) — hand it to an auditor")
    ab.add_argument("--out", default="inspeximus_audit_bundle.json", help="output json path")
    ab.add_argument("--expected-pubkey", default=None, help="pin the signature-authenticity check to this key")

    av = sub.add_parser("audit-verify", help="verify an audit bundle OFFLINE (needs only the file, no store)")
    av.add_argument("bundle", help="the bundle json to verify")
    av.add_argument("--witnesses", default=None, help="comma-separated allowlisted witness pubkeys (hex)")
    av.add_argument("--threshold", type=int, default=1, help="k-of-n witness threshold")

    ins = sub.add_parser("install", help="register the MCP server in an editor's own config file")
    ins.add_argument("--ide", required=True,
                     help="host to configure: " + ", ".join(sorted(_install.HOSTS)))
    ins.add_argument("--scope", choices=["user", "project"], default=None,
                     help="user-level (default) or project-level config, where the host supports it")
    ins.add_argument("--project", default=None, help="project directory for project scope (default: cwd)")
    ins.add_argument("--store", default=None, help="value for INSPEXIMUS_PATH in the written config")
    ins.add_argument("--name", default=_install.SERVER_NAME, help="server name to write")
    ins.add_argument("--dry-run", action="store_true", help="print the exact diff, write nothing")

    a = ap.parse_args(argv)

    # `install` edits an editor's config; it must never touch a memory store. Opening one here would
    # create inspeximus_memory.json in the working directory as a side effect of asking for help.
    if a.cmd == "install":
        p = _install.plan(a.ide, scope=a.scope, project=a.project, store_path=a.store, name=a.name)
        print(_install.render(p, dry_run=a.dry_run))
        if p.get("error"):
            return 2
        if a.dry_run:
            return 0
        ok, msg = _install.apply(p)
        print(f"  {msg}")
        return 0 if ok else 1

    # audit-verify needs only the bundle file — never open a store (that would create one as a side effect).
    if a.cmd == "audit-verify":
        from inspeximus.audit_bundle import verify_bundle
        with open(a.bundle, encoding="utf-8") as f:
            bundle = json.load(f)
        wl = [w.strip() for w in a.witnesses.split(",")] if a.witnesses else None
        res = verify_bundle(bundle, witnesses=wl, threshold=a.threshold)
        if a.json:
            _out(res, True)
        else:
            for c in res["checks"]:
                print(f"  OK   {c}")
            for pr in res["problems"]:
                print(f"  FAIL {pr}")
            s = res["summary"]
            print(f"\nVERDICT: {'PASS' if res['ok'] else 'FAIL'}  "
                  f"({s.get('writes')} writes, {s.get('erasures')} erasures"
                  f"{', operator-adversarial' if s.get('operator_adversarial') else ''})")
        return 0 if res["ok"] else 1

    # audit-build/compliance must reload the receipt/tombstone chains, so force receipts on regardless of the flag.
    m = _store(a.path, receipts=a.receipts or a.cmd in ("audit-build", "compliance"))

    if a.cmd == "compliance":
        from inspeximus.compliance import compliance_report, render_html
        rep = compliance_report(m, expected_pubkey=a.expected_pubkey)
        if a.json:
            _out(rep, True)
        elif a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                f.write(render_html(rep))
            print(f"wrote compliance report -> {a.out}  "
                  f"({rep['summary']['controls_with_evidence']}/{len(rep['controls'])} controls with live evidence)")
        else:
            from inspeximus.compliance import _STATUS_LABEL
            for c in rep["controls"]:
                print(f"  [{_STATUS_LABEL.get(c['status'], c['status'])}] {c['article']} {c['title']}")
            print(f"\nscope: {rep['scope']}")
        return 0

    if a.cmd == "audit-build":
        from inspeximus.audit_bundle import build_bundle
        bundle = build_bundle(m, expected_pubkey=a.expected_pubkey)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)
        n = bundle["anchor"]["n_writes"]
        _out({"out": a.out, "writes": n, "erasures": bundle["anchor"]["n_tombstones"]}, a.json) or print(
            f"wrote audit bundle -> {a.out}  ({n} writes, {bundle['anchor']['n_tombstones']} erasures)"
            + ("\nnote: 0 writes — this store was not written with receipts enabled; write with "
               "`inspeximus --receipts remember ...` to build an auditable chain." if n == 0 else ""))
        return 0

    if a.cmd == "remember":
        tags = [t.strip() for t in a.tags.split(",")] if a.tags else None
        mid = m.remember(a.text, key=a.key, object=a.object, tags=tags, mtype=a.mtype)
        m._save(force=True)
        _out({"id": mid, "key": a.key}, a.json) or print(f"remembered {mid}" + (f" [key={a.key}]" if a.key else ""))

    elif a.cmd == "recall":
        hits = m.recall(a.query, k=a.k) or []
        if a.json:
            _out(hits, True)
        elif not hits:
            print("(nothing in memory for that query)")
        else:
            for h in hits:
                print(f"- {h.get('text','')}")

    elif a.cmd == "revert":
        res = m.revert(a.key)
        m._save(force=True)
        _out(res, a.json) or print(f"reverted {a.key}: now -> {res.get('restored') or res.get('active') or res}")

    elif a.cmd == "forget":
        where = None
        if a.contains:
            needle = a.contains.lower()
            where = lambda rec: needle in (rec.get("text") or "").lower()
        elif a.key:
            where = lambda rec: rec.get("key") == a.key
        ids = [a.id] if a.id else None
        if not ids and where is None:
            print("forget: pass --key, --id, or --contains", file=sys.stderr)
            return 2
        res = m.forget(ids=ids, where=where)
        m._save(force=True)
        _out(res, a.json) or print(f"forgot {res.get('forgotten', 0)} memory(ies)")

    elif a.cmd == "list":
        rows = [r for r in getattr(m, "items", []) if r.get("status") == "active"]
        rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
        rows = rows[: a.n]
        if a.json:
            _out([{"id": r["id"], "key": r.get("key"), "text": r.get("text", "")} for r in rows], True)
        else:
            for r in rows:
                k = f" [key={r['key']}]" if r.get("key") else ""
                print(f"- {r.get('text','')}{k}")

    elif a.cmd == "stats":
        items = getattr(m, "items", [])
        active = sum(1 for r in items if r.get("status") == "active")
        superseded = sum(1 for r in items if r.get("status") == "superseded")
        keyed = sum(1 for r in items if r.get("key"))
        st = {"path": str(m.path), "total": len(items), "active": active,
              "superseded": superseded, "keyed": keyed}
        _out(st, a.json) or print(
            f"{st['path']}: {st['total']} total ({active} active, {superseded} superseded, {keyed} keyed)")

    elif a.cmd == "reembed":
        if m.embed is None:
            print("reembed: no embedder configured (set INSPEXIMUS_EMBED_URL, or .inspeximus/config.json {\"embed\":{...}})",
                  file=sys.stderr)
            return 2
        m = _store(a.path, persist_vectors=True)      # re-open so the rebuilt vectors actually reach disk
        res = m.reembed(only_missing=not a.all, batch=a.batch)
        _out(res, a.json) or print(
            f"re-embedded {res['reembedded']} ({res['failed']} failed, {res['remaining']} still without a vector)"
            + (f"\n{res['warning']}" if res.get("warning") else ""))

    elif a.cmd == "browse":
        from inspeximus.browser import write_html
        path = write_html(m, a.out)
        if a.open:
            import webbrowser, pathlib
            # as_uri(), not "file://" + abspath: on Windows the latter yields file://C:\... (backslashes,
            # missing third slash) and it mangles spaces/non-ASCII in the path.
            webbrowser.open(pathlib.Path(path).resolve().as_uri())
        _out({"written": path}, a.json) or print(f"wrote memory browser -> {path}" + ("  (opened)" if a.open else ""))

    elif a.cmd == "decision":
        mid = m.remember_decision(a.decision, because=a.because, topic=a.topic)
        m._save(force=True)
        _out({"id": mid, "topic": a.topic}, a.json) or print(f"decision stored {mid}" + (f" [topic={a.topic}]" if a.topic else ""))

    elif a.cmd == "contradictions":
        pairs = m.contradictions()
        if a.json:
            _out(pairs, True)
        elif not pairs:
            print("(no contradictions)")
        else:
            for p in pairs:
                print(f"- {p.get('a_text','')}  <>  {p.get('b_text','')}")

    elif a.cmd == "governance":
        _out(m.governance_report(), a.json) or print(json.dumps(m.governance_report(), indent=2, default=str))

    elif a.cmd == "consolidate":
        res = m.consolidate(keep=a.keep)
        m._save(force=True)
        _out(res, a.json) or print(f"consolidated: {res}")

    elif a.cmd == "why":
        exp = m.why_recalled(a.query)
        _out(exp, a.json) or print(json.dumps(exp, indent=2, default=str))

    elif a.cmd == "deprecate":
        from inspeximus.code_guard import deprecate_symbol
        try:
            res = deprecate_symbol(m, a.old, a.new, reason=a.reason or "")
        except ValueError as e:
            print(f"deprecate: {e}", file=sys.stderr)
            return 2
        m._save(force=True)
        _out(res, a.json) or print(f"deprecated `{res['symbol']}` -> `{res['replacement']}`"
                                   + (f"  ({res['reason']})" if res['reason'] else ""))

    elif a.cmd == "check-code":
        from inspeximus.code_guard import scan_lines
        violations = []
        for path in a.paths:
            try:
                code = open(path, encoding="utf-8", errors="replace").read()
            except OSError as e:
                print(f"check-code: {e}", file=sys.stderr)
                return 2
            for h in scan_lines(m, code):
                h = dict(h, file=path)
                violations.append(h)
        if a.json:
            _out(violations, True)
        else:
            for h in violations:
                print(f"{h['file']}:{h['line']}: resurrected `{h['symbol']}` -> use `{h['replacement']}`"
                      + (f" ({h['reason']})" if h['reason'] else ""))
            print(f"check-code: {'clean' if not violations else str(len(violations)) + ' resurrected deprecated symbol(s)'}",
                  file=sys.stderr)
        return 1 if violations else 0

    elif a.cmd == "distill":
        from inspeximus import default_distiller
        try:
            text = open(a.file, encoding="utf-8").read() if a.file else sys.stdin.read()
        except OSError as e:                    # an unreadable --file deserves the same tidy exit as the
            print(f"distill: {e}", file=sys.stderr)   # missing-endpoint case below, not a raw traceback
            return 2
        try:
            distiller = default_distiller()
        except RuntimeError as e:
            print(f"distill: {e}", file=sys.stderr)
            return 2
        res = m.distill_and_remember(text, distiller)
        m._save(force=True)
        _out(res, a.json) or print(f"distilled: {res.get('captured',0)} kept "
                                   f"({res.get('decisions',0)} decisions, {res.get('facts',0)} facts, "
                                   f"{res.get('dropped',0)} dropped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
