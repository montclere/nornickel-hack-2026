# -*- coding: utf-8 -*-
"""HTML-отчёт: граф знаний (послойный SVG) + карточки гипотез. Самодостаточный."""
from __future__ import annotations

import html
import os

from factory.client import TELEMETRY
from factory.config import OUTPUTS_DIR
from factory.reader import ELEMENT_SYMBOLS, PRIMARY_ELEMENT


def _rel(path):
    """Путь к исходнику относительно папки отчёта — для кликабельной ссылки (file://)."""
    try:
        return os.path.relpath(path, OUTPUTS_DIR)
    except (ValueError, TypeError):
        return path or ""


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
        tip = f'{_esc(sd["label"])} — {_esc(dd["label"])}: {e["tonnes"]} т'
        edges_svg += (f'<path class="gedge" data-a="{_esc(e["src"])}" data-b="{_esc(e["dst"])}" '
                      f'data-tip="{tip}" d="M{x1r:.0f},{y1:.0f} C{mx:.0f},{y1:.0f} '
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
        ntip = f'{kind}: {_esc(nd["label"])}'
        nodes_svg += (
            f'<g class="gnode" data-id="{_esc(nid)}" data-tip="{ntip}">'
            f'<rect x="{x-w/2:.0f}" y="{y-15:.0f}" '
            f'width="{w}" height="30" rx="8" fill="{fill}" stroke="{stroke}"/>'
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
def _evidence_html(evidence):
    """Заземление до ячейки с КЛИКАБЕЛЬНОЙ ссылкой на файл-источник (открыть в новой вкладке)."""
    rows = []
    for e in evidence:
        loc = _esc((e.get("source", "") + " · ") if e.get("source") else "") + _esc(e.get("cell", ""))
        if e.get("path"):
            loc = f'<a href="{_esc(_rel(e["path"]))}" target="_blank" rel="noopener">{loc}</a>'
        rows.append(f'<div class="ev"><span>{_esc(e["label"])}</span><em>{loc}</em></div>')
    return "".join(rows)


def _card(h, runinfo=None):
    runinfo = runinfo or {}
    m = h.metrics
    impact_pct = round(m["impact"] * 100)
    alts = "".join(f"<li>{_esc(a)}</li>" for a in h.alternatives)
    ev = _evidence_html(h.evidence)
    src = "".join(f"<li>{_esc(s)}</li>" for s in h.sources)
    warn = ""
    if h.violates_constraints:
        warn = (f'<div class="warn">нарушает ограничение из запроса: '
               f'{_esc(", ".join(h.violates_constraints))} — приоритет намеренно занижен, '
               f'но гипотеза не скрыта</div>')
    fb = getattr(h, "expert_feedback", None)
    if fb:
        note = f' — «{_esc(fb["note"])}»' if fb.get("note") else ""
        novel = (" Совпадает с базой испробованных направлений → не ново."
                 if fb.get("not_novel") else "")
        warn += (f'<div class="fb">фидбэк эксперта: '
                 f'<b>{_esc(fb.get("verdict", "").replace("_", " "))}</b>{note} · '
                 f'приоритет ×{fb.get("multiplier", 1)} '
                 f'({"точное совпадение" if fb.get("tier") == "exact" else "по семейству"}).'
                 f'{novel} Переранжирована, не скрыта.</div>')
    # плитки металла — по КЛЮЧАМ rec_tonnes (из схемы), а не по зашитым Ni/Cu
    metal_pills = "".join(f'<div class="pill"><b>{v}</b><span>т {_esc(sym)} извлек.</span></div>'
                          for sym, v in (h.metrics.get("rec_tonnes") or {}).items())
    wp = _world_practice_html(h.world_practice, runinfo.get("web"))
    return f"""
    <article class="card">
      <div class="chead">
        <div class="rank">#{h.rank}</div>
        <div class="money">{impact_pct}%<span>извлекаемых потерь {_esc(h.target_element)} по фабрике</span></div>
        <div class="fam">{_esc(h.family)}</div>
      </div>
      <div class="tri">
        <div class="row"><span class="lab">если</span><p>{_esc(h.statement_if)}</p></div>
        <div class="row"><span class="lab">то</span><p>{_esc(h.statement_then)}</p></div>
        <div class="row"><span class="lab because">потому что</span>
          <p class="muted">{_esc(h.statement_because)}</p></div>
      </div>
      {warn}
      <div class="bars">
        <div class="bar-row"><div class="bar-head"><span>масштаб потери</span><b>{impact_pct}%</b></div>
          <div class="bar"><i style="width:{min(m['impact']*100,100):.0f}%"></i></div></div>
        <div class="bar-row"><div class="bar-head"><span>излечимость</span><b>{m['addressability']}</b></div>
          <div class="bar"><i style="width:{m['addressability']*100:.0f}%"></i></div></div>
        <div class="pills">
          {metal_pills}
          <div class="pill"><b>{m['clarity']}</b><span>ясность механизма</span></div>
          <div class="pill"><b>{m['feasibility']}</b><span>реализуемость</span></div>
        </div>
      </div>
      <div class="alts"><b>Альтернативы:</b><ul>{alts}</ul></div>
      <div class="exp"><b>Эксперимент</b>
        <div class="exprow"><span>тест</span><p>{_esc(h.exp_test)}</p></div>
        <div class="exprow"><span>метрика</span><p>{_esc(h.exp_metric)}</p></div>
        <div class="exprow"><span>критерий</span><p>{_esc(h.exp_criterion)}</p></div>
      </div>
      {_roadmap_html(getattr(h, "roadmap", None))}
      <div class="evidence"><b>Заземление (ячейки отчёта)</b>{ev}</div>
      <div class="src"><b>Основание метода</b><ul>{src}</ul></div>
      {_literature_html(getattr(h, "literature", None))}
      <div class="wp"><b>Мировая практика:</b>{wp}</div>
      {_dossier_html(getattr(h, "dossier", None), runinfo.get("dossier"))}
    </article>"""


def _dossier_html(dossier, searched=None):
    """Досье OpenAlex: реальные источники с цитируемостью («важность») + фраза из
    abstract («причина») + ссылка. Детерминированно, без LLM."""
    if not dossier:
        msg = ('работ не найдено'
               if searched else
               'поиск не запускался (<code>--dossier</code>)')
        return f'<div class="dos"><b>Научные источники:</b><p class="muted">{msg}</p></div>'
    items = "".join(
        f'<div class="dosrc"><div class="doshead">'
        f'<span class="cit">{e.get("cited_by", 0)} цит.</span>'
        f'<a href="{_esc(e.get("url",""))}" target="_blank" rel="noopener">'
        f'{_esc((e.get("title") or "источник")[:110])}</a>'
        f'<span class="yr">{e.get("year") or ""}</span></div>'
        f'<div class="dosq">«{_esc(e.get("quote",""))}»</div></div>'
        for e in dossier)
    return (f'<div class="dos"><b>Научные источники ({len(dossier)})</b>'
            f'{items}</div>')


def _literature_html(lit):
    """Подтверждение из ВЫДАННОГО корпуса: дословные цитаты с локатором до страницы
    (подбирает litsupport.py детерминированно по кэшу извлечения). Нет цитат — блока нет."""
    if not lit:
        return ""
    qs = "".join(
        f'<blockquote class="litq">«{_esc(e["quote"])}»'
        f'<span class="litloc">{_esc(e.get("locator") or e.get("source") or "")}</span>'
        f'</blockquote>' for e in lit)
    return f'<div class="lit"><b>Из базы знаний</b>{qs}</div>'


def _roadmap_html(rm):
    """Дорожная карта эксперимента: этапы лаборатория→пилот→внедрение с критериями
    перехода (го/стоп). Строится детерминированным шаблоном в roadmap.py."""
    if not rm:
        return ""
    steps = "".join(
        f'<li><b>{_esc(s["name"])}.</b> {_esc(s["actions"])}'
        f'<span class="crit">критерий перехода: {_esc(s["success"])}</span></li>'
        for s in rm)
    return (f'<div class="rm"><b>Дорожная карта эксперимента:</b>'
            f'<ol>{steps}</ol></div>')


def _world_practice_html(wp, searched=None):
    """world_practice: dict {practice,quote,url,site} от веб-поиска, либо None.
    Показываем резюме + ДОСЛОВНУЮ цитату + кликабельный источник (заземление)."""
    if not wp:
        msg = ('подтверждение в вебе не найдено'
               if searched else
               'поиск не запускался (<code>--web</code>)')
        return f'<p class="muted">{msg}</p>'
    if isinstance(wp, str):        # обратная совместимость
        return f'<p class="muted">{_esc(wp)}</p>'
    url, site = _esc(wp.get("url", "")), _esc(wp.get("site", "источник"))
    practice, quote = (wp.get("practice") or "").strip(), (wp.get("quote") or "").strip()
    # в детерминированном режиме practice == quote (цитата и есть практика) — не дублируем;
    # отдельное резюме показываем, только если оно РЕАЛЬНО другое (было у LLM-версии)
    summary = f'<p>{_esc(practice)}</p>' if practice and practice != quote else ""
    return (f'{summary}<blockquote class="wpq">«{_esc(quote)}»</blockquote>'
            f'<div class="wpsrc">источник: <a href="{url}" target="_blank" '
            f'rel="noopener">{site}</a></div>')


def _liberation_svg(lib):
    if not lib:
        return ""
    W, H, pad = 620, 210, 34
    n = len(lib)
    xs = [pad + (W - 2 * pad) * i / max(n - 1, 1) for i in range(n)]
    def y(p):
        return H - pad - (H - 2 * pad) * p / 100
    def poly(key, color, name):
        pts = " ".join(f"{xs[i]:.0f},{y(r[key]):.0f}" for i, r in enumerate(lib))
        dots = "".join(
            f'<circle class="gdot" cx="{xs[i]:.0f}" cy="{y(r[key]):.0f}" r="4" fill="{color}" '
            f'data-tip="{_esc(r["class"])} · {name}: {r[key]}%'
            + (f' · {r["rec_tonnes"]} т извлекаемо' if key == "recoverable_pct" and r.get("rec_tonnes") is not None else '')
            + '"/>' for i, r in enumerate(lib))
        return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>{dots}'
    grid = "".join(f'<line x1="{pad}" y1="{y(v):.0f}" x2="{W-pad}" y2="{y(v):.0f}" '
                   f'stroke="#eef4f7"/><text x="{pad-6}" y="{y(v)+4:.0f}" text-anchor="end" '
                   f'font-size="9" fill="#9db3bf">{v}%</text>' for v in (0, 25, 50, 75, 100))
    labels = "".join(f'<text x="{xs[i]:.0f}" y="{H-10}" text-anchor="middle" font-size="10" '
                     f'fill="#5f7d8c">{_esc(r["class"])}</text>' for i, r in enumerate(lib))
    return (f'<svg viewBox="0 0 {W} {H}" width="100%">{grid}'
            f'{poly("locked_pct","#1f7ae0","закрытый")}'
            f'{poly("recoverable_pct","#12b3ab","извлекаемо")}{labels}</svg>')


def panels_html(layered, analysis):
    """Готовые визуальные панели (граф знаний + кривая раскрытия + форм-таблица) — те же
    SVG/таблицы, что в HTML-отчёте ядра, для ВСТРАИВАНИЯ в веб-страницу (webapp).
    Разметка использует классы .panel/.legend/.forms/.h-sub/.anote (см. app.css)."""
    graph = _graph_svg(layered) if layered else ""
    legend = ('<div class="legend">'
              '<span><i style="background:#1f7ae0"></i>элемент → класс (потери)</span>'
              '<span><i style="background:#12b3ab"></i>класс → извлекаемая форма</span>'
              '<span><i style="background:#d3dee6"></i>класс → неизвлекаемая форма</span></div>')
    graph_panel = f'<div class="panel"><h2>Граф знаний</h2>{graph}{legend}</div>' if graph else ""
    return graph_panel + _analysis_html(analysis)


def _analysis_html(a):
    if not a:
        return ""
    grind = a.get("optimal_grind")
    grind_html = (f'<div class="cnote"><b>Обрыв раскрытия</b> до класса {_esc(grind)}: '
                  f'закрытого Pnt больше раскрытого — измельчать мельче этой границы.</div>'
                  if grind else "")
    tos = "".join(f'<div class="cnote">{_esc(t)}</div>' for t in a.get("tradeoffs", []))
    forms = "".join(
        f'<tr class="{"rec" if r["recoverable"] else "norec"}"><td>{"✓" if r["recoverable"] else "✗"}</td>'
        f'<td>{_esc(r["form"])}</td><td>{r["tonnes"]} т</td><td>{r["share_pct"]}%</td>'
        f'<td>{_esc(r["status"])}</td><td class="why">{_esc(r["why"])}</td></tr>'
        for r in a.get("forms", []))
    el = a.get("element") or PRIMARY_ELEMENT
    return f"""
  <div class="panel">
    <h2>Кривая раскрытия по крупности ({_esc(el)})</h2>
    <div class="h-sub">как меняется форма {_esc(el)} с размером частиц</div>
    {_liberation_svg(a.get("liberation", []))}
    <div class="legend">
      <span><i style="background:#1f7ae0"></i>закрытый Pnt (заперт в сростках)</span>
      <span><i style="background:#12b3ab"></i>извлекаемо всего</span>
    </div>
    {grind_html}{tos}
  </div>
  <div class="panel">
    <h2>Куда физически уходит {_esc(el)} (по формам)</h2>
    <div class="h-sub">не всё извлекаемо: часть {_esc(el)} в силикатах/пирротине — потолок реального извлечения</div>
    <table class="forms"><thead><tr><th></th><th>форма</th><th>т {_esc(el)}</th><th>доля</th>
      <th>статус</th><th>почему</th></tr></thead><tbody>{forms}</tbody></table>
  </div>"""


def render_literature(discoveries, kpi=""):
    """Отдельный HTML для гипотез ВЕТКИ Б (из литературы): связи/разрывы Свонсона с
    ДОСЛОВНЫМИ цитатами и локаторами источника (файл:страница) — то самое «эффектное»
    заземление до места в документе."""
    cards = []
    for i, d in enumerate(discoveries, 1):
        quotes = []
        for e in getattr(d, "chain", []) or []:
            q = (e.get("quote") or "").strip()
            loc = e.get("locator") or e.get("source") or ""
            if q:
                quotes.append(f'<div class="litq">«{_esc(q[:280])}»'
                              f'<span class="litloc">{_esc(loc)}</span></div>')
        tag = ("действие" if getattr(d, "is_action", False) else "к исследованию")
        role = "состояние фабрики" if getattr(d, "role", "") == "state" else "справочное"
        cards.append(f"""
    <article class="card">
      <div class="chead"><div class="rank">#{i}</div>
        <div class="money">novelty {getattr(d,"novelty",0)}<span>редкость в корпусе</span></div>
        <div class="fam">{_esc(tag)} · {_esc(role)}</div></div>
      <div class="tri">
        <div class="row"><span class="lab">если</span><p>{_esc(d.statement_if)}</p></div>
        <div class="row"><span class="lab">то</span><p>{_esc(d.statement_then)}</p></div>
        <div class="row"><span class="lab because">потому что</span>
          <p class="muted">{_esc(d.statement_because)}</p></div>
      </div>
      <div class="litqs"><b>Цитаты-источники</b>{''.join(quotes) or '<p class="muted">—</p>'}</div>
    </article>""")
    body = "\n".join(cards) or '<p class="muted">гипотез из литературы не найдено</p>'
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Гипотезы из литературы</title>
<style>
body{{margin:0;font-family:'Ubuntu',-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#12303f;
  background:linear-gradient(180deg,#e7f3fa,#eef6fb);line-height:1.5}}
.wrap{{max-width:860px;margin:0 auto;padding:34px 20px 60px}}
h1{{font-size:24px;font-weight:800;margin:0 0 4px}} h1 span{{color:#12b3ab}}
.srcbar{{font-size:12.5px;color:#5f7d8c;margin:2px 0 16px}}
.card{{background:#fff;border:1px solid #e6eef3;border-radius:16px;padding:18px 20px;margin:0 0 14px;
  box-shadow:0 2px 12px rgba(31,122,224,.06);transition:box-shadow .18s,transform .18s}}
.card:hover{{box-shadow:0 8px 26px rgba(31,122,224,.13);transform:translateY(-2px)}}
.chead{{display:flex;align-items:center;gap:12px;margin-bottom:10px}}
.rank{{font-size:15px;font-weight:800;color:#fff;background:linear-gradient(135deg,#1f7ae0,#12b3ab);
  width:34px;height:34px;border-radius:9px;display:flex;align-items:center;justify-content:center}}
.money{{font-size:15px;font-weight:800;color:#1f7ae0;display:flex;flex-direction:column;line-height:1}}
.money span{{font-size:10px;font-weight:600;color:#9db3bf}}
.fam{{margin-left:auto;font-size:11px;font-weight:700;color:#0a7f79;background:#e6f7f5;padding:5px 12px;border-radius:20px}}
.tri .row{{display:flex;gap:12px;align-items:baseline;margin:5px 0}}
.lab{{flex:0 0 84px;text-align:right;font-size:10px;font-weight:700;text-transform:uppercase;color:#9db3bf}}
.tri p{{margin:0;font-size:14.5px;overflow-wrap:anywhere}} .muted{{color:#5f7d8c}}
.litqs{{margin-top:10px}} .litqs>b{{font-size:11px;text-transform:uppercase;color:#9db3bf}}
.litq{{margin:6px 0 0;padding:7px 11px;border-left:3px solid #12b3ab;background:#f2fbfa;
  font-size:12.5px;color:#2a4550;overflow-wrap:anywhere}}
.litloc{{display:block;margin-top:3px;font-size:11px;color:#1f7ae0;font-weight:600}}
a{{color:#1f7ae0}}
</style></head><body><div class="wrap">
  <h1>Гипотезы из <span>литературы</span></h1>
  <div class="srcbar">ветка Б · извлечено из текста с цитатным гейтом · KPI: {_esc(kpi)}</div>
  {body}
  <div style="text-align:center;margin-top:22px"><a href="glossary.html">как читать →</a></div>
</div></body></html>"""


def _run_badges(hyps, tech, runinfo=None) -> str:
    """Чем ПОЛЬЗОВАЛИСЬ в прогоне (что реально запускалось, по флагам, а не «нашлось»)."""
    runinfo = runinfo or {}
    used = ["ядро (детерминированно)"]
    if runinfo.get("dossier"):
        used.append("досье OpenAlex")
    if runinfo.get("web"):
        used.append("веб-практики")
    if tech and tech.get("llm", "нет") not in ("нет", None):
        used.append("LLM-полировка")
    return "".join(f'<span class="badge">{_esc(b)}</span>' for b in used)


def _metrics_footer() -> str:
    """Все замеренные метрики прогона (вызовы/задержки/токены) — внизу отчёта."""
    snap = TELEMETRY.snapshot()
    if not snap["total"]["calls"]:
        return ""
    rows = "".join(
        f'<tr><td>{_esc(src)}</td><td>{s["calls"]}</td><td>{s["retries"]}</td>'
        f'<td>{s["errors"]}</td><td>{s["avg_latency_ms"]} мс</td>'
        f'<td>{s["tokens_in"]}→{s["tokens_out"]}</td></tr>'
        for src, s in snap["by_source"].items())
    t = snap["total"]
    return (f'<div class="panel metrics"><h2>Метрики прогона</h2>'
            f'<div class="h-sub">внешние вызовы за {snap["wall_seconds"]} c · '
            f'все считаются в единой точке (client.py) → outputs/run_metrics.json</div>'
            f'<table class="mtab"><thead><tr><th>источник</th><th>вызовы</th><th>ретраи</th>'
            f'<th>ошибки</th><th>ср. задержка</th><th>токены in→out</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
            f'<div class="mtot">итого: {t["calls"]} вызовов, {t["retries"]} ретраев, '
            f'{t["errors"]} ошибок, токенов LLM {t["tokens_in"]}→{t["tokens_out"]}</div></div>')


def render(profile, layered, hyps, kpi="", tech=None, analysis=None, runinfo=None):
    # итоги по металлам — по всем символам схемы, а не по зашитым Ni/Cu
    symbols = list(ELEMENT_SYMBOLS)
    for h in hyps:                                   # добираем символы, если схема шире
        for sym in (h.metrics.get("rec_tonnes") or {}):
            if sym not in symbols:
                symbols.append(sym)
    totals = {sym: round(sum(h.metrics["rec_tonnes"].get(sym, 0) for h in hyps), 1)
              for sym in symbols}
    metal_summary = "".join(
        f'<span><b>{v} т</b><br>извлекаемого {_esc(sym)} в хвостах (факт)</span>'
        for sym, v in totals.items())
    cards = "\n".join(_card(h, runinfo) for h in hyps)
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
*{{box-sizing:border-box}} body{{margin:0;font-family:'Ubuntu',-apple-system,Segoe UI,Roboto,Arial,sans-serif;
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
.card{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:22px 24px;margin:0 0 18px;
  box-shadow:0 2px 12px rgba(31,122,224,.06);transition:box-shadow .18s ease,transform .18s ease,border-color .18s}}
.card:hover{{box-shadow:0 8px 26px rgba(31,122,224,.13);transform:translateY(-2px);border-color:#cfe0ea}}
/* строка источника + бейджи прогона (что применялось) */
.srcbar{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:2px 0 14px}}
.srcfile{{font-size:12.5px;color:#5f7d8c}} .srcfile b{{color:#12303f}}
.badge{{font-size:10.5px;font-weight:700;color:#0a7f79;background:var(--teal-soft);
  border:1px solid #cdeeea;padding:3px 9px;border-radius:20px;transition:transform .15s}}
.badge:hover{{transform:translateY(-1px)}}
.glink{{margin-left:auto;font-size:12px;color:var(--blue);text-decoration:none}}
.glink:hover{{text-decoration:underline}}
/* нейтральная заметка аналитики (без эмодзи/крика) */
.anote{{background:#f6fafc;border:1px solid var(--line);border-left:3px solid #cbd9e2;
  border-radius:8px;padding:9px 13px;font-size:12.5px;color:#425c69;margin:8px 0 0}}
.anote b{{color:#12303f}}
/* метрики прогона */
.metrics .mtab{{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}}
.metrics .mtab th{{text-align:left;color:#9db3bf;font-weight:600;padding:5px 8px;border-bottom:1px solid var(--line)}}
.metrics .mtab td{{padding:5px 8px;border-bottom:1px solid #f0f5f8}}
.metrics .mtot{{font-size:11.5px;color:#9db3bf;margin-top:8px}}
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
.exp{{font-size:13px;margin:10px 0;background:#f6fbfd;border:1px solid var(--line);
  border-radius:10px;padding:10px 12px}}
.exp>b{{font-size:11px;text-transform:uppercase;color:#9db3bf}}
.exprow{{display:flex;gap:10px;align-items:baseline;margin:5px 0 0}}
.exprow span{{flex:0 0 62px;text-align:right;font-size:10px;font-weight:700;letter-spacing:.4px;
  text-transform:uppercase;color:#9db3bf}}
.exprow p{{margin:0;font-size:13px}}
.rm{{font-size:13px;margin:10px 0;background:#f6fbfd;border:1px solid var(--line);
  border-radius:10px;padding:10px 14px}}
.rm>b{{font-size:11px;text-transform:uppercase;color:#9db3bf}}
.rm ol{{margin:6px 0 0;padding-left:20px}} .rm li{{margin:0 0 8px}}
.rm .crit{{display:block;margin-top:2px;font-size:12px;color:#0a7f79}}
.src{{font-size:12px;margin:10px 0}} .src b{{font-size:11px;text-transform:uppercase;color:#9db3bf}}
.src ul{{margin:5px 0 0;padding-left:18px;color:#37505c}} .src li{{margin:2px 0}}
.wp{{font-size:12px;margin:10px 0}} .wp b{{font-size:11px;text-transform:uppercase;color:#9db3bf}}
.wp p{{margin:4px 0 0}} .wp code{{background:#eef4f7;padding:1px 4px;border-radius:3px}}
.wpq{{margin:6px 0 4px;padding:6px 10px;border-left:3px solid #12b3ab;background:#f2fbfa;
  color:#2a4550;font-size:12.5px;overflow-wrap:anywhere}}
.lit{{font-size:12px;margin:10px 0}} .lit>b{{font-size:11px;text-transform:uppercase;color:#9db3bf}}
.litq{{margin:6px 0 4px;padding:6px 10px;border-left:3px solid #1f7ae0;background:#f4f9fe;
  color:#2a4550;font-size:12.5px;overflow-wrap:anywhere}}
.litloc{{display:block;margin-top:3px;color:#9db3bf;font-size:11px}}
.wpsrc{{font-size:11px;color:#9db3bf}} .wpsrc a{{color:#1f7ae0;text-decoration:none}}
.dos{{font-size:12px;margin:10px 0}} .dos>b{{font-size:11px;text-transform:uppercase;color:#9db3bf}}
.dos code{{background:#eef4f7;padding:1px 4px;border-radius:3px}}
.dosrc{{margin:6px 0;padding:7px 10px;background:#f6fafd;border:1px solid var(--line);border-radius:8px}}
.doshead{{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}}
.doshead a{{color:#1f7ae0;text-decoration:none;font-weight:600;font-size:12.5px;flex:1;min-width:0;overflow-wrap:anywhere}}
.cit{{background:#12b3ab;color:#fff;font-size:10px;font-weight:700;padding:1px 6px;border-radius:9px;white-space:nowrap}}
.yr{{color:#9db3bf;font-size:11px}} .dosq{{color:#37505c;font-size:12px;margin-top:3px;overflow-wrap:anywhere}}
.evidence{{font-size:12px;margin-top:8px}} .evidence>b{{font-size:11px;text-transform:uppercase;color:#9db3bf}}
.ev{{display:flex;justify-content:space-between;gap:10px;padding:3px 0;border-bottom:1px dashed var(--line)}}
.ev em{{color:#9db3bf;font-style:normal}}
.grind{{background:#eefaf8;border:1px solid #bfe9e4;border-radius:10px;padding:10px 14px;
  margin-top:12px;font-size:13.5px}}
.warn{{background:#fff6e9;border:1px solid #f4dcae;border-radius:10px;padding:10px 14px;
  margin-top:10px;font-size:13px;color:#8a5a12}}
.fb{{background:#f1ecfc;border:1px solid #d9ccf5;border-radius:10px;padding:10px 14px;
  margin-top:10px;font-size:13px;color:#5b3fa8}}
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
  <div class="srcbar">
    <span class="srcfile">источник: <b>{_esc(profile.source)}</b></span>
    {_run_badges(hyps, tech, runinfo)}
    <a class="glink" href="glossary.html">как читать →</a>
  </div>
  {"".join(f'<div class="warn">{_esc(w)}</div>' for w in getattr(profile, "warnings", []))}
  <div class="kpi"><b>KPI</b> &nbsp;{_esc(kpi)}</div>
  <div class="summary">
    {metal_summary}
    <span><b>{len(hyps)}</b><br>гипотез</span>
  </div>
  <div class="panel">
    <h2>Граф знаний</h2>
    {graph}
    <div class="legend">
      <span><i style="background:#1f7ae0"></i>элемент → класс (потери)</span>
      <span><i style="background:#12b3ab"></i>класс → извлекаемая форма</span>
      <span><i style="background:#d3dee6"></i>класс → неизвлекаемая форма</span>
    </div>
  </div>
  {_analysis_html(analysis)}
  <h2 style="margin:0 0 10px;font-size:16px">Гипотезы</h2>
  {cards}
  {_metrics_footer()}
  <footer><a href="glossary.html">как читать граф, кривые и метрики →</a></footer>
</div></body></html>"""
