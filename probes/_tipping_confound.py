"""Confound check on memory_tipping_ews: is the pre-collapse variance rise genuine critical-slowing-down, or a
BINOMIAL SAMPLING ARTIFACT? Quality q_t = hits/QSAMPLE is a binomial rate; its sampling variance p(1-p)/n
mechanically PEAKS at p=0.5, which the series crosses on its way 1->0. Real CSD lives in the variance of
FLUCTUATIONS AROUND the moving mean (detrended) and in rising lag-1 autocorrelation (white sampling noise
LOWERS AC1). Recompute from saved q_series (no re-run): raw-var AUC vs DETRENDED-var AUC vs the binomial
prediction. If detrended-var AUC collapses toward 0.5 and raw-var tracks p(1-p)/n, the CSD signal is an artifact."""
import json
from pathlib import Path

D = json.loads(Path(__file__).with_name("memory_tipping_ews_result.json").read_text(encoding="utf-8"))
WIN = D["params"]["WIN"]; QS = D["params"]["QSAMPLE"]; COLL = D["params"]["COLLAPSE"]


def var(xs):
    n = len(xs)
    if n < 2: return 0.0
    m = sum(xs) / n; return sum((x - m) ** 2 for x in xs) / (n - 1)


def ac1(xs):
    n = len(xs)
    if n < 3: return 0.0
    m = sum(xs) / n
    num = sum((xs[i] - m) * (xs[i - 1] - m) for i in range(1, n)); den = sum((x - m) ** 2 for x in xs)
    return num / den if den > 1e-12 else 0.0


def auc(ind, coll, horizon=10):
    if coll is None or coll < WIN + horizon + 3: return None
    idx = list(range(WIN, coll)); pos = [i for i in idx if i >= coll - horizon]; neg = [i for i in idx if i < coll - horizon]
    if not pos or not neg: return None
    w = t = 0
    for p in pos:
        for q in neg:
            if ind[p] > ind[q]: w += 1
            elif ind[p] == ind[q]: t += 1
    return (w + 0.5 * t) / (len(pos) * len(neg))


def rollmean(xs, i, w):
    seg = xs[max(0, i - w):i]; return sum(seg) / len(seg) if seg else xs[i]


print(f"{'regime':13s} {'seed':4s} {'coll':4s} | raw_varAUC det_varAUC det_ac1AUC | corr(rawvar,binom)")
agg = {}
for r in D["rows"]:
    q = r["q_series"]; coll = r["collapse_idx"]
    if coll is None:
        continue
    raw_var = [var(q[max(0, i - WIN):i]) for i in range(len(q))]
    resid = [q[i] - rollmean(q, i, WIN) for i in range(len(q))]          # detrend: fluctuation around moving mean
    det_var = [var(resid[max(0, i - WIN):i]) for i in range(len(q))]
    det_ac1 = [ac1(resid[max(0, i - WIN):i]) for i in range(len(q))]
    binom = [(qi * (1 - qi) / QS) for qi in q]                            # expected sampling variance at each step
    # correlation between raw rolling variance and the binomial prediction over the pre-collapse window
    a = raw_var[WIN:coll]; b = binom[WIN:coll]
    if len(a) > 3:
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        sa = (sum((x - ma) ** 2 for x in a)) ** .5; sb = (sum((y - mb) ** 2 for y in b)) ** .5
        corr = cov / (sa * sb) if sa * sb > 1e-12 else 0.0
    else:
        corr = None
    rv, dv, da = auc(raw_var, coll), auc(det_var, coll), auc(det_ac1, coll)
    print(f"{r['regime']:13s} s{r['seed']:<3d} {coll:<4d} | "
          f"{('%.2f'%rv) if rv else '  - ':>9s} {('%.2f'%dv) if dv else '  - ':>10s} "
          f"{('%.2f'%da) if da else '  - ':>10s} | {('%.2f'%corr) if corr is not None else '-'}")
    ag = agg.setdefault(r["regime"], {"rv": [], "dv": [], "da": [], "corr": []})
    for k, v in (("rv", rv), ("dv", dv), ("da", da), ("corr", corr)):
        if v is not None: ag[k].append(v)

print("\n=== means (collapsing regimes only) ===")
for reg, a in agg.items():
    def m(k): return round(sum(a[k]) / len(a[k]), 3) if a[k] else None
    print(f"{reg:13s} raw_varAUC={m('rv')}  detrended_varAUC={m('dv')}  detrended_ac1AUC={m('da')}  "
          f"corr(rawvar,binom)={m('corr')}  (n={len(a['rv'])})")
print("\nReading: if raw_varAUC>>detrended_varAUC and corr(rawvar,binom)~1, the 'EWS' is a binomial artifact,")
print("not critical slowing down. Genuine CSD would keep detrended_varAUC and detrended_ac1AUC high (>0.7).")
