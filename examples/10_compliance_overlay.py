"""The agent-memory compliance overlay -- turn a live store into an article-labelled EVIDENCE report for the
MEMORY slice of the EU AI Act + GDPR, with live counts. Runnable end-to-end.

Honest scope: this is the memory slice only (records, corrections, erasures in THIS store), and it is EVIDENCE,
not a certification. The Act imposes far more than any memory library can satisfy.

Run: python examples/10_compliance_overlay.py
"""
from inspeximus.core import Inspeximus
from inspeximus.compliance import compliance_report, render_html, _STATUS_LABEL


def main():
    m = Inspeximus(path=None, receipts=True)
    m.remember("data retention policy is 90 days", key="policy::retention", object="90d")
    m.remember("data retention policy is 30 days", key="policy::retention", object="30d")   # a correction (Art.5(1)(d))
    m.remember("user u_17 phone is +100", key="u17::phone", object="+100")
    m.forget(where=lambda r: r.get("key") == "u17::phone")                                   # a right-to-erasure (Art.17)

    rep = compliance_report(m)
    print(f"scope: {rep['scope']}\n")
    for c in rep["controls"]:
        cnt = "" if c["live_count"] is None else f"  (x{c['live_count']})"
        print(f"  [{_STATUS_LABEL.get(c['status'], c['status'])}]{cnt:>10}  {c['framework'].split('(')[0].strip()} "
              f"{c['article']} - {c['title']}")
    print(f"\nsummary: {rep['summary']}")

    html = render_html(rep)
    print(f"\nrender_html -> {len(html)} bytes, self-contained (no external assets, no JS): "
          f"{'http' not in html and '<script' not in html}")
    print("disclaimer carried into the HTML:", "not a certification" in html.lower())

    print("\nRESULT: one command (`inspeximus compliance --out report.html`) turns the store into a DPO-facing\n"
          "        evidence report -- article-labelled, live counts, honest scope. Evidence, not certification.")


if __name__ == "__main__":
    main()
