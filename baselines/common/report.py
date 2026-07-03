# -*- coding: utf-8 -*-
"""Рендер результата пайплайна в самодостаточную HTML-страницу.

Минималистично, сине-бирюзово-белая палитра. Всё инлайн (CSS + данные) — файл
открывается двойным кликом (file://), без сервера и внешних зависимостей.
"""
from __future__ import annotations

import html
import json


def _esc(x):
    return html.escape(str(x if x is not None else ""))


def _bar(label, value):
    pct = max(0.0, min(1.0, float(value or 0))) * 100
    return f"""
        <div class="bar-row">
          <div class="bar-head"><span>{_esc(label)}</span><b>{value}</b></div>
          <div class="bar"><i style="width:{pct:.0f}%"></i></div>
        </div>"""


def _pill(label, value):
    return f'<div class="pill"><b>{_esc(value)}</b><span>{_esc(label)}</span></div>'


def _evidence(facts):
    rows = ""
    for f in facts:
        sign = f.get("sign", 0)
        cls = "p" if sign > 0 else ("n" if sign < 0 else "z")
        mark = "＋" if sign > 0 else ("−" if sign < 0 else "≈")
        rows += f"""
          <div class="ev">
            <span class="chip {cls}">{mark}</span>
            <div class="ev-b">
              <div class="ev-q">«{_esc(str(f.get('quote',''))[:180])}»</div>
              <div class="ev-s">{_esc(f.get('locator',''))}</div>
            </div>
          </div>"""
    return rows


def _card(i, h):
    m = h.get("metrics", {})
    grounded = h.get("grounded")
    badge = ('<span class="badge ok">grounded</span>' if grounded
             else '<span class="badge warn">не заземлена</span>')
    nearest = m.get("nearest")
    near = ""
    if nearest:
        near = (f'<div class="near"><span>ближайшее известное</span> '
                f'<i>{_esc(nearest.get("text",""))}</i> '
                f'<em>{_esc(nearest.get("locator",""))}</em></div>')
    return f"""
    <article class="card">
      <div class="chead">
        <div class="rank">#{i}</div>
        <div class="score">score {m.get('score','—')}</div>
        {badge}
      </div>
      <div class="tri">
        <div class="row"><span class="lab">если</span><p>{_esc(h.get('if'))}</p></div>
        <div class="row"><span class="lab">то</span><p>{_esc(h.get('then'))}</p></div>
        <div class="row"><span class="lab because">потому что</span>
          <p class="muted">{_esc(h.get('because'))}</p></div>
      </div>

      <div class="bars">
        {_bar('relevance — близость к KPI', m.get('relevance', 0))}
        {_bar('novelty — новизна', m.get('novelty', 0))}
      </div>
      <div class="pills">
        {_pill('источников', m.get('support', 0))}
        {_pill('risk', m.get('risk', 0))}
        {_pill('фактов', len(h.get('facts', [])))}
      </div>

      <div class="exp"><span class="lab">эксперимент</span>
        <p>{_esc(h.get('experiment'))}</p></div>

      <div class="evidence">{_evidence(h.get('facts', []))}</div>
      {near}
    </article>"""


def _tech(tech):
    if not tech:
        return ""
    ph = "".join(f'<span class="tchip">{_esc(k)} · {v}s</span>'
                 for k, v in (tech.get("phases") or {}).items())
    cells = [
        (f"{tech.get('total_seconds','—')}s", "время всего"),
        (f"{tech.get('api_seconds','—')}s", "из них API"),
        (tech.get("llm_calls", "—"), "вызовов LLM"),
        (tech.get("embed_calls", "—"), "эмбеддингов"),
        (tech.get("total_tokens", "—"), "токенов LLM"),
        (tech.get("embed_tokens", "—"), "токенов эмбед."),
    ]
    grid = "".join(f'<div><b>{_esc(v)}</b><span>{_esc(l)}</span></div>' for v, l in cells)
    return f"""
    <section class="tech">
      <div class="tech-grid">{grid}</div>
      <div class="tech-foot">
        вход {_esc(tech.get('input_tokens','—'))} + выход {_esc(tech.get('completion_tokens','—'))} токенов
        · модель {_esc(tech.get('model',''))}
      </div>
      <div class="phases">{ph}</div>
    </section>"""


def render(export, kpi, materials="", stats=None, tech=None):
    cards = "\n".join(_card(i, h) for i, h in enumerate(export, 1))
    stat_line = ""
    if stats:
        grounded = sum(1 for h in export if h.get("grounded"))
        stat_line = (f'<div class="stats">'
                     f'<span><b>{stats.get("kept","?")}</b> связей в графе</span>'
                     f'<span><b>{stats.get("dropped","?")}</b> отсеяно цитатным гейтом</span>'
                     f'<span><b>{grounded}/{len(export)}</b> заземлено</span></div>')
    payload = html.escape(json.dumps(export, ensure_ascii=False))
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Фабрика гипотез</title>
<style>
:root{{
  --bg:#eef6fb; --card:#fff; --ink:#12303f; --muted:#5f7d8c;
  --blue:#1f7ae0; --teal:#12b3ab; --teal-soft:#e6f7f5; --line:#e6eef3;
  --radius:16px;
}}
*{{box-sizing:border-box}}
html,body{{margin:0}}
body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  background:linear-gradient(180deg,#e7f3fa 0%,#eef6fb 100%);color:var(--ink);
  line-height:1.55;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:820px;margin:0 auto;padding:40px 22px 72px}}
header h1{{margin:0;font-size:28px;font-weight:800;letter-spacing:-.4px}}
header h1 span{{color:var(--teal)}}
header .sub{{color:var(--muted);font-size:13.5px;margin-top:4px}}
.kpi{{background:var(--teal-soft);border:1px solid #cdeeea;border-radius:var(--radius);
  padding:14px 18px;margin:22px 0 10px;font-size:15px}}
.kpi b{{color:var(--blue);font-weight:700}}
.src-line{{color:var(--muted);font-size:12.5px;margin:0 2px 14px}}
.stats{{display:flex;flex-wrap:wrap;gap:18px;margin:0 2px 20px;font-size:12.5px;color:var(--muted)}}
.stats b{{color:var(--ink)}}

/* ── технический блок ── */
.tech{{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  padding:18px 20px;margin:0 0 26px;box-shadow:0 1px 8px rgba(31,122,224,.05)}}
.tech-grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:14px}}
.tech-grid div{{display:flex;flex-direction:column;align-items:center;text-align:center;gap:2px}}
.tech-grid b{{font-size:20px;font-weight:800;color:var(--blue);line-height:1.1}}
.tech-grid span{{font-size:10.5px;color:var(--muted)}}
.tech-foot{{text-align:center;color:var(--muted);font-size:12px;margin-top:14px;
  padding-top:12px;border-top:1px solid var(--line)}}
.phases{{display:flex;flex-wrap:wrap;gap:7px;justify-content:center;margin-top:10px}}
.tchip{{background:var(--teal-soft);color:#0a7f79;font-size:11px;padding:4px 10px;border-radius:20px}}

/* ── карточка гипотезы ── */
.card{{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  padding:22px 24px;margin:0 0 18px;box-shadow:0 2px 12px rgba(31,122,224,.06)}}
.chead{{display:flex;align-items:center;gap:12px;margin-bottom:14px}}
.rank{{font-size:17px;font-weight:800;color:#fff;background:linear-gradient(135deg,var(--blue),var(--teal));
  width:40px;height:40px;border-radius:11px;display:flex;align-items:center;justify-content:center}}
.score{{font-size:13px;font-weight:700;color:var(--blue);background:#eaf3fd;
  padding:5px 12px;border-radius:20px}}
.badge{{margin-left:auto;font-size:11px;font-weight:700;padding:5px 12px;border-radius:20px}}
.badge.ok{{background:#e3f7ee;color:#0a8f54}}
.badge.warn{{background:#fdeee9;color:#c0532a}}

.tri{{margin:2px 0 18px}}
.tri .row{{display:flex;gap:12px;align-items:baseline;margin:7px 0}}
.lab{{flex:0 0 92px;text-align:right;font-size:10.5px;font-weight:700;letter-spacing:.6px;
  text-transform:uppercase;color:var(--teal);padding-top:2px}}
.lab.because{{color:#9db3bf}}
.tri p{{margin:0;font-size:15.5px;overflow-wrap:anywhere}}
.tri .muted{{color:var(--muted);font-size:14px}}

.bars{{display:grid;grid-template-columns:1fr 1fr;gap:12px 24px;margin:16px 0 14px}}
.bar-head{{display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted)}}
.bar-head b{{color:var(--ink)}}
.bar{{height:8px;background:#eaf1f5;border-radius:6px;margin-top:5px;overflow:hidden}}
.bar i{{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--teal));
  border-radius:6px}}
.pills{{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap}}
.pill{{background:#f5fafd;border:1px solid var(--line);border-radius:11px;padding:7px 14px;
  display:flex;flex-direction:column;align-items:center;min-width:74px}}
.pill b{{font-size:15px;font-weight:800;color:var(--ink)}}
.pill span{{font-size:10.5px;color:var(--muted)}}

.exp{{display:flex;gap:12px;align-items:baseline;background:#f6fbfd;border:1px solid var(--line);
  border-radius:12px;padding:11px 14px;margin-bottom:14px}}
.exp .lab{{flex:0 0 92px}}
.exp p{{margin:0;font-size:13.5px;overflow-wrap:anywhere}}

.evidence{{display:flex;flex-direction:column;gap:9px}}
.ev{{display:flex;gap:11px;align-items:flex-start}}
.chip{{flex:0 0 22px;height:22px;border-radius:7px;display:flex;align-items:center;
  justify-content:center;font-weight:800;font-size:12px;color:#fff;margin-top:1px}}
.chip.p{{background:var(--teal)}} .chip.n{{background:#e0895a}} .chip.z{{background:#9db3bf}}
.ev-b{{flex:1;min-width:0}}
.ev-q{{font-size:13px;color:#37505c;overflow-wrap:anywhere}}
.ev-s{{font-size:11px;color:#9db3bf;margin-top:1px}}
.near{{margin-top:14px;padding-top:12px;border-top:1px solid var(--line);font-size:12.5px}}
.near span{{color:#9db3bf;text-transform:uppercase;font-size:10px;letter-spacing:.5px;margin-right:6px}}
.near i{{color:#37505c}} .near em{{color:#9db3bf;font-style:normal}}

footer{{color:#9db3bf;font-size:12px;text-align:center;margin-top:30px;line-height:1.6}}

@media(max-width:600px){{
  .wrap{{padding:26px 15px 48px}}
  .tech-grid{{grid-template-columns:repeat(3,1fr);gap:16px 10px}}
  .bars{{grid-template-columns:1fr}}
  .lab,.exp .lab{{flex-basis:70px}}
}}
</style></head>
<body><div class="wrap">
  <header>
    <h1>Фабрика <span>гипотез</span></h1>
    <div class="sub">автоматический grounded-пайплайн · метрики считаются детерминированно</div>
  </header>
  <div class="kpi"><b>KPI</b> &nbsp;{_esc(kpi)}</div>
  <div class="src-line">материалы: {_esc(materials)}</div>
  {stat_line}
  {_tech(tech)}
  {cards}
  <footer>Каждая гипотеза заземлена цитатой до источника<br>
    новизна = расстояние до ближайшего известного решения</footer>
</div>
<script id="data" type="application/json">{payload}</script>
</body></html>"""
