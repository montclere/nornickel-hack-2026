# -*- coding: utf-8 -*-
"""HTML-отчёт: граф знаний (послойный SVG) + карточки гипотез. Самодостаточный."""
from __future__ import annotations

import html


def _esc(x):
    return html.escape(str(x if x is not None else ""))


# ─────────────────────────── граф знаний (SVG) ───────────────────────────
PREFIX = {"el": "element", "cls": "class", "form": "form"}


def _graph_svg(layered):
    cols = {"element": 60, "class": 430, "form": 610}
    boxw = {"element": 90, "class": 150, "form": 250}
    W, pad, row_h = 900, 30, 60
    layers = layered["layers"]
    n_rows = max(len(layers["class"]), len(layers["form"]), 1)
    H = pad * 2 + n_rows * row_h

    pos = {}
    for kind, xs in cols.items():
        nodes = layers[kind]
        n = len(nodes) or 1
        for i, nd in enumerate(nodes):
            y = pad + (H - 2 * pad) * (i + 0.5) / n
            pos[nd["id"]] = (xs, y, nd)

    maxt = max((e["tonnes"] for e in layered["edges"]), default=1) or 1
    edges_svg = ""
    for e in layered["edges"]:
        if e["src"] not in pos or e["dst"] not in pos:
            continue
        x1, y1, sd = pos[e["src"]]
        x2, y2, dd = pos[e["dst"]]
        x1r = x1 + boxw[PREFIX[e["src"].split(":")[0]]] / 2
        x2l = x2 - boxw[PREFIX[e["dst"].split(":")[0]]] / 2
        w = 1 + 5 * (e["tonnes"] / maxt)
        color = "#12b3ab" if e.get("recoverable") else (
            "#1f7ae0" if e["kind"] == "loses" else "#d3dee6")
        mx = (x1r + x2l) / 2
        edges_svg += (f'<path d="M{x1r:.0f},{y1:.0f} C{mx:.0f},{y1:.0f} '
                      f'{mx:.0f},{y2:.0f} {x2l:.0f},{y2:.0f}" fill="none" '
                      f'stroke="{color}" stroke-width="{w:.1f}" opacity="0.55"/>')

    nodes_svg = ""
    for nid, (x, y, nd) in pos.items():
        kind = PREFIX[nid.split(":")[0]]
        w = boxw[kind]
        if kind == "element":
            fill, stroke, tcol = "#1f7ae0", "#1f7ae0", "#fff"
        elif kind == "class":
            fill, stroke, tcol = "#eaf3fd", "#bcdcfa", "#12303f"
        else:
            rec = nd.get("recoverable")
            fill = "#e6f7f5" if rec else "#f2f5f7"
            stroke = "#9fe3dd" if rec else "#dbe4ea"
            tcol = "#0a7f79" if rec else "#8aa0ac"
        label = _esc(nd["label"])
        if len(label) > 24:
            label = label[:23] + "…"
        nodes_svg += (
            f'<g><rect x="{x-w/2:.0f}" y="{y-15:.0f}" width="{w}" height="30" rx="8" '
            f'fill="{fill}" stroke="{stroke}"/>'
            f'<text x="{x:.0f}" y="{y+4:.0f}" text-anchor="middle" font-size="11.5" '
            f'fill="{tcol}">{label}</text></g>')

    heads = (f'<text x="{cols["element"]}" y="18" text-anchor="middle" font-size="11" '
             f'fill="#8aa0ac">ЭЛЕМЕНТ</text>'
             f'<text x="{cols["class"]}" y="18" text-anchor="middle" font-size="11" '
             f'fill="#8aa0ac">КЛАСС КРУПНОСТИ</text>'
             f'<text x="{cols["form"]}" y="18" text-anchor="middle" font-size="11" '
             f'fill="#8aa0ac">МИНЕРАЛЬНАЯ ФОРМА</text>')
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" '
            f'xmlns="http://www.w3.org/2000/svg">{heads}{edges_svg}{nodes_svg}</svg>')


# ─────────────────────────── карточки ───────────────────────────
def _card(h):
    m = h.metrics
    impact_pct = round(m["impact"] * 100)
    alts = "".join(f"<li>{_esc(a)}</li>" for a in h.alternatives)
    ev = "".join(f'<div class="ev"><span>{_esc(e["label"])}</span>'
                 f'<em>{_esc(e["cell"])}</em></div>' for e in h.evidence)
    return f"""
    <article class="card">
      <div class="chead">
        <div class="rank">#{h.rank}</div>
        <div class="money">{impact_pct}%<span>извлекаемых потерь фабрики</span></div>
        <div class="fam">{_esc(h.family)}</div>
      </div>
      <div class="tri">
        <div class="row"><span class="lab">если</span><p>{_esc(h.statement_if)}</p></div>
        <div class="row"><span class="lab">то</span><p>{_esc(h.statement_then)}</p></div>
        <div class="row"><span class="lab because">потому что</span>
          <p class="muted">{_esc(h.statement_because)}</p></div>
      </div>
      <div class="bars">
        <div class="bar-row"><div class="bar-head"><span>impact — масштаб потери</span><b>{impact_pct}%</b></div>
          <div class="bar"><i style="width:{min(m['impact']*100,100):.0f}%"></i></div></div>
        <div class="bar-row"><div class="bar-head"><span>addressability — «излечимость»</span><b>{m['addressability']}</b></div>
          <div class="bar"><i style="width:{m['addressability']*100:.0f}%"></i></div></div>
        <div class="pills">
          <div class="pill"><b>{m['rec_tonnes'].get('Ni',0)}</b><span>т Ni извлек.</span></div>
          <div class="pill"><b>{m['rec_tonnes'].get('Cu',0)}</b><span>т Cu извлек.</span></div>
          <div class="pill"><b>{m['clarity']}</b><span>ясность механизма</span></div>
          <div class="pill"><b>{m['feasibility']}</b><span>реализуемость</span></div>
        </div>
      </div>
      <div class="alts"><b>Альтернативы:</b><ul>{alts}</ul></div>
      <div class="evidence"><b>Заземление (ячейки отчёта):</b>{ev}</div>
    </article>"""


def _liberation_svg(lib):
    if not lib:
        return ""
    W, H, pad = 620, 210, 34
    n = len(lib)
    xs = [pad + (W - 2 * pad) * i / max(n - 1, 1) for i in range(n)]
    def y(p):
        return H - pad - (H - 2 * pad) * p / 100
    def poly(key, color):
        pts = " ".join(f"{xs[i]:.0f},{y(r[key]):.0f}" for i, r in enumerate(lib))
        dots = "".join(f'<circle cx="{xs[i]:.0f}" cy="{y(r[key]):.0f}" r="3.5" '
                       f'fill="{color}"/>' for i, r in enumerate(lib))
        return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>{dots}'
    grid = "".join(f'<line x1="{pad}" y1="{y(v):.0f}" x2="{W-pad}" y2="{y(v):.0f}" '
                   f'stroke="#eef4f7"/><text x="{pad-6}" y="{y(v)+4:.0f}" text-anchor="end" '
                   f'font-size="9" fill="#9db3bf">{v}%</text>' for v in (0, 25, 50, 75, 100))
    labels = "".join(f'<text x="{xs[i]:.0f}" y="{H-10}" text-anchor="middle" font-size="10" '
                     f'fill="#5f7d8c">{_esc(r["class"])}</text>' for i, r in enumerate(lib))
    return (f'<svg viewBox="0 0 {W} {H}" width="100%">{grid}'
            f'{poly("locked_pct","#1f7ae0")}{poly("recoverable_pct","#12b3ab")}{labels}</svg>')


def _analysis_html(a):
    if not a:
        return ""
    grind = a.get("optimal_grind")
    grind_html = (f'<div class="grind">🎯 <b>Обрыв раскрытия</b> до класса <b>{_esc(grind)}</b> — '
                  f'закрытого Pnt больше раскрытого; измельчать мельче этой границы.</div>'
                  if grind else "")
    tos = "".join(f'<div class="warn">⚠ {_esc(t)}</div>' for t in a.get("tradeoffs", []))
    forms = "".join(
        f'<tr class="{"rec" if r["recoverable"] else "norec"}"><td>{"✓" if r["recoverable"] else "✗"}</td>'
        f'<td>{_esc(r["form"])}</td><td>{r["tonnes"]} т</td><td>{r["share_pct"]}%</td>'
        f'<td>{_esc(r["status"])}</td><td class="why">{_esc(r["why"])}</td></tr>'
        for r in a.get("forms", []))
    return f"""
  <div class="panel">
    <h2>Кривая раскрытия по крупности</h2>
    <div class="h-sub">как меняется форма Ni с размером частиц (данные отчёта, детерминированно)</div>
    {_liberation_svg(a.get("liberation", []))}
    <div class="legend">
      <span><i style="background:#1f7ae0"></i>закрытый Pnt (заперт в сростках)</span>
      <span><i style="background:#12b3ab"></i>извлекаемо всего</span>
    </div>
    {grind_html}{tos}
  </div>
  <div class="panel">
    <h2>Куда физически уходит Ni (по формам)</h2>
    <div class="h-sub">не всё извлекаемо: часть Ni в силикатах/пирротине — потолок реального извлечения</div>
    <table class="forms"><thead><tr><th></th><th>форма</th><th>т Ni</th><th>доля</th>
      <th>статус</th><th>почему</th></tr></thead><tbody>{forms}</tbody></table>
  </div>"""


def render(profile, layered, hyps, kpi="", tech=None, analysis=None):
    total_ni = round(sum(h.metrics["rec_tonnes"].get("Ni", 0) for h in hyps), 1)
    total_cu = round(sum(h.metrics["rec_tonnes"].get("Cu", 0) for h in hyps), 1)
    cards = "\n".join(_card(h) for h in hyps)
    graph = _graph_svg(layered)
    techln = ""
    if tech:
        techln = (f'<div class="tech">детерминированный проход · '
                  f'{tech.get("seconds","—")} c · LLM-полировка: '
                  f'{tech.get("llm","нет")} · граф: {tech.get("nodes","?")} узлов / '
                  f'{tech.get("edges","?")} рёбер</div>')
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Фабрика гипотез · {_esc(profile.fabric)}</title>
<style>
:root{{--ink:#12303f;--muted:#5f7d8c;--blue:#1f7ae0;--teal:#12b3ab;--teal-soft:#e6f7f5;--line:#e6eef3}}
*{{box-sizing:border-box}} body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;
  background:linear-gradient(180deg,#e7f3fa,#eef6fb);color:var(--ink);line-height:1.55}}
.wrap{{max-width:940px;margin:0 auto;padding:38px 22px 70px}}
h1{{margin:0;font-size:27px;font-weight:800;letter-spacing:-.4px}} h1 span{{color:var(--teal)}}
.sub{{color:var(--muted);font-size:13.5px;margin-top:4px}}
.kpi{{background:var(--teal-soft);border:1px solid #cdeeea;border-radius:14px;padding:13px 17px;margin:20px 0 8px}}
.kpi b{{color:var(--blue)}}
.summary{{display:flex;gap:22px;flex-wrap:wrap;margin:8px 2px 18px;font-size:13px;color:var(--muted)}}
.summary b{{color:var(--ink);font-size:17px}}
.tech{{font-size:12px;color:#9db3bf;margin:2px 2px 16px}}
.panel{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px 18px;margin:0 0 22px;
  box-shadow:0 2px 12px rgba(31,122,224,.06);overflow-x:auto}}
.panel h2{{margin:0 0 4px;font-size:15px}} .panel .h-sub{{color:var(--muted);font-size:12px;margin-bottom:8px}}
.legend{{display:flex;gap:16px;font-size:11.5px;color:var(--muted);margin-top:6px;flex-wrap:wrap}}
.legend i{{display:inline-block;width:22px;height:4px;border-radius:2px;vertical-align:middle;margin-right:5px}}
.card{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px 22px;margin:0 0 16px;
  box-shadow:0 2px 12px rgba(31,122,224,.06)}}
.chead{{display:flex;align-items:center;gap:12px;margin-bottom:12px}}
.rank{{font-size:16px;font-weight:800;color:#fff;background:linear-gradient(135deg,var(--blue),var(--teal));
  width:38px;height:38px;border-radius:10px;display:flex;align-items:center;justify-content:center}}
.money{{font-size:19px;font-weight:800;color:var(--blue);display:flex;flex-direction:column;line-height:1}}
.money span{{font-size:10px;font-weight:600;color:var(--muted)}}
.fam{{margin-left:auto;font-size:11.5px;font-weight:700;color:#0a7f79;background:var(--teal-soft);
  padding:5px 12px;border-radius:20px}}
.tri .row{{display:flex;gap:12px;align-items:baseline;margin:6px 0}}
.lab{{flex:0 0 92px;text-align:right;font-size:10.5px;font-weight:700;letter-spacing:.5px;
  text-transform:uppercase;color:var(--teal)}} .lab.because{{color:#9db3bf}}
.tri p{{margin:0;font-size:15px;overflow-wrap:anywhere}} .tri .muted{{color:var(--muted);font-size:13.5px}}
.bars{{margin:14px 0 10px}} .bar-head{{display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted)}}
.bar-head b{{color:var(--ink)}} .bar{{height:8px;background:#eaf1f5;border-radius:6px;margin:5px 0 12px;overflow:hidden}}
.bar i{{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--teal))}}
.pills{{display:flex;gap:10px;flex-wrap:wrap}}
.pill{{background:#f5fafd;border:1px solid var(--line);border-radius:11px;padding:7px 13px;
  display:flex;flex-direction:column;align-items:center;min-width:82px}}
.pill b{{font-size:15px;font-weight:800}} .pill span{{font-size:10px;color:var(--muted)}}
.alts{{font-size:13px;margin:10px 0}} .alts b{{font-size:11px;text-transform:uppercase;color:#9db3bf}}
.alts ul{{margin:5px 0 0;padding-left:18px;color:#37505c}} .alts li{{margin:2px 0}}
.evidence{{font-size:12px;margin-top:8px}} .evidence>b{{font-size:11px;text-transform:uppercase;color:#9db3bf}}
.ev{{display:flex;justify-content:space-between;gap:10px;padding:3px 0;border-bottom:1px dashed var(--line)}}
.ev em{{color:#9db3bf;font-style:normal}}
.grind{{background:#eefaf8;border:1px solid #bfe9e4;border-radius:10px;padding:10px 14px;
  margin-top:12px;font-size:13.5px}}
.warn{{background:#fff6e9;border:1px solid #f4dcae;border-radius:10px;padding:10px 14px;
  margin-top:10px;font-size:13px;color:#8a5a12}}
table.forms{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}}
table.forms th{{text-align:left;color:#9db3bf;font-weight:600;font-size:11px;padding:4px 6px;
  border-bottom:1px solid var(--line)}}
table.forms td{{padding:5px 6px;border-bottom:1px solid #f0f5f8}}
table.forms tr.rec td:first-child{{color:var(--teal);font-weight:800}}
table.forms tr.norec td:first-child{{color:#c07a4a;font-weight:800}}
table.forms .why{{color:#7d94a1}}
footer{{color:#9db3bf;font-size:12px;text-align:center;margin-top:26px}}
footer a{{color:var(--blue);text-decoration:none}}
</style></head><body><div class="wrap">
  <h1>Фабрика <span>гипотез</span> · {_esc(profile.fabric)}</h1>
  <div class="sub">детерминированный граф из данных · метрики и логика воспроизводимы · LLM только оформляет текст</div>
  {"".join(f'<div class="warn">⚠ {_esc(w)}</div>' for w in getattr(profile, "warnings", []))}
  <div class="kpi"><b>KPI</b> &nbsp;{_esc(kpi or "снизить потери извлекаемого металла с хвостами")}</div>
  <div class="summary">
    <span><b>{total_ni} т</b><br>извлекаемого Ni в хвостах (факт)</span>
    <span><b>{total_cu} т</b><br>извлекаемого Cu в хвостах (факт)</span>
    <span><b>{len(hyps)}</b><br>гипотез по классам крупности</span>
  </div>
  <div class="tech">оценка безразмерна (без цен): impact — масштаб потери, addressability — излечимость, clarity — ясность механизма · источник: {_esc(profile.source)}</div>
  {techln}
  <div class="panel">
    <h2>Граф знаний</h2>
    <div class="h-sub">извлечён из отчёта детерминированно · ширина ребра ∝ потерям · бирюза = извлекаемая форма</div>
    {graph}
    <div class="legend">
      <span><i style="background:#1f7ae0"></i>элемент → класс (потери)</span>
      <span><i style="background:#12b3ab"></i>класс → извлекаемая форма</span>
      <span><i style="background:#d3dee6"></i>класс → неизвлекаемая форма</span>
    </div>
  </div>
  {_analysis_html(analysis)}
  <h2 style="margin:0 0 10px;font-size:16px">Ранжированные гипотезы (по приоритету: масштаб × излечимость × реализуемость)</h2>
  {cards}
  <footer>Каждая гипотеза заземлена до ячейки отчёта · <a href="glossary.html">как считаются метрики →</a></footer>
</div></body></html>"""
