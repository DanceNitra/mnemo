"""Crucible replication + adversarial stress-test: the Generative Agents (Park et al., 2023, arXiv:2304.03442)
memory-retrieval mechanism, and where its linear recency/importance/relevance weighting BREAKS under
contradiction + scale — vs inspeximus's structural supersession.

FAITHFUL GA retrieval (paper, Memory Retrieval): for a query q, each memory m is scored
    score(m) = normalize(recency) + normalize(importance) + normalize(relevance),
  recency   = 0.995 ** hours_since_last_access   (0.5%/hour exponential decay),
  importance= LLM-rated poignancy 1..10 (here drawn realistically, not rigged),
  relevance = cosine(embed(q), embed(m)),
each min-max normalized to [0,1] across the candidate pool, EQUAL weights, then top-k retrieved.

THE FAILURE MODE (measured, not asserted): when a fact is UPDATED, GA keeps both the stale and the fresh
memory. recency is only ONE of three equal terms, so a stale memory with comparable importance/relevance and
only-slightly-lower recency can OUTRANK the fresh one — GA surfaces the stale value. inspeximus's keyed
supersession retires the stale memory, so recall only ever returns the current value.

METRIC (retrieval-level, LLM-free, deterministic): for each updated fact, does the retriever rank the FRESH
memory ABOVE the STALE one (correct), and is the stale value absent from the top-k the agent would act on?
Swept over contradiction density and store scale. FALSIFIER for the replication's headline: if GA does NOT
degrade with contradiction/scale, the "linear weighting is insufficient" claim fails.
"""
import json
import os
import random
import sys

import torch
from transformers import AutoModel, AutoTokenizer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inspeximus import Inspeximus

random.seed(20260716)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DECAY = 0.995            # GA recency decay per hour (paper constant)


def load_embed(hf="sentence-transformers/all-MiniLM-L6-v2"):
    """Memoized + batched embedder. Distractor texts are reused across every condition/seed, so a cache
    means the expensive pool is embedded exactly ONCE (the earlier version re-embedded 10k texts per
    condition and timed out). `warm(texts)` batch-fills the cache up front for speed."""
    tok = AutoTokenizer.from_pretrained(hf)
    mdl = AutoModel.from_pretrained(hf).to(DEVICE).eval()
    cache = {}

    def _encode(texts):
        e = tok(list(texts), padding=True, truncation=True, max_length=64, return_tensors="pt").to(DEVICE)
        with torch.no_grad():
            out = mdl(**e)
            mask = e["attention_mask"].unsqueeze(-1).float()
            v = (out.last_hidden_state * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return v.cpu().tolist()

    def warm(texts, bs=512):
        todo = [t for t in dict.fromkeys(texts) if t not in cache]
        for i in range(0, len(todo), bs):
            chunk = todo[i:i + bs]
            for t, v in zip(chunk, _encode(chunk)):
                cache[t] = v

    def embed(t):
        v = cache.get(t)
        if v is None:
            v = _encode([t])[0]
            cache[t] = v
        return v

    embed.warm = warm
    return embed


def _cos(a, b):
    num = sum(x * y for x, y in zip(a, b))
    da = sum(x * x for x in a) ** 0.5
    db = sum(y * y for y in b) ** 0.5
    return num / (da * db) if da and db else 0.0


def _norm(vals):
    lo, hi = min(vals), max(vals)
    return [(v - lo) / (hi - lo) if hi > lo else 0.0 for v in vals]


# A memory record: dict(text, vec, importance 1..10, hours_ago, key, value, is_stale)
def ga_topk(mems, qvec, k):
    """Faithful GA retrieval: equal-weight sum of min-max-normalized recency, importance, relevance."""
    rec = [DECAY ** m["hours_ago"] for m in mems]
    imp = [m["importance"] for m in mems]
    rel = [_cos(qvec, m["vec"]) for m in mems]
    nr, ni, nl = _norm(rec), _norm(imp), _norm(rel)
    scored = sorted(range(len(mems)), key=lambda i: nr[i] + ni[i] + nl[i], reverse=True)
    return [mems[i] for i in scored[:k]]


SUBJECTS = ["the production payments vendor", "the on-call contact", "the backup schedule",
            "the data retention window", "the approved cloud region", "the release sign-off owner",
            "the sev-1 threshold", "the vendor review cadence", "the deploy freeze window",
            "the PII access path", "the staging reset time", "the incident channel",
            "the rollback owner", "the api rate limit", "the log retention", "the oncall rotation",
            "the secrets store", "the canary percentage", "the alert threshold", "the db failover target"]
VALUES = ["Stripe", "Dana Ruiz", "02:00 UTC", "30 days", "eu-central-1", "the QA lead", "any data loss",
          "every 6 months", "Fridays 15:00", "manager plus security", "Sunday 23:00", "#incidents",
          "Priya", "1000 rps", "90 days", "weekly", "Vault", "5 percent", "p99 200ms", "replica-2"]
NEW = ["Adyen", "Sam Cole", "03:30 UTC", "90 days", "us-east-1", "any engineer", "full outage",
       "yearly", "never", "self-approval", "Sunday 01:00", "#war-room", "Alex", "5000 rps",
       "1 year", "daily", "1Password", "10 percent", "p99 500ms", "replica-4"]
FILLER = ["the coffee machine descales monthly", "the standup is at 09:30", "parking renews in August",
          "the wiki reindexes overnight", "the sprint is two weeks", "the office recycles on tuesday"]


def build(embed, n_facts, contra_frac, scale_distractors):
    """Return (ga_mems, inspeximus_store, updated_keys) with `contra_frac` of facts UPDATED (stale+fresh both
    present for GA; superseded in inspeximus), plus `scale_distractors` unrelated old memories to stress scale."""
    facts = list(zip(SUBJECTS, VALUES, NEW))[:n_facts]
    ga, updated = [], []
    st = Inspeximus(None, embed=embed)
    st.semantic_threshold = 1
    for subj, old, new in facts:
        key = subj.lower()
        updated_this = random.random() < contra_frac
        # base (older) memory
        old_txt = f"{subj} is {old}"
        ga.append({"text": old_txt, "vec": embed(old_txt), "importance": random.randint(3, 9),
                   "hours_ago": random.uniform(24, 240), "key": key, "value": old, "is_stale": updated_this})
        st.remember(old_txt, key=key, object=old)
        if updated_this:
            new_txt = f"{subj} is now {new}"
            ga.append({"text": new_txt, "vec": embed(new_txt), "importance": random.randint(3, 9),
                       "hours_ago": random.uniform(0, 6), "key": key, "value": new, "is_stale": False})
            st.remember(new_txt, key=key, object=new)   # supersedes old for this key
            updated.append((subj, key, new, old))
    # scale distractors (unrelated, aged) — stress the min-max normalization + top-k competition.
    # DETERMINISTIC text per index so the embedder cache is reused across seeds/conditions (the earlier
    # random.choice made every text unique -> cache-miss -> timeout).
    for i in range(scale_distractors):
        f = f"{FILLER[i % len(FILLER)]} (note {i})"
        ga.append({"text": f, "vec": embed(f), "importance": random.randint(1, 6),
                   "hours_ago": random.uniform(1, 500), "key": None, "value": None, "is_stale": False})
        st.remember(f)
    return ga, st, updated


def run(embed, n_facts=20, contra_frac=0.5, scale_distractors=0, k=8):
    ga, st, updated = build(embed, n_facts, contra_frac, scale_distractors)
    if not updated:
        return None
    ga_correct = inspeximus_correct = ga_stale = inspeximus_stale = 0
    for subj, key, new, old in updated:
        q = f"what is {subj}?"
        qv = embed(q)
        top = ga_topk(ga, qv, k)
        keyed = [m for m in top if m["key"] == key]
        ga_ans = keyed[0]["value"] if keyed else None
        ga_correct += int(ga_ans == new)
        ga_stale += int(any(m["key"] == key and m["value"] == old for m in top))   # stale in GA's top-k
        # inspeximus: recall EXCLUDES superseded by default -> only the current (fresh) record survives.
        # recall hits carry text (not key/object), so match on the value string in the text.
        hits = st.recall(q, k=k, mode="semantic")
        sub_hits = [h for h in hits if subj.lower() in h["text"].lower()]
        top_txt = sub_hits[0]["text"].lower() if sub_hits else ""
        inspeximus_correct += int(new.lower() in top_txt)
        inspeximus_stale += int(any(subj.lower() in h["text"].lower() and old.lower() in h["text"].lower()
                              for h in hits))                                        # stale leaked into inspeximus recall
    m = len(updated)
    return {"n_facts": n_facts, "contra_frac": contra_frac, "scale_distractors": scale_distractors,
            "updated": m, "ga_acc": round(ga_correct / m, 3), "inspeximus_acc": round(inspeximus_correct / m, 3),
            "ga_stale_ctx": round(ga_stale / m, 3), "inspeximus_stale_ctx": round(inspeximus_stale / m, 3)}


if __name__ == "__main__":
    embed = load_embed()
    MAXSCALE = 5000
    # warm the embedder cache once: all fact/query texts + the full distractor pool (embedded ONE time)
    warm = [f"{s} is {v}" for s, v in zip(SUBJECTS, VALUES)] + [f"{s} is now {v}" for s, v in zip(SUBJECTS, NEW)]
    warm += [f"what is {s}?" for s in SUBJECTS]
    warm += [f"{FILLER[i % len(FILLER)]} (note {i})" for i in range(MAXSCALE)]
    print(f"warming embedder cache ({len(warm)} texts)...")
    embed.warm(warm)
    OUT = []
    print("=== GA retrieval vs inspeximus supersession: contradiction + scale sweep ===")
    for contra in (0.2, 0.5, 0.9):
        for scale in (0, 1000, MAXSCALE):
            # average over 2 seeds for stability
            accs = []
            for s in range(2):
                random.seed(20260716 + s)
                r = run(embed, n_facts=20, contra_frac=contra, scale_distractors=scale, k=8)
                if r:
                    accs.append(r)
            if accs:
                ga = round(sum(a["ga_acc"] for a in accs) / len(accs), 3)
                mn = round(sum(a["inspeximus_acc"] for a in accs) / len(accs), 3)
                gs = round(sum(a["ga_stale_ctx"] for a in accs) / len(accs), 3)
                ms = round(sum(a["inspeximus_stale_ctx"] for a in accs) / len(accs), 3)
                row = {"contra_frac": contra, "scale": scale, "ga_acc": ga, "inspeximus_acc": mn,
                       "ga_stale_ctx": gs, "inspeximus_stale_ctx": ms}
                OUT.append(row)
                print(f"contra={contra:.0%} scale={scale:6d}: acc GA={ga:.0%}/inspeximus={mn:.0%}  |  "
                      f"STALE-in-context GA={gs:.0%}/inspeximus={ms:.0%}")
    json.dump(OUT, open(os.path.join(os.path.dirname(__file__), "generative_agents_retrieval_stress_result.json"), "w"), indent=1)
