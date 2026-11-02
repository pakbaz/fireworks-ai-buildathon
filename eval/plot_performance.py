"""Performance plot from saved predictions: docs/results/performance_<split>.html (+ PNG via headless Chrome).

    python3 eval/plot_performance.py dev 50      # first 50 dev cases
    python3 eval/plot_performance.py test        # whole test split, rows that have finished
"""
import html, json, os, sys
split = sys.argv[1]; limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
cases = [json.loads(l) for l in open(f"data/{split}.jsonl")]
if limit: cases = cases[:limit]
lab = {c["case_id"]: c["label"] for c in cases}
ROWS = [("kimi_alone", "Kimi K3 alone (frontier)"), ("glm_alone", "GLM 5.3 Flash alone"),
        ("glm_harness", "GLM + harness, no wiki"), ("glm_harness_wiki", "GLM + harness + wiki (ours)")]
data = []
for key, name in ROWS:
    p = f"runs/{key}/{split}.jsonl"
    if not os.path.exists(p): continue
    preds = {json.loads(l)["case_id"]: json.loads(l) for l in open(p)}
    ids = [i for i in lab if i in preds]
    if len(ids) < len(lab): continue  # only rows that covered every case
    real = [i for i in ids if lab[i]["real_discrepancy"]]; fine = [i for i in ids if lab[i]["stratum"] in ("clean", "messy")]
    caught = sum(preds[i]["action"] == "ESCALATE" for i in real); fp = sum(preds[i]["action"] == "ESCALATE" for i in fine)
    cost = 100 * sum(preds[i]["cost_usd"] for i in ids) / len(ids)
    data.append({"key": key, "name": name, "caught": caught, "real": len(real), "fp": fp, "fine": len(fine), "cost": cost, "n": len(ids)})
n = data[0]["n"] if data else 0
panels = [("Real problems caught", "higher is better", lambda d: d["caught"] / d["real"], lambda d: f"{d['caught']}/{d['real']}", 1.0),
          ("Fine invoices sent to a person", "lower is better", lambda d: d["fp"] / d["fine"], lambda d: f"{d['fp']}/{d['fine']}", max([d["fp"] / d["fine"] for d in data] + [0.05]) * 1.15),
          ("Model cost per 100 invoices", "lower is better", lambda d: d["cost"], lambda d: f"${d['cost']:.2f}", max([d["cost"] for d in data] + [0.01]) * 1.15)]
W, ROWH, LBL = 300, 44, 0
svgs = []
for title, hint, val, txt, vmax in panels:
    rows = []
    for i, d in enumerate(data):
        v = val(d); w = max(2, (W - 70) * v / vmax); y = 10 + i * ROWH
        ours = d["key"] == "glm_harness_wiki"
        rows.append(f'<g class="bar" tabindex="0"><title>{html.escape(d["name"])}: {html.escape(txt(d))}</title>'
                    f'<rect x="0" y="{y}" width="{W-70}" height="28" fill="transparent"/>'
                    f'<path d="M0,{y} h{w-4} a4,4 0 0 1 4,4 v20 a4,4 0 0 1 -4,4 h-{w-4} z" fill="var({"--ours" if ours else "--other"})"/>'
                    f'<text x="{w+6}" y="{y+19}" class="v{" b" if ours else ""}">{html.escape(txt(d))}</text></g>')
    svgs.append(f'<figure><figcaption><b>{title}</b><span>{hint}</span></figcaption><svg viewBox="0 0 {W} {10+len(data)*ROWH}" role="img" aria-label="{title}">'
                f'<line x1="0" y1="0" x2="0" y2="{10+len(data)*ROWH}" class="axis"/>{"".join(rows)}</svg></figure>')
names = "".join(f'<div class="nm{" b" if d["key"]=="glm_harness_wiki" else ""}" style="height:{ROWH}px">{html.escape(d["name"])}</div>' for d in data)
table = "".join(f'<tr><td>{html.escape(d["name"])}</td><td>{d["caught"]}/{d["real"]}</td><td>{d["fp"]}/{d["fine"]}</td><td>${d["cost"]:.2f}</td></tr>' for d in data)
page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Invoice Reconciliation Results</title>
<style>
:root{{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--grid:#e3e2de;--ours:#2a78d6;--other:#b9b7b0}}
@media (prefers-color-scheme: dark){{:root:where(:not([data-theme="light"])){{--bg:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#3a3936;--ours:#3987e5;--other:#6b6a64}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:22px 16px}}h1{{font-size:20px;margin:0}}.sub{{color:var(--ink2);margin:4px 0 18px}}
.grid{{display:grid;grid-template-columns:230px repeat(3,1fr);gap:18px;align-items:start}}@media (max-width:820px){{.grid{{grid-template-columns:1fr}}}}
.names{{padding-top:38px}}.nm{{display:flex;align-items:center;color:var(--ink2)}}.nm.b{{color:var(--ink);font-weight:700}}
figure{{margin:0;min-width:0}}figcaption{{display:flex;flex-direction:column;height:38px}}figcaption span{{color:var(--ink2);font-size:12px}}
svg{{width:100%;height:auto;overflow:visible}}.axis{{stroke:var(--grid);stroke-width:1}}text.v{{font-size:13px;fill:var(--ink2)}}text.v.b{{fill:var(--ink);font-weight:700}}
.bar:hover path,.bar:focus path{{opacity:.85}}.bar:focus{{outline:none}}
details{{margin-top:18px;color:var(--ink2)}}table{{border-collapse:collapse;margin-top:8px}}td,th{{padding:4px 12px 4px 0;text-align:left;border-bottom:1px solid var(--grid)}}
</style></head><body><main>
<h1>Invoice reconciliation: four ways to read the same invoices</h1>
<p class="sub">{html.escape(split)} split, {n} cases. Same documents, billing history and company pages for every row. Kimi K3 is the frontier baseline; our system runs on GLM 5.3 Flash.</p>
<div class="grid"><div class="names">{names}</div>{"".join(svgs)}</div>
<details><summary>Table view</summary><table><tr><th>Row</th><th>Real problems caught</th><th>Fine invoices sent to a person</th><th>Model cost per 100 invoices</th></tr>{table}</table></details>
</main></body></html>"""
out = f"docs/results/performance_{split}.html"
open(out, "w").write(page)
print(out, [(d["key"], f'{d["caught"]}/{d["real"]}', f'{d["fp"]}/{d["fine"]}', round(d["cost"], 3)) for d in data])
