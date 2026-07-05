from __future__ import annotations


def _mock_graph_svg() -> str:
    return """
<svg viewBox="0 0 660 280" width="100%" font-family="inherit">
  <text x="70" y="20" font-size="11" fill="#9db3bf">ЭЛЕМЕНТ</text>
  <text x="300" y="20" font-size="11" fill="#9db3bf">КЛАСС КРУПНОСТИ</text>
  <text x="520" y="20" font-size="11" fill="#9db3bf">МИНЕРАЛЬНАЯ ФОРМА</text>
  <!-- рёбра (ширина ∝ тонны) -->
  <line x1="110" y1="140" x2="300" y2="95" stroke="#12b3ab" stroke-width="9" opacity=".55"/>
  <line x1="110" y1="140" x2="300" y2="195" stroke="#12b3ab" stroke-width="4" opacity=".55"/>
  <line x1="360" y1="95" x2="520" y2="55" stroke="#12b3ab" stroke-width="7" opacity=".7"/>
  <line x1="360" y1="95" x2="520" y2="130" stroke="#1f7ae0" stroke-width="5" opacity=".7"/>
  <line x1="360" y1="195" x2="520" y2="205" stroke="#c2cdd4" stroke-width="6" opacity=".8"/>
  <!-- узлы -->
  <g font-size="12" text-anchor="middle">
    <circle cx="80" cy="140" r="26" fill="#12303f"/><text x="80" y="144" fill="#fff">Ni</text>
    <rect x="300" y="78" width="60" height="34" rx="8" fill="#e6f7f5" stroke="#12b3ab"/><text x="330" y="99">-10</text>
    <rect x="300" y="178" width="60" height="34" rx="8" fill="#e6f7f5" stroke="#12b3ab"/><text x="330" y="199">-45+20</text>
    <rect x="520" y="40" width="120" height="30" rx="8" fill="#e6f7f5" stroke="#12b3ab"/><text x="580" y="60">Раскрытый ✓</text>
    <rect x="520" y="115" width="120" height="30" rx="8" fill="#e6f7f5" stroke="#12b3ab"/><text x="580" y="135">Закрытый ✓</text>
    <rect x="520" y="190" width="120" height="30" rx="8" fill="#f4f6f7" stroke="#c2cdd4"/><text x="580" y="210" fill="#8a9aa5">Силикат ✗</text>
  </g>
  <text x="200" y="118" font-size="10" fill="#12b3ab" transform="rotate(-14 200 118)">толще ребро = больше тонн</text>
</svg>"""

def _mock_liberation_svg() -> str:
    W, H, pad = 620, 210, 34
    xs = [pad + (W - 2*pad) * i / 4 for i in range(5)]
    labels = ["+125", "-125+71", "-71+45", "-45+20", "-10"]
    locked = [78, 70, 55, 35, 12]
    recover = [40, 52, 68, 80, 88]
    def y(p): return H - pad - (H - 2*pad) * p / 100
    def poly(vals, color):
        pts = " ".join(f"{xs[i]:.0f},{y(v):.0f}" for i, v in enumerate(vals))
        dots = "".join(f'<circle cx="{xs[i]:.0f}" cy="{y(v):.0f}" r="3.5" fill="{color}"/>'
                       for i, v in enumerate(vals))
        return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>{dots}'
    grid = "".join(f'<line x1="{pad}" y1="{y(v):.0f}" x2="{W-pad}" y2="{y(v):.0f}" stroke="#eef4f7"/>'
                   f'<text x="{pad-6}" y="{y(v)+4:.0f}" text-anchor="end" font-size="9" fill="#9db3bf">{v}%</text>'
                   for v in (0, 25, 50, 75, 100))
    labs = "".join(f'<text x="{xs[i]:.0f}" y="{H-10}" text-anchor="middle" font-size="10" fill="#5f7d8c">{lb}</text>'
                   for i, lb in enumerate(labels))

    xb = xs[2]
    marker = (f'<line x1="{xb:.0f}" y1="{pad}" x2="{xb:.0f}" y2="{H-pad}" stroke="#f59e0b" '
              f'stroke-dasharray="4 3" stroke-width="1.5"/>'
              f'<text x="{xb+5:.0f}" y="{pad+12}" font-size="10" fill="#f59e0b">обрыв раскрытия</text>')
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" font-family="inherit">{grid}'
            f'{poly(locked, "#1f7ae0")}{poly(recover, "#12b3ab")}{marker}{labs}'
            f'<text x="{W-pad}" y="{y(locked[-1])-6:.0f}" font-size="10" fill="#1f7ae0" text-anchor="end">закрытый</text>'
            f'<text x="{W-pad}" y="{y(recover[-1])-6:.0f}" font-size="10" fill="#12b3ab" text-anchor="end">извлекаемо</text>'
            f'</svg>')

def _mock_swanson_svg() -> str:
    return """
<svg viewBox="0 0 620 160" width="100%" font-family="inherit" font-size="12" text-anchor="middle">
  <defs><marker id="ar" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
    <path d="M0,0 L6,3 L0,6 Z" fill="#12303f"/></marker>
  <marker id="ar2" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
    <path d="M0,0 L6,3 L0,6 Z" fill="#12b3ab"/></marker></defs>
  <line x1="130" y1="70" x2="250" y2="70" stroke="#12303f" stroke-width="2" marker-end="url(#ar)"/>
  <line x1="370" y1="70" x2="490" y2="70" stroke="#12303f" stroke-width="2" marker-end="url(#ar)"/>
  <path d="M95,90 Q310,175 525,90" fill="none" stroke="#12b3ab" stroke-width="2.2"
        stroke-dasharray="6 4" marker-end="url(#ar2)"/>
  <g>
    <rect x="35" y="52" width="120" height="36" rx="9" fill="#e6f7f5" stroke="#12b3ab"/><text x="95" y="75">известь (A)</text>
    <rect x="250" y="52" width="120" height="36" rx="9" fill="#eef4f7" stroke="#9db3bf"/><text x="310" y="75">pH пульпы (B)</text>
    <rect x="465" y="52" width="130" height="36" rx="9" fill="#e6f7f5" stroke="#12b3ab"/><text x="530" y="75">извлечение Ni (C)</text>
  </g>
  <text x="190" y="60" font-size="10" fill="#5f7d8c">повышает</text>
  <text x="430" y="60" font-size="10" fill="#5f7d8c">повышает</text>
  <text x="310" y="150" font-size="11" fill="#12b3ab">скрытая связь A→C — прямой в корпусе нет (гипотеза)</text>
</svg>"""

FIGURES = [
    ("Как читать граф профиля потерь", _mock_graph_svg(),
     "Три слоя: <b>Элемент → Класс крупности → Минеральная форма</b>. Ширина ребра ∝ "
     "тоннам теряемого металла (толще = больнее). Цвет формы: <b>бирюзовый ✓ извлекаемо</b> "
     "текущей технологией, <b>серый ✗ — физический потолок</b> (силикаты/пирит — не берутся). "
     "Читать так: идём от Ni по самому толстому ребру к проблемному классу, оттуда — к "
     "доминирующей форме; она и задаёт тип вмешательства."),
    ("Как читать кривую раскрытия", _mock_liberation_svg(),
     "По оси X — классы крупности (крупный→тонкий), по Y — доли <b>закрытого</b> (заперт в "
     "сростках, синий) и <b>извлекаемого</b> (бирюзовый) минерала. Где синяя падает ниже "
     "бирюзовой — <b>«обрыв раскрытия»</b>: граница, мельче которой минерал раскрывается. "
     "Рекомендация «измельчать мельче этой границы» берётся ОТСЮДА, из данных, а не из головы."),
    ("Разрыв Свонсона (literature-based discovery)", _mock_swanson_svg(),
     "Классический приём поиска скрытых связей. В корпусе есть «известь→pH» и «pH→извлечение "
     "Ni», но прямой связи «известь→извлечение Ni» нет. Система предлагает её как <b>гипотезу</b> "
     "(пунктир). Знак (повышает/снижает) перемножается по цепочке детерминированно. Это не "
     "выдумка LLM: обе опорные связи заземлены дословной цитатой из источника (цитатный гейт)."),
]

METRICS = [
    ("Тоннаж извлекаемого металла", "ФАКТ из данных", "Σ тонн по извлекаемым формам класса",
     "Берётся напрямую из ячеек Excel. Ничего не оценивается — это измерение.",
     "класс −10: 120 т извлекаемого Ni (из ячеек отчёта)"),
    ("impact — масштаб потери", "0..1 · факт из данных",
     "impact = извлек.тонны класса / Σ извлек.тонны фабрики",
     "Какая доля всех излечимых потерь фабрики приходится на класс. Ведёт ранжирование.",
     "120 / 385 = <b>0.31</b> → 31% излечимых потерь Ni сидит в этом классе"),
    ("addressability — «излечимость»", "0..1 · факт из данных",
     "addressability = извлек.тонны / все тонны класса",
     "Какая часть потерь класса вообще берётся текущей технологией (остальное — потолок).",
     "120 / 150 = <b>0.80</b> → 80% потерь класса в принципе излечимо"),
    ("clarity — ясность механизма", "0..1 · факт из данных",
     "clarity = тонны главной формы / извлек.тонны",
     "Доминирование ОДНОЙ формы = один чёткий механизм = защитимее гипотеза.",
     "100 / 120 = <b>0.83</b> → механизм почти однозначен"),
    ("feasibility — реализуемость", "0.6 / 1.0 · наша шкала",
     "1.0 без нового оборудования, иначе 0.6",
     "Задаётся правилом диагноза. Грубая шкала — честно помечаем как нашу оценку.",
     "грохочение существующим узлом → <b>1.0</b>"),
    ("confidence — достоверность", "0.3 / 0.6 / 1.0 · наша шкала",
     "по полноте минералогии и целостности чисел (#REF!)",
     "Есть ли под классом минералогия и не битые ли ячейки.",
     "минералогия полная, чисел нет #REF! → <b>1.0</b>"),
    ("priority — приоритет", "0..1 · НАША эвристика (не факт)",
     "impact·(0.5+0.5·addr)·(0.7+0.3·clarity)·feas·conf",
     "Свёртка для сортировки. МАСШТАБ (impact, факт) ведёт; addressability и clarity мягко "
     "модулируют (не переворачивают порядок); feasibility/confidence — множители. Это НАШЕ "
     "правило приоритизации, поэтому формула показана открыто — можете пересчитать вручную.",
     "0.31·(0.5+0.5·0.80)·(0.7+0.3·0.83)·1·1 = 0.31·0.90·0.949 = <b>≈0.265</b>"),
]

TECHNIQUES = [
    ("Цитатный гейт (ветка Б)",
     "Связь из текста принимается, ТОЛЬКО если её дословная цитата реально есть в источнике "
     "(для OCR — мягко, ≥80% слов). Так LLM не может «досочинить» факт: нет цитаты — нет связи. "
     "Знак влияния берётся из закрытого словаря {повышает/снижает/не_влияет/связан}, а не от LLM."),
    ("Новизна (novelty, ветка Б)",
     "Редкость концептов связи в поданном корпусе (idf-подобно): чем реже сущности встречаются "
     "в имеющемся знании — тем связь новее. Это прокси к «отличию от существующего»: когда "
     "подключат внешнюю базу готовых решений — сюда встанет непохожесть на неё."),
    ("FAMILY-COVERAGE (бенчмарк)",
     "Наши и эталонные вмешательства раскладываются по семействам (измельчение / классификация "
     "/ грохочение / флотация / реагенты). RECALL — доля эталона, чьё семейство встретилось у "
     "нас; PRECISION — доля наших семейств, что есть в эталоне (не набросали ли лишнего); "
     "GROUNDING — доля гипотез с привязкой к ячейкам. Официальный эталон — одна пара (по QA)."),
]

def body_html() -> str:
    figs = "".join(
        f'<div class="fig"><h3>{t}</h3><div class="canvas">{svg}</div><p>{d}</p></div>'
        for t, svg, d in FIGURES)
    mrows = "".join(
        f'<tr><td class="mt">{t}<span class="rng">{r}</span></td>'
        f'<td class="mf"><code>{f}</code><div class="mex">{ex}</div></td>'
        f'<td class="md">{d}</td></tr>' for t, r, f, d, ex in METRICS)
    trows = "".join(f'<div class="e"><div class="term">{t}</div><div class="d">{d}</div></div>'
                    for t, d in TECHNIQUES)
    return f"""
  <h2>Рисунки: как их читать</h2>
  {figs}
  <h2>Метрики: формула + пример на числах</h2>
  <div class="note">Честно разделяем: <b>факт из данных</b> (тоннаж, impact, addressability,
  clarity — считаются прямо из ячеек) и <b>наша эвристика</b> (priority, шкалы feasibility/
  confidence — это НАШЕ правило приоритизации, показано открыто, без подтасовки).</div>
  <table class="gtab"><tbody>{mrows}</tbody></table>
  <h2>Техники и гейты</h2>
  {trows}"""

def render():
    body = body_html()
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Как это читать · глоссарий</title>
<style>
body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#12303f;
  background:linear-gradient(180deg,#e7f3fa,#eef6fb);line-height:1.55}}
.wrap{{max-width:900px;margin:0 auto;padding:38px 22px 70px}}
h1{{font-size:26px;font-weight:800;margin:0 0 4px}} h1 span{{color:#12b3ab}}
h2{{font-size:18px;margin:34px 0 12px;padding-bottom:6px;border-bottom:2px solid #d6e6ef}}
.sub{{color:#5f7d8c;font-size:13.5px;margin-bottom:8px}}
.fig{{background:#fff;border:1px solid #e6eef3;border-radius:14px;padding:16px 18px;margin:0 0 16px;
  box-shadow:0 2px 10px rgba(31,122,224,.05)}}
.fig h3{{margin:0 0 10px;font-size:15px}} .canvas{{background:#fbfdfe;border-radius:10px;padding:8px}}
.fig p{{color:#37505c;font-size:13.5px;margin:12px 0 0}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e6eef3;border-radius:14px;overflow:hidden}}
td{{padding:11px 14px;border-top:1px solid #eef4f7;vertical-align:top;font-size:13px}}
.mt{{font-weight:700;width:26%}} .rng{{display:block;color:#9db3bf;font-weight:500;font-size:11px;margin-top:3px}}
.mf code{{background:#eef4f7;padding:2px 5px;border-radius:4px;font-size:12px;display:inline-block}}
.mex{{color:#0e8f88;font-size:12px;margin-top:5px}} .md{{color:#37505c;width:40%}}
.e{{background:#fff;border:1px solid #e6eef3;border-radius:12px;padding:12px 16px;margin:0 0 10px}}
.term{{font-weight:700;font-size:14px}} .d{{color:#37505c;font-size:13px;margin-top:3px}}
a{{color:#1f7ae0;text-decoration:none;font-size:13px}}
.note{{background:#fff7ed;border:1px solid #fde3c0;border-radius:10px;padding:10px 14px;
  font-size:12.5px;color:#7c4a12;margin:6px 0 18px}}
.gtab{{width:100%;border-collapse:collapse}}
</style></head><body><div class="wrap">
  <a href="javascript:history.back()">← назад к отчёту</a>
  <h1>Как это <span>читать</span></h1>
  <div class="sub">рисунки-примеры (иллюстративные числа), формулы метрик и техники — чтобы
  эксперт мог проверить каждый шаг, а не верить на слово</div>
  {body}
</div></body></html>"""

def write(out_dir):
    import os
    path = os.path.join(out_dir, "glossary.html")
    open(path, "w", encoding="utf-8").write(render())
    return path
