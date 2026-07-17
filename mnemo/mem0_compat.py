"""mem0-compatible drop-in for mnemo — change ONE import, get deterministic correction integrity.

    from mnemo.mem0 import Memory      # was:  from mem0 import Memory

Same surface you already use (`add` / `search` / `get` / `get_all` / `update` / `delete` / `delete_all` /
`history` / `reset`), backed by mnemo. What you get for free: when a fact is corrected and the OLD value is
later *restated* — a user repeating a preference they forgot they changed, or one stray line in a long chat —
mnemo keeps the correction. A similarity store revives the stale value ~47% of the time (measured, n=30:
mem0 2.0.11 scored 0.53 echo-resistance; this drop-in scores 1.00 — github.com/DanceNitra/ramr).

How it decides "same fact": mnemo supersedes by an explicit KEY (subject-relation), not by cosine similarity
(which can't tell a contradiction from a duplicate). The drop-in derives that key two ways:
  1. explicit — pass metadata={"mnemo_key": "user/region", "mnemo_object": "Ohio"} for precise control;
  2. automatic — for simple "<subject> is/are/was <value>" statements the key/value are parsed out, so
     plain mem0 code (add("the region is Frankfurt"); add("region is Ohio")) auto-supersedes with no changes.
Statements it can't key are stored as ordinary memories (no supersession) — exactly like mem0 without infer.

Honest scope: this is a drop-in for the STORAGE + CORRECTION layer, not a re-implementation of mem0's
LLM fact-extraction. Recall is mnemo's (lexical unless you wire an embedder). The edge is integrity:
deterministic supersession, echo-resistance, revert — tested in the open.
"""
import re
from .mnemo import Mnemo

# Light, deterministic key/value extractor for "<subject phrase> is/are/was/were <value>" facts.
# Key = everything up to and including the copula (lower-cased); value = the trailing phrase.
_COPULA = re.compile(r'^(.*?\b(?:is|are|was|were)\b)\s+(.+?)\.?$', re.IGNORECASE)
# strip a leading "correction:", "update:", "reminder:", "actually," etc. before keying
_LEAD = re.compile(r'^\s*(?:correction|update|reminder|note|fyi|actually|btw)\s*[:,-]?\s*', re.IGNORECASE)


def _derive_key_object(text, metadata):
    md = metadata or {}
    if md.get("mnemo_key"):
        return md["mnemo_key"], md.get("mnemo_object")
    body = _LEAD.sub("", text.strip())
    m = _COPULA.match(body)
    if m:
        return m.group(1).strip().lower(), m.group(2).strip().rstrip(".")
    return None, None


def _text_of(messages):
    if isinstance(messages, str):
        return messages
    if isinstance(messages, dict):
        return messages.get("content", "")
    if isinstance(messages, list):
        return " ".join(
            (mm.get("content", "") if isinstance(mm, dict) else str(mm)) for mm in messages
        ).strip()
    return str(messages)


class Memory:
    """Drop-in replacement for mem0.Memory with deterministic, echo-resistant correction."""

    def __init__(self, config=None):
        path = None
        if isinstance(config, dict):
            vs = (config.get("vector_store") or {}).get("config") or {}
            path = vs.get("path") or config.get("path")
        self._m = Mnemo(path=path)
        self._m.echo_guard = True                       # the differentiator, on by default
        self.config = config

    @classmethod
    def from_config(cls, config):
        return cls(config)

    # ---- id -> full record helper (recall hits don't carry meta/object) ----
    def _by_id(self):
        return {it["id"]: it for it in self._m.items}

    def _fmt(self, item, score=None):
        meta = dict(item.get("meta") or {})
        uid = meta.pop("user_id", None)
        out = {"id": item["id"], "memory": item.get("text", ""), "metadata": meta}
        if uid is not None:
            out["user_id"] = uid
        if score is not None:
            out["score"] = score
        return out

    # ---- mem0 API ----
    def add(self, messages, *, user_id=None, agent_id=None, run_id=None, metadata=None,
            infer=True, **kwargs):
        uid = user_id or agent_id or run_id
        text = _text_of(messages)
        key, obj = _derive_key_object(text, metadata)
        if key is not None and uid is not None:
            key = f"{uid}::{key}"                        # scope supersession per user — keys must not collide across users
        meta = dict(metadata or {})
        meta.pop("mnemo_key", None); meta.pop("mnemo_object", None)
        if uid is not None:
            meta["user_id"] = uid
        active_before = self._m._current_active(key).get("object") if key and self._m._current_active(key) else None
        rid = self._m.remember(text, key=key, object=obj, meta=meta or None)
        active_after = self._m._current_active(key).get("object") if key and self._m._current_active(key) else None
        # mem0-style event: UPDATE if this write changed the active value under a key, else ADD
        event = "UPDATE" if (key and active_before is not None and active_after != active_before) else "ADD"
        return {"results": [{"id": rid, "memory": text, "event": event}]}

    def search(self, query, *, top_k=20, limit=None, filters=None, threshold=None, **kwargs):
        f = filters or {}
        uid = f.get("user_id") or f.get("agent_id") or f.get("run_id")
        k = limit or top_k
        where = {"user_id": uid} if uid is not None else None
        hits = self._m.recall(query, k=k, where=where)
        by = self._by_id()
        results = [self._fmt(by.get(h["id"], {"id": h["id"], "text": h.get("text", "")}),
                            score=h.get("score")) for h in hits]
        return {"results": results}

    def get(self, memory_id):
        it = self._by_id().get(memory_id)
        return self._fmt(it) if it else None

    def get_all(self, *, user_id=None, filters=None, top_k=20, limit=None, **kwargs):
        f = filters or {}
        uid = user_id or f.get("user_id") or f.get("agent_id") or f.get("run_id")
        k = limit or top_k
        items = [it for it in self._m.items if it.get("status") == "active"]
        if uid is not None:
            items = [it for it in items if (it.get("meta") or {}).get("user_id") == uid]
        return {"results": [self._fmt(it) for it in items[:k]]}

    def update(self, memory_id, data=None, metadata=None, **kwargs):
        """Update = a keyed correction: supersede the record's key with the new value (echo-resistant)."""
        it = self._by_id().get(memory_id)
        if not it:
            return {"results": []}
        key = it.get("key")
        meta = dict(it.get("meta") or {})
        if metadata:
            meta.update(metadata)
        if key:
            _, obj = _derive_key_object(data or "", metadata)
            rid = self._m.remember(data or it.get("text", ""), key=key, object=obj, meta=meta or None)
            return {"results": [{"id": rid, "memory": data, "event": "UPDATE"}]}
        # no key: overwrite in place via forget + re-add
        self._m.forget(ids=[memory_id])
        rid = self._m.remember(data or it.get("text", ""), meta=meta or None)
        return {"results": [{"id": rid, "memory": data, "event": "UPDATE"}]}

    def delete(self, memory_id):
        self._m.forget(ids=[memory_id])
        return {"message": "Memory deleted successfully!"}

    def delete_all(self, user_id=None, agent_id=None, run_id=None):
        uid = user_id or agent_id or run_id
        ids = [it["id"] for it in self._m.items
               if uid is None or (it.get("meta") or {}).get("user_id") == uid]
        if ids:
            self._m.forget(ids=ids)
        return {"message": "Memories deleted successfully!"}

    def history(self, memory_id):
        """Supersession lineage for the record's key (what corrected what)."""
        it = self._by_id().get(memory_id)
        if not it or not it.get("key"):
            return []
        key = it["key"]
        chain = [x for x in self._m.items if x.get("key") == key]
        chain.sort(key=lambda x: x.get("ts", 0))
        return [{"id": x["id"], "memory": x.get("text", ""), "object": x.get("object"),
                 "status": x.get("status"), "timestamp": x.get("iso")} for x in chain]

    def reset(self):
        ids = [it["id"] for it in self._m.items]
        if ids:
            self._m.forget(ids=ids)
        return {"message": "All memories reset"}
