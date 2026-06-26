// Полный граф знаний в стиле Connected Papers: силовая раскладка (fcose),
// размер узла ∝ степени, цвет ∝ типу, наведение подсвечивает окрестность,
// клик по узлу/ребру открывает детали (цитаты, первоисточники).

import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import { NODE_TYPE_META, nodeTypeMeta, signSymbol } from "../lib/format";
import type { CyEdgeData, FullCyNodeData, FullGraph } from "../types";

// регистрация плагина раскладки — один раз на модуль
let fcoseReady = false;
function ensureFcose() {
  if (!fcoseReady) {
    try {
      cytoscape.use(fcose);
    } catch {
      /* уже зарегистрирован (hot-reload) */
    }
    fcoseReady = true;
  }
}

function edgeColor(sign: string): string {
  return sign === "+" ? "#3fae84" : sign === "-" ? "#dd7777" : "#9aa3b2";
}

// степень → диаметр узла (Connected-Papers-вид: важные узлы крупнее)
function nodeSize(degree: number): number {
  return Math.min(64, 24 + degree * 9);
}

function stylesheet(): cytoscape.StylesheetCSS[] {
  return [
    {
      selector: "node",
      css: {
        "background-color": (n: cytoscape.NodeSingular) => nodeTypeMeta(n.data("type")).color,
        width: (n: cytoscape.NodeSingular) => nodeSize(n.data("degree") ?? 0),
        height: (n: cytoscape.NodeSingular) => nodeSize(n.data("degree") ?? 0),
        label: "data(label)",
        color: "#334155",
        "font-size": 11,
        "font-family": "Inter, system-ui, sans-serif",
        "text-valign": "bottom",
        "text-margin-y": 4,
        "text-wrap": "wrap",
        "text-max-width": "130px",
        "border-width": 3,
        "border-color": "#ffffff",
        "transition-property": "opacity",
        "transition-duration": 150,
      },
    },
    {
      selector: "edge",
      css: {
        width: 2,
        "line-color": (e: cytoscape.EdgeSingular) => edgeColor(e.data("sign")),
        "target-arrow-color": (e: cytoscape.EdgeSingular) => edgeColor(e.data("sign")),
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.9,
        "curve-style": "bezier",
        opacity: 0.75,
      },
    },
    { selector: ".dim", css: { opacity: 0.12 } },
    {
      selector: "node.pick",
      css: { "border-color": "#cd6c4c", "border-width": 4 },
    },
    {
      selector: "edge.pick",
      css: { width: 4, "line-color": "#cd6c4c", "target-arrow-color": "#cd6c4c", opacity: 1 },
    },
  ];
}

type Selection =
  | { kind: "node"; data: FullCyNodeData }
  | { kind: "edge"; data: CyEdgeData }
  | null;

export function FullGraph() {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [graph, setGraph] = useState<FullGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<Selection>(null);

  useEffect(() => {
    ensureFcose();
    let alive = true;
    api
      .graph()
      .then((g) => alive && setGraph(g))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!containerRef.current || !graph) return;
    const elements: ElementDefinition[] = [
      ...graph.elements.nodes.map((n) => ({ data: n.data })),
      ...graph.elements.edges.map((e) => ({ data: e.data })),
    ];
    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: stylesheet(),
      layout: {
        name: "fcose",
        quality: "default",
        animate: true,
        animationDuration: 700,
        randomize: true,
        nodeRepulsion: 9000,
        idealEdgeLength: 110,
        padding: 30,
      } as cytoscape.LayoutOptions,
      minZoom: 0.3,
      maxZoom: 2.5,
      wheelSensitivity: 0.2,
    });
    cyRef.current = cy;

    // наведение — подсветка окрестности (сигнатурный приём Connected Papers)
    cy.on("mouseover", "node", (evt) => {
      const nb = evt.target.closedNeighborhood();
      cy.elements().addClass("dim");
      nb.removeClass("dim");
    });
    cy.on("mouseout", "node", () => cy.elements().removeClass("dim"));

    // клик — выбор узла/ребра
    cy.on("tap", "node", (evt) => {
      cy.elements().removeClass("pick");
      evt.target.addClass("pick");
      setSel({ kind: "node", data: evt.target.data() as FullCyNodeData });
    });
    cy.on("tap", "edge", (evt) => {
      cy.elements().removeClass("pick");
      evt.target.addClass("pick");
      setSel({ kind: "edge", data: evt.target.data() as CyEdgeData });
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        cy.elements().removeClass("pick");
        setSel(null);
      }
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [graph]);

  return (
    <div className="flex h-full gap-4">
      <div className="relative flex-1 overflow-hidden rounded-xl border border-line bg-surface">
        <div ref={containerRef} className="h-full w-full" />
        {!graph && !error && (
          <div className="absolute inset-0 grid place-items-center text-sm text-slate-400">
            Загрузка графа…
          </div>
        )}
        {error && (
          <div className="absolute inset-0 grid place-items-center px-6 text-center text-sm text-rose-500">
            {error}
          </div>
        )}
        <Legend />
      </div>
      <SidePanel graph={graph} sel={sel} />
    </div>
  );
}

function Legend() {
  return (
    <div className="absolute left-3 top-3 rounded-lg border border-line bg-surface/90 p-2.5 backdrop-blur">
      <div className="mb-1.5 text-[11px] font-semibold text-slate-500">Типы узлов</div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1">
        {Object.values(NODE_TYPE_META).map((m) => (
          <div key={m.label} className="flex items-center gap-1.5 text-[11px] text-slate-600">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: m.color }} />
            {m.label}
          </div>
        ))}
      </div>
      <div className="mt-2 border-t border-line pt-1.5 text-[10px] leading-snug text-slate-400">
        размер — связность узла · наведение — окрестность
      </div>
    </div>
  );
}

function SidePanel({ graph, sel }: { graph: FullGraph | null; sel: Selection }) {
  const labels = useMemo(() => {
    const m = new Map<string, string>();
    graph?.elements.nodes.forEach((n) => m.set(n.data.id, n.data.label));
    return m;
  }, [graph]);

  const incident = useMemo(() => {
    if (!graph || sel?.kind !== "node") return [];
    const id = sel.data.id;
    return graph.elements.edges.map((e) => e.data).filter((d) => d.source === id || d.target === id);
  }, [graph, sel]);

  return (
    <aside className="w-80 flex-none overflow-y-auto rounded-xl border border-line bg-surface p-4">
      {!sel && (
        <div className="grid h-full place-items-center text-center text-sm text-slate-400">
          <div>
            <div className="font-medium text-slate-500">Полный граф знаний</div>
            Кликните узел или ребро, чтобы увидеть связи, цитаты и первоисточники.
          </div>
        </div>
      )}

      {sel?.kind === "node" && (
        <div className="space-y-3">
          <div>
            <span
              className="pill"
              style={{ background: nodeTypeMeta(sel.data.type).color + "22", color: "#475569" }}
            >
              <span
                className="mr-1 inline-block h-2 w-2 rounded-full"
                style={{ background: nodeTypeMeta(sel.data.type).color }}
              />
              {nodeTypeMeta(sel.data.type).label}
            </span>
            <h3 className="mt-2 text-base font-semibold text-slate-800">{sel.data.label}</h3>
            <p className="font-mono text-xs text-slate-400">{sel.data.id}</p>
          </div>
          {sel.data.closure_reason && (
            <div className="rounded-md border border-rose-200 bg-rose-50 p-2 text-xs text-rose-700">
              Причина закрытия: {sel.data.closure_reason}
            </div>
          )}
          <div>
            <div className="mb-1.5 text-xs font-semibold text-slate-600">
              Связи ({incident.length})
            </div>
            <div className="space-y-2">
              {incident.map((e, i) => {
                const other = e.source === sel.data.id ? e.target : e.source;
                const dir = e.source === sel.data.id ? "→" : "←";
                return (
                  <div key={i} className="rounded-md border border-line bg-slate-50 p-2 text-xs">
                    <div className="text-slate-600">
                      {dir} {labels.get(other) ?? other}{" "}
                      <span className="text-clay-500">{signSymbol(e.sign)}</span>
                      {e.year ? ` · ${e.year}` : ""}
                    </div>
                    {e.quote && <p className="quote mt-1 text-[12px]">«{e.quote}»</p>}
                    {e.doc_id && <div className="mt-1 src-tag">{e.doc_id}</div>}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {sel?.kind === "edge" && (
        <div className="space-y-3">
          <div className="text-xs text-slate-500">
            {labels.get(sel.data.source) ?? sel.data.source}{" "}
            <span className="text-clay-500">{signSymbol(sel.data.sign)}</span>{" "}
            {labels.get(sel.data.target) ?? sel.data.target}
            {sel.data.year ? ` · ${sel.data.year}` : ""}
          </div>
          {sel.data.quote ? (
            <p className="quote">«{sel.data.quote}»</p>
          ) : (
            <p className="text-xs text-slate-400">цитата не приложена</p>
          )}
          {sel.data.doc_id && (
            <div className="text-xs text-slate-500">
              Первоисточник: <span className="src-tag">{sel.data.doc_id}</span>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
