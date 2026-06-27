"""Рендер графа знаний в самодостаточную HTML-страницу через Pyvis (vis.js).

Бэкенд генерирует интерактивный граф (физика, перетаскивание, подсветка
окрестности при наведении), фронт встраивает его в <iframe>. Цитаты и
первоисточники показываются во всплывающих подсказках узлов/рёбер.

vis.js инлайнится (`cdn_resources="in_line"`) — страница работает без интернета.
"""

from __future__ import annotations

import html

from app.service.entities import Edge, Node

# тип узла → (подпись, цвет). Совпадает с палитрой фронта.
_TYPE_META: dict[str, tuple[str, str]] = {
    "KPI": ("KPI", "#dd8a6c"),
    "failure": ("Провал", "#d96a6a"),
    "material": ("Материал", "#7c83e0"),
    "reagent": ("Реагент", "#4fb08c"),
    "parameter": ("Параметр", "#5b9bd6"),
    "process": ("Процесс", "#b083d6"),
}

_SIGN_COLOR = {"+": "#3fae84", "-": "#dd7777", "0": "#9aa3b2"}
_SIGN_ARROW = {"+": "↑", "-": "↓", "0": "·"}


def _degree(edges: list[Edge]) -> dict[str, int]:
    deg: dict[str, int] = {}
    for e in edges:
        deg[e.source] = deg.get(e.source, 0) + 1
        deg[e.target] = deg.get(e.target, 0) + 1
    return deg


def build_graph_html(nodes: list[Node], edges: list[Edge]) -> str:
    """Собрать HTML-страницу с интерактивным графом знаний (Pyvis).

    Размер узла растёт со связностью, цвет кодирует тип. Подсказка ребра несёт
    дословную цитату и первоисточник.
    """
    from pyvis.network import Network  # тяжёлая зависимость — импортируем лениво

    degree = _degree(edges)
    labels = {n.id: n.label for n in nodes}

    net = Network(
        height="100vh",
        width="100%",
        directed=True,
        bgcolor="#f5f4f8",
        font_color="#334155",
        neighborhood_highlight=True,  # наведение подсвечивает окрестность
        cdn_resources="in_line",
    )
    net.barnes_hut(gravity=-9000, central_gravity=0.3, spring_length=120, spring_strength=0.04)

    for node in nodes:
        type_label, color = _TYPE_META.get(node.type, (node.type, "#94a3b8"))
        tooltip = f"<b>{html.escape(node.label)}</b><br>тип: {html.escape(type_label)}"
        if node.closure_reason:
            tooltip += f"<br>закрыто: {html.escape(node.closure_reason)}"
        net.add_node(
            node.id,
            label=node.label,
            title=tooltip,
            color=color,
            size=12 + degree.get(node.id, 0) * 6,
            shape="dot",
        )

    for edge in edges:
        head = f"{labels.get(edge.source, edge.source)} {_SIGN_ARROW.get(edge.sign, edge.sign)} {labels.get(edge.target, edge.target)}"
        if edge.year:
            head += f" · {edge.year}"
        tooltip = html.escape(head)
        if edge.evidence_quote:
            tooltip += f"<br>«{html.escape(edge.evidence_quote)}»"
        if edge.doc_id:
            tooltip += f"<br>источник: {html.escape(edge.doc_id)}"
        net.add_edge(
            edge.source,
            edge.target,
            title=tooltip,
            color=_SIGN_COLOR.get(edge.sign, "#9aa3b2"),
            width=2,
        )

    return net.generate_html(notebook=False)


__all__ = ["build_graph_html"]
