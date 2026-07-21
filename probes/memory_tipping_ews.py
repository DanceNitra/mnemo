"""MEMORY TIPPING POINTS probe: is catastrophic forgetting in an agent memory a SECOND-ORDER (critical-slowing-
down-warned) transition or a FIRST-ORDER (silent) one — and does the answer depend on the CAUSE of degradation?

Honest design (the anti-'true-by-construction' rule): the degradation dynamics EMERGE from a real inspeximus store
with real embeddings — we do NOT hand-pick a q*(forcing) whose transition order we choose. We only supply:
 - a workload: facts subject->value; quality q_t = fraction of a query sample whose recall top-1 = current value;
 - a RESTORING FORCE: each step we reinforce (inspeximus credit) a random subset of correct facts, so their
   value-weighted recall standing is refreshed — the dynamical 'return to equilibrium' CSD needs to be meaningful;
 - a FORCING that ramps each step, in three regimes:
     A capacity      : add unrelated distractor facts (retrieval SNR pressure);
     B interference  : add near-duplicate colliding facts on the SAME subjects (wrong values);
     C poisoning     : inject on-topic poisoned records that get corroborated (MemoryGraft-style), able to
                       supersede/outrank the correct value.
Whether each regime declines gradually with rising variance + lag-1 autocorrelation BEFORE collapse
(second-order / CSD-warned) or stays flat then falls off a cliff (first-order / silent) is EMERGENT.

FALSIFIER (for the 'complex-systems transfer holds' claim): EWS (rolling variance & lag-1 AC) must rise before
collapse (Kendall tau > 0, AUC(pre-collapse-window) > 0.7) in a regime. The INTERESTING result is differential:
if capacity/interference are CSD-warned but poisoning is SILENT, defenders cannot rely on EWS to catch poisoning.
"""
import json, os, random, sys, math
from pathlib import Path
import torch
from transformers import AutoModel, AutoTokenizer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inspeximus import Inspeximus

random.seed(20260716)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
OUT = Path(__file__).with_name("memory_tipping_ews_result.json")
NBASE = int(os.environ.get("NBASE", 50))          # base facts (the 'signal' the agent must retain)
STEPS = int(os.environ.get("STEPS", 120))
SEEDS = int(os.environ.get("SEEDS", 3))
QSAMPLE = 24                                       # queries sampled per step to estimate quality (adds noise)
WIN = 12                                           # rolling window for EWS
COLLAPSE = 0.30                                    # retrieval quality below this = catastrophic forgetting


def load_embed(hf="sentence-transformers/all-MiniLM-L6-v2"):
    tok = AutoTokenizer.from_pretrained(hf); mdl = AutoModel.from_pretrained(hf).to(DEVICE).eval(); cache = {}
    def enc(texts):
        e = tok(list(texts), padding=True, truncation=True, max_length=48, return_tensors="pt").to(DEVICE)
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


SUBJ = [f"entity_{i:03d}" for i in range(400)]
VAL = [f"value_{i:03d}" for i in range(400)]
DISTR = [f"note_{i:04d} about topic {i%37}" for i in range(6000)]


def variance(xs):
    n = len(xs)
    if n < 2: return 0.0
    m = sum(xs) / n
    return sum((x - m) ** 2 for x in xs) / (n - 1)


def lag1_ac(xs):
    n = len(xs)
    if n < 3: return 0.0
    m = sum(xs) / n
    num = sum((xs[i] - m) * (xs[i - 1] - m) for i in range(1, n))
    den = sum((x - m) ** 2 for x in xs)
    return num / den if den > 1e-12 else 0.0


def kendall_tau(xs):
    """Trend of a series vs its index (concordant-discordant over pairs), in [-1,1]."""
    n = len(xs); c = d = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (xs[j] - xs[i])
            if s > 0: c += 1
            elif s < 0: d += 1
    tot = c + d
    return (c - d) / tot if tot else 0.0


def auc_pre_collapse(indicator, collapse_idx, horizon=12):
    """AUC of the EWS indicator separating the `horizon` steps just before collapse (label 1) from earlier
    steps (label 0) — 'does EWS rise SPECIFICALLY before collapse'. Only over the pre-collapse portion."""
    if collapse_idx is None or collapse_idx < WIN + horizon + 4:
        return None
    idx = list(range(WIN, collapse_idx))
    pos = [i for i in idx if i >= collapse_idx - horizon]
    neg = [i for i in idx if i < collapse_idx - horizon]
    if not pos or not neg: return None
    wins = ties = 0
    for p in pos:
        for q in neg:
            a, b = indicator[p], indicator[q]
            if a > b: wins += 1
            elif a == b: ties += 1
    tot = len(pos) * len(neg)
    return (wins + 0.5 * ties) / tot if tot else None


def run_regime(embed, regime, seed):
    random.seed(seed * 1000 + hash(regime) % 997)
    subs = random.sample(SUBJ, NBASE)
    cur = {s: random.choice(VAL) for s in subs}
    st = Inspeximus(None, embed=embed); st.semantic_threshold = 1
    for s in subs:
        st.remember(f"the {s} is {cur[s]}", key=s, object=cur[s])
    q_series = []
    dpool = iter(DISTR)
    for t in range(STEPS):
        # RESTORING FORCE: reinforce a random subset of correct facts (inspeximus credit raises value-weight)
        for s in random.sample(subs, max(1, NBASE // 6)):
            rid = None
            for h in st.recall(f"the {s} is {cur[s]}", k=3, mode="semantic"):
                if s in h["text"] and cur[s] in h["text"]:
                    rid = h.get("id"); break
            if rid is not None:
                try: st.credit([rid], "good")
                except Exception: pass
        # FORCING ramp (grows with t): the degradation specific to the regime. Rates are calibrated so each
        # regime traverses q~1 -> collapse over the run with a pre-collapse EWS window; the TRANSITION ORDER
        # (gradual-with-CSD vs cliff) is what emerges, NOT set here.
        if regime == "capacity":
            for _ in range(1 + t // 18):
                st.remember(f"the {next(dpool)}")               # unrelated distractors: retrieval SNR pressure
        elif regime == "interference":
            for _ in range(2 + t // 4):
                s = random.choice(subs)
                st.remember(f"the {s} is {random.choice(VAL)}") # colliding wrong value on a real subject, unkeyed
        elif regime == "poisoning":
            for _ in range(2 + t // 5):
                s = random.choice(subs)
                bad = random.choice(VAL)
                rid = st.remember(f"the {s} is {bad}")          # on-topic graft, same form -> competes in recall
                try: st.credit([rid], "good")                   # self-graded corroboration (MemoryGraft hole)
                except Exception: pass
        # MEASURE quality on a noisy sample
        hit = 0; sample = random.sample(subs, min(QSAMPLE, len(subs)))
        for s in sample:
            hits = st.recall(f"what is the {s}?", k=1, mode="semantic")
            if hits and s in hits[0]["text"] and cur[s] in hits[0]["text"]:
                hit += 1
        q_series.append(hit / len(sample))
    # EWS on rolling windows
    rvar = [variance(q_series[max(0, i - WIN):i]) for i in range(len(q_series))]
    rac = [lag1_ac(q_series[max(0, i - WIN):i]) for i in range(len(q_series))]
    # first collapse crossing
    collapse_idx = next((i for i, q in enumerate(q_series) if q < COLLAPSE), None)
    pre = collapse_idx if collapse_idx else len(q_series)
    tau_var = kendall_tau(rvar[WIN:pre]) if pre > WIN + 3 else None
    tau_ac = kendall_tau(rac[WIN:pre]) if pre > WIN + 3 else None
    # shape: cliff-ratio = biggest single-step drop / total drop (high => first-order/silent)
    drops = [q_series[i - 1] - q_series[i] for i in range(1, pre or 1)]
    total_drop = max(1e-9, q_series[0] - (q_series[pre - 1] if pre else q_series[-1]))
    cliff = (max(drops) / total_drop) if drops else 0.0
    return {"regime": regime, "seed": seed, "q_series": [round(x, 3) for x in q_series],
            "collapse_idx": collapse_idx, "q_end": round(q_series[-1], 3),
            "tau_var": None if tau_var is None else round(tau_var, 3),
            "tau_ac": None if tau_ac is None else round(tau_ac, 3),
            "auc_var": auc_pre_collapse(rvar, collapse_idx), "auc_ac": auc_pre_collapse(rac, collapse_idx),
            "cliff_ratio": round(cliff, 3)}


def main():
    embed = load_embed()
    embed.warm([f"the {s} is {v}" for s in SUBJ[:80] for v in VAL[:1]]
               + [f"what is the {s}?" for s in SUBJ[:80]] + DISTR[:400])
    rows = []
    for regime in ("capacity", "interference", "poisoning"):
        for seed in range(SEEDS):
            r = run_regime(embed, regime, seed)
            rows.append(r)
            av = "" if r["auc_var"] is None else f"{r['auc_var']:.2f}"
            print(f"{regime:13s} s{seed}: collapse@{r['collapse_idx']} q_end={r['q_end']:.2f} "
                  f"tau_var={r['tau_var']} tau_ac={r['tau_ac']} auc_var={av} cliff={r['cliff_ratio']:.2f}",
                  flush=True)
        # aggregate
        rs = [x for x in rows if x["regime"] == regime]
        def mean(key):
            vs = [x[key] for x in rs if x[key] is not None]
            return round(sum(vs) / len(vs), 3) if vs else None
        print(f"  == {regime}: mean tau_var={mean('tau_var')} tau_ac={mean('tau_ac')} "
              f"auc_var={mean('auc_var')} cliff={mean('cliff_ratio')} "
              f"collapsed={sum(1 for x in rs if x['collapse_idx'] is not None)}/{len(rs)}", flush=True)
        OUT.write_text(json.dumps({"ok": True, "params": {"NBASE": NBASE, "STEPS": STEPS, "WIN": WIN,
                       "COLLAPSE": COLLAPSE, "QSAMPLE": QSAMPLE}, "rows": rows}, indent=1), encoding="utf-8")


try:
    main()
except Exception as e:
    import traceback
    OUT.write_text(json.dumps({"ok": False, "error": repr(e), "tb": traceback.format_exc()}, indent=1), encoding="utf-8")
    print("ERR", e); traceback.print_exc()
