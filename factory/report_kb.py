# -*- coding: utf-8 -*-
"""HTML-отчёт ветки Б (литература → граф → открытия). Самодостаточный, без LLM.

Раньше результаты ветки Б жили только в консоли flex.py — а это единственная ветка
для кейсов БЕЗ структурных данных (металлургия/шлаки: «схема + описание + промпт»),
т.е. у половины сценариев не было визуального артефакта вообще. Здесь рендерится
тот же стиль, что у отчёта ветки А (report.py): SVG-граф + карточки, каждая карточка
заземлена дословными цитатами с локатором до страницы.

Честность формулировок сохраняется из discover.py: промышленное действие (is_action) —
«внедрить», абстрактный факт — «исследовать применимость»; разрыв Свонсона отличается
от прямой связи бейджем. Ничего не переоценивается — рендерится то, что насчитало
детерминированное ядро поверх кэша извлечения.
"""
from __future__ import annotations

import html
import math


def _esc(x):
    return html.escape(str(x if x is not None else ""))


# ─────────────────────────── граф связей (SVG, круговая раскладка) ───────────────────────────

_SIGN_COLOR = {1: "#12b3ab", -1: "#e0762f", 0: "#b9c8d2"}
_SIGN_LABEL = {1: "повышает", -1: "снижает", 0: "связан / не влияет"}


def _graph_svg(layered, max_label=22):
    """Круговая раскладка топ-узлов по связности; ребро окрашено знаком влияния.
    Полное имя узла — в <title> (тултип браузера), подпись обрезается."""
    nodes = sorted(layered["nodes"], key=lambda n: -n["deg"])
    if not nodes:
        return '<p class="muted">граф пуст — извлечённых связей нет</p>'
    W, H = 900, 520
    cx, cy, rx, ry = W / 2, H / 2 + 8, W / 2 - 120, H / 2 - 52

    pos = {}
    n = len(nodes)
    for i, nd in enumerate(nodes):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        pos[nd["id"]] = (cx + rx * math.cos(ang), cy + ry * math.sin(ang), nd)

    # рёбра: дубликаты (мультиграф) схлопываем по (src,dst,sign) для читаемости
    seen, edges_svg = set(), ""
    for e in layered["edges"]:
        key = (e["src"], e["dst"], e["sign"])
        if key in seen or e["src"] not in pos or e["dst"] not in pos:
            continue
        seen.add(key)
        x1, y1, _ = pos[e["src"]]
        x2, y2, _ = pos[e["dst"]]
        qx, qy = (x1 + x2) / 2 * 0.45 + cx * 0.55, (y1 + y2) / 2 * 0.45 + cy * 0.55
        color = _SIGN_COLOR.get(e["sign"], _SIGN_COLOR[0])
        edges_svg += (f'<path d="M{x1:.0f},{y1:.0f} Q{qx:.0f},{qy:.0f} {x2:.0f},{y2:.0f}" '
                      f'fill="none" stroke="{color}" stroke-width="1.6" opacity="0.55" '
                      f'marker-end="url(#ar{e["sign"]})"/>')

    max_deg = max(nd["deg"] for nd in nodes) or 1
    nodes_svg = ""
    for nid, (x, y, nd) in pos.items():
        label = nd["label"]
        short = label if len(label) <= max_label else label[:max_label - 1] + "…"
        w = min(170, 16 + len(short) * 6.4)
        hub = nd["deg"] >= max_deg * 0.6 and nd["deg"] >= 3   # узлы-концентраторы — темнее
        fill, stroke = ("#dcebfb", "#8fc1f0") if hub else ("#eaf3fd", "#bcdcfa")
        nodes_svg += (
            f'<g><title>{_esc(label)} · связей: {nd["deg"]}</title>'
            f'<rect x="{x - w/2:.0f}" y="{y - 12:.0f}" width="{w:.0f}" height="24" rx="12" '
            f'fill="{fill}" stroke="{stroke}"/>'
            f'<text x="{x:.0f}" y="{y + 3.5:.0f}" text-anchor="middle" font-size="10" '
            f'fill="#12303f">{_esc(short)}</text></g>')

    defs = "".join(
        f'<marker id="ar{s}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" '
        f'markerHeight="6" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="{c}"/></marker>'
        for s, c in _SIGN_COLOR.items())
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" '
            f'xmlns="http://www.w3.org/2000/svg"><defs>{defs}</defs>'
            f'{edges_svg}{nodes_svg}</svg>')


# ─────────────────────────── карточки открытий ───────────────────────────

def _quotes_html(chain):
    """Дословные цитаты цепочки с локатором до страницы — заземление карточки."""
    seen, out = set(), ""
    for e in chain or []:
        q = (e.get("quote") or "").strip()
        if not q or q in seen:
            continue
        seen.add(q)
        loc = e.get("locator") or e.get("source") or ""
        out += (f'<blockquote class="q">«{_esc(q)}»'
                + (f'<span class="loc">{_esc(loc)}</span>' if loc else "")
                + "</blockquote>")
    return out or '<p class="muted">структурный вывод графа — прямой цитаты у ребра нет</p>'


def _card(i, d):
    kind_gap = bool(d.b)                          # b заполнен только у разрыва Свонсона
    badges = ""
    if d.is_action:
        badges += '<span class="tag act">промышленное действие → внедрить</span>'
    else:
        badges += '<span class="tag res">абстрактный факт → исследовать</span>'
    badges += ('<span class="tag gap">разрыв Свонсона</span>' if kind_gap
               else '<span class="tag dir">прямая связь из источника</span>')
    if d.role == "state":
        badges += '<span class="tag st">состояние фабрики</span>'
    src = "".join(f"<li>{_esc(s)}</li>" for s in d.sources if s)
    return f"""
    <article class="card">
      <div class="chead">
        <div class="rank">#{i}</div>
        <div class="money">{d.score}<span>score (novelty · релевантность KPI · action)</span></div>
        <div class="tags">{badges}</div>
      </div>
      <div class="tri">
        <div class="row"><span class="lab">если</span><p>{_esc(d.statement_if)}</p></div>
        <div class="row"><span class="lab">то</span><p>{_esc(d.statement_then)}</p></div>
        <div class="row"><span class="lab because">потому что</span>
          <p class="muted">{_esc(d.statement_because)}</p></div>
      </div>
      <div class="pills">
        <div class="pill"><b>{d.novelty}</b><span>новизна (редкость в корпусе)</span></div>
        <div class="pill"><b>{d.relevance}</b><span>релевантность KPI</span></div>
        <div class="pill"><b>{_SIGN_LABEL.get(d.sign, "—")}</b><span>знак влияния</span></div>
      </div>
      <div class="quotes"><b>Заземление (дословные цитаты):</b>{_quotes_html(d.chain)}</div>
      <div class="src"><b>Источники:</b><ul>{src}</ul></div>
    </article>"""


# ─────────────────────────── страница ───────────────────────────

def render_kb(layered, discoveries, kpi="", tech=None):
    """Граф (сериализация RelationGraph.to_layered) + открытия → HTML-страница."""
    tech = tech or {}
    cards = "\n".join(_card(i, d) for i, d in enumerate(discoveries, 1)) or \
        ('<div class="warn">Гипотез из литературы не найдено: граф слишком мал или '
         'KPI лексически не пересёкся с корпусом. Добавьте материалов или уточните KPI.</div>')
    techln = " · ".join(f"{k}: {v}" for k, v in tech.items() if v not in (None, ""))
    n_act = sum(1 for d in discoveries if d.is_action)
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Фабрика гипотез · литература</title>
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
.tech{{font-size:12px;color:#9db3bf;margin:2px 2px 16px;overflow-wrap:anywhere}}
.panel{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px 18px;margin:0 0 22px;
  box-shadow:0 2px 12px rgba(31,122,224,.06);overflow-x:auto}}
.panel h2{{margin:0 0 4px;font-size:15px}} .panel .h-sub{{color:var(--muted);font-size:12px;margin-bottom:8px}}
.legend{{display:flex;gap:16px;font-size:11.5px;color:var(--muted);margin-top:6px;flex-wrap:wrap}}
.legend i{{display:inline-block;width:22px;height:4px;border-radius:2px;vertical-align:middle;margin-right:5px}}
.card{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px 22px;margin:0 0 16px;
  box-shadow:0 2px 12px rgba(31,122,224,.06)}}
.chead{{display:flex;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap}}
.rank{{font-size:16px;font-weight:800;color:#fff;background:linear-gradient(135deg,var(--blue),var(--teal));
  width:38px;height:38px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex:0 0 38px}}
.money{{font-size:19px;font-weight:800;color:var(--blue);display:flex;flex-direction:column;line-height:1}}
.money span{{font-size:10px;font-weight:600;color:var(--muted)}}
.tags{{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}}
.tag{{font-size:10.5px;font-weight:700;padding:4px 10px;border-radius:20px}}
.tag.act{{color:#0a7f79;background:var(--teal-soft)}}
.tag.res{{color:#8a5a12;background:#fff6e9}}
.tag.gap{{color:#5b3fa8;background:#f1ecfc}}
.tag.dir{{color:#1f7ae0;background:#eaf3fd}}
.tag.st{{color:#a83f66;background:#fdeef4}}
.tri .row{{display:flex;gap:12px;align-items:baseline;margin:6px 0}}
.lab{{flex:0 0 92px;text-align:right;font-size:10.5px;font-weight:700;letter-spacing:.5px;
  text-transform:uppercase;color:var(--teal)}} .lab.because{{color:#9db3bf}}
.tri p{{margin:0;font-size:15px;overflow-wrap:anywhere}} .tri .muted{{color:var(--muted);font-size:13.5px}}
.pills{{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 4px}}
.pill{{background:#f5fafd;border:1px solid var(--line);border-radius:11px;padding:7px 13px;
  display:flex;flex-direction:column;align-items:center;min-width:82px}}
.pill b{{font-size:14px;font-weight:800}} .pill span{{font-size:10px;color:var(--muted)}}
.quotes{{font-size:12px;margin:10px 0}} .quotes>b{{font-size:11px;text-transform:uppercase;color:#9db3bf}}
.q{{margin:6px 0 4px;padding:6px 10px;border-left:3px solid var(--teal);background:#f2fbfa;
  color:#2a4550;font-size:12.5px;overflow-wrap:anywhere}}
.q .loc{{display:block;margin-top:3px;color:#9db3bf;font-size:11px;font-style:normal}}
.src{{font-size:12px;margin:10px 0 0}} .src b{{font-size:11px;text-transform:uppercase;color:#9db3bf}}
.src ul{{margin:5px 0 0;padding-left:18px;color:#37505c}} .src li{{margin:2px 0}}
.muted{{color:var(--muted)}}
.warn{{background:#fff6e9;border:1px solid #f4dcae;border-radius:10px;padding:10px 14px;
  margin-top:10px;font-size:13px;color:#8a5a12}}
footer{{color:#9db3bf;font-size:12px;text-align:center;margin-top:26px}}
</style></head><body><div class="wrap">
  <h1>Фабрика <span>гипотез</span> · литература</h1>
  <div class="sub">ветка Б: LLM извлекает связи с дословной цитатой (цитатный гейт) ·
    граф, разрывы и ранжирование — детерминированно поверх кэша</div>
  <div class="kpi"><b>KPI</b> &nbsp;{_esc(kpi)}</div>
  <div class="summary">
    <span><b>{len(discoveries)}</b><br>гипотез из литературы</span>
    <span><b>{n_act}</b><br>промышленных действий (внедрить)</span>
    <span><b>{len(discoveries) - n_act}</b><br>направлений исследовать</span>
  </div>
  <div class="tech">{_esc(techln)}</div>
  <div class="panel">
    <h2>Граф знаний из литературы</h2>
    <div class="h-sub">узлы — сущности (наведите для полного имени) · стрелка — направление
      влияния · тёмные узлы — концентраторы</div>
    {_graph_svg(layered)}
    <div class="legend">
      <span><i style="background:{_SIGN_COLOR[1]}"></i>повышает</span>
      <span><i style="background:{_SIGN_COLOR[-1]}"></i>снижает</span>
      <span><i style="background:{_SIGN_COLOR[0]}"></i>связан / не влияет</span>
    </div>
  </div>
  <h2 style="margin:0 0 10px;font-size:16px">Гипотезы из литературы
    (ранжированы: релевантность KPI → score)</h2>
  {cards}
  <footer>Каждая гипотеза заземлена дословной цитатой источника (цитатный гейт) ·
    LLM не участвует в ранжировании</footer>
</div></body></html>"""
