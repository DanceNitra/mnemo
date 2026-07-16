"""SOTA lever test: mnemo's keyed supersession already holds latest-value-per-key (exactly the CR task). The
missing piece is QUERY-SIDE key resolution: map the question to the right key, then return that key's current
(latest, non-superseded) value deterministically. This bypasses the fuzzy-retrieval ceiling. Measures the
keyed-lookup ceiling (top-1 and top-3 key match) vs the fuzzy ceiling from _diag_cr.py. Writes _diag_cr2_result.json."""
import os, sys, json, string, re
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
from memoryagentbench_cr import fact_lines, parse_fact
from huggingface_hub import hf_hub_download
import pandas as pd, torch
from transformers import AutoModel, AutoTokenizer

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
ROWS = [int(x) for x in (sys.argv[1].split(",") if len(sys.argv) > 1 else ["0", "1", "2"])]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 30
OUT = Path(__file__).with_name("_diag_cr2_result.json")


def load_embed(hf="sentence-transformers/all-MiniLM-L6-v2"):
    tok = AutoTokenizer.from_pretrained(hf); mdl = AutoModel.from_pretrained(hf).to(DEVICE).eval(); cache = {}
    def enc(texts):
        e = tok(list(texts), padding=True, truncation=True, max_length=64, return_tensors="pt").to(DEVICE)
        with torch.no_grad():
            o = mdl(**e); m = e["attention_mask"].unsqueeze(-1).float()
            v = (o.last_hidden_state * m).sum(1) / m.sum(1).clamp(min=1e-9)
        import torch.nn.functional as F
        return F.normalize(v, dim=1).cpu().tolist()
    def warm(texts, bs=512):
        todo = [t for t in dict.fromkeys(texts) if t not in cache]
        for i in range(0, len(todo), bs):
            for t, v in zip(todo[i:i+bs], enc(todo[i:i+bs])): cache[t] = v
    def embed(t):
        v = cache.get(t)
        if v is None: v = enc([t])[0]; cache[t] = v
        return v
    embed.warm = warm; return embed


def norm(t):
    t = t.lower(); t = "".join(c for c in t if c not in string.punctuation)
    t = re.sub(r"\b(a|an|the)\b", " ", t); return " ".join(t.split())


def cos(a, b): return sum(x*y for x, y in zip(a, b))


def main():
    embed = load_embed()
    p = hf_hub_download("ai-hyz/MemoryAgentBench", "data/Conflict_Resolution-00000-of-00001.parquet", repo_type="dataset")
    df = pd.read_parquet(p)
    res = []
    for ridx in ROWS:
        row = df.iloc[ridx]
        lines = fact_lines(row["context"])
        # mnemo supersession result: latest value per key (last write wins), + keyed-fact coverage
        key2val = {}; keyed = 0
        for ln in lines:
            pf = parse_fact(ln)
            if pf: key2val[pf[0]] = pf[1]; keyed += 1
        keys = list(key2val.keys())
        qs = list(row["questions"])[:N]
        golds = [list(g) if hasattr(g, "__len__") and not isinstance(g, str) else [g] for g in list(row["answers"])[:N]]
        embed.warm(keys + qs)
        kvecs = [embed(k) for k in keys]
        top1 = top3 = keyhit = 0
        for q, gl in zip(qs, golds):
            qv = embed(q)
            sims = sorted(range(len(keys)), key=lambda i: cos(qv, kvecs[i]), reverse=True)
            gnorm = [norm(g) for g in gl if norm(g)]
            # top-1: does the single best-matched key's latest value contain the gold?
            v1 = norm(key2val[keys[sims[0]]])
            top1 += int(any(g and g in v1 for g in gnorm))
            # top-3: gold among the 3 best-matched keys' latest values
            v3 = " ".join(norm(key2val[keys[i]]) for i in sims[:3])
            top3 += int(any(g and g in v3 for g in gnorm))
            # is the gold value present as SOME key's latest value at all (parser+supersession ceiling)?
            allv = " ".join(norm(v) for v in key2val.values())
            keyhit += int(any(g and g in allv for g in gnorm))
        n = len(qs)
        res.append({"row": ridx, "facts": len(lines), "keyed_facts": keyed, "keys": len(keys), "n": n,
                    "keyed_top1": round(top1/n, 3), "keyed_top3": round(top3/n, 3),
                    "gold_is_a_latest_value": round(keyhit/n, 3)})
        print(f"row {ridx} ({len(lines)}f, {len(keys)} keys): KEYED-LOOKUP top1={top1/n:.0%} top3={top3/n:.0%} "
              f"| gold-is-some-latest-value={keyhit/n:.0%}")
    OUT.write_text(json.dumps({"ok": True, "rows": res}, indent=1), encoding="utf-8")


try:
    main()
except Exception as e:
    import traceback
    OUT.write_text(json.dumps({"ok": False, "error": repr(e), "tb": traceback.format_exc()}, indent=1), encoding="utf-8")
