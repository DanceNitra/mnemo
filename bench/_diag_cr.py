"""Diagnose where mnemo loses on MemoryAgentBench CR: retrieval-miss vs reasoning-miss, and whether SEMANTIC
recall lifts the retrieval ceiling over LEXICAL (SOTA lever #1). No LLM in the retrieval-ceiling part — the
ceiling is 'is the gold answer even in the retrieved context'. Writes _diag_cr_result.json."""
import os, sys, json, string, re
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
from memoryagentbench_cr import fact_lines, parse_fact
from mnemo import Mnemo
from huggingface_hub import hf_hub_download
import pandas as pd
import torch
from transformers import AutoModel, AutoTokenizer

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
ROWS = [int(x) for x in (sys.argv[1].split(",") if len(sys.argv) > 1 else ["0", "1", "2"])]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 30
K = 15
HOPS = 2
OUT = Path(__file__).with_name("_diag_cr_result.json")


def load_embed(hf="sentence-transformers/all-MiniLM-L6-v2"):
    tok = AutoTokenizer.from_pretrained(hf)
    mdl = AutoModel.from_pretrained(hf).to(DEVICE).eval()
    cache = {}

    def enc(texts):
        e = tok(list(texts), padding=True, truncation=True, max_length=64, return_tensors="pt").to(DEVICE)
        with torch.no_grad():
            o = mdl(**e); m = e["attention_mask"].unsqueeze(-1).float()
            v = (o.last_hidden_state * m).sum(1) / m.sum(1).clamp(min=1e-9)
        return v.cpu().tolist()

    def warm(texts, bs=512):
        todo = [t for t in dict.fromkeys(texts) if t not in cache]
        for i in range(0, len(todo), bs):
            for t, v in zip(todo[i:i + bs], enc(todo[i:i + bs])):
                cache[t] = v

    def embed(t):
        v = cache.get(t)
        if v is None:
            v = enc([t])[0]; cache[t] = v
        return v
    embed.warm = warm
    return embed


def build_store(lines, embed):
    st = Mnemo(None, embed=embed)
    st.semantic_threshold = 1
    for ln in lines:
        p = parse_fact(ln)
        if p:
            st.remember(ln, key=p[0], object=p[1])
        else:
            st.remember(ln)
    return st


def norm(t):
    t = t.lower(); t = "".join(c for c in t if c not in string.punctuation)
    t = re.sub(r"\b(a|an|the)\b", " ", t); return " ".join(t.split())


def gold_in(ctx_texts, golds):
    c = norm(" ".join(ctx_texts))
    return int(any(norm(g) and norm(g) in c for g in golds))


def iter_ctx(st, q, mode):
    """Iterative retrieval, heuristic next-hop = recall on the values seen so far. Returns the context set."""
    facts = {h["text"] for h in st.recall(q, k=K, mode=mode)}
    for _ in range(HOPS):
        # next-hop query = the accumulated facts' tail tokens (entity chaining, no LLM for the ceiling test)
        seed = " ".join(list(facts)[:8])
        facts |= {h["text"] for h in st.recall(seed, k=K, mode=mode)}
    return facts


def main():
    embed = load_embed()
    p = hf_hub_download("ai-hyz/MemoryAgentBench", "data/Conflict_Resolution-00000-of-00001.parquet", repo_type="dataset")
    df = pd.read_parquet(p)
    res = []
    for ridx in ROWS:
        row = df.iloc[ridx]
        lines = fact_lines(row["context"])
        embed.warm(lines + [f"what is {row['questions'][i]}?" for i in range(min(N, len(row["questions"])))])
        st = build_store(lines, embed)
        qs = list(row["questions"])[:N]
        golds = [list(g) if hasattr(g, "__len__") and not isinstance(g, str) else [g] for g in list(row["answers"])[:N]]
        hit = {"lex_single": 0, "sem_single": 0, "lex_iter": 0, "sem_iter": 0}
        for q, gl in zip(qs, golds):
            lex1 = [h["text"] for h in st.recall(q, k=K, mode="lexical")]
            sem1 = [h["text"] for h in st.recall(q, k=K, mode="semantic")]
            hit["lex_single"] += gold_in(lex1, gl)
            hit["sem_single"] += gold_in(sem1, gl)
            hit["lex_iter"] += gold_in(iter_ctx(st, q, "lexical"), gl)
            hit["sem_iter"] += gold_in(iter_ctx(st, q, "semantic"), gl)
        n = len(qs)
        res.append({"row": ridx, "facts": len(lines), "n": n,
                    **{k: round(v / n, 3) for k, v in hit.items()}})
        print(f"row {ridx} ({len(lines)} facts): retrieval-CEILING (gold-in-ctx)  "
              f"lex single={hit['lex_single']/n:.0%} iter={hit['lex_iter']/n:.0%}  |  "
              f"sem single={hit['sem_single']/n:.0%} iter={hit['sem_iter']/n:.0%}")
    OUT.write_text(json.dumps({"ok": True, "rows": res}, indent=1), encoding="utf-8")


try:
    main()
except Exception as e:
    import traceback
    OUT.write_text(json.dumps({"ok": False, "error": repr(e), "tb": traceback.format_exc()}, indent=1), encoding="utf-8")
