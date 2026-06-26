// Кликабельная цепочка доказательств — центр интерпретируемости.
// Cytoscape-граф пути гипотезы (/graph/path/{id}); клик по ребру → дословная
// цитата + первоисточник.

import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { nodeTypeMeta, signSymbol } from "../lib/format";
import type { CyEdgeData, GraphPath } from "../types";

function edgeColor(sign: string): string {
  return sign === "+" ? "#3fae84" : sign === "-" ? "#dd7777" : "#9aa3b2";
}

function stylesheet(): cytoscape.StylesheetCSS[] {
  return [
    {
      selector: "node",
      css: {
        "background-color": (n: cytoscape.NodeSingular) => nodeTypeMeta(n.data("type")).color,
        label: "data(label)",
        color: "#334155",
        "font-size": 11,
        "font-family": "Inter, system-ui, sans-serif",
        "text-valign": "bottom",
        "text-margin-y": 5,
        "text-wrap": "wrap",
        "text-max-width": "120px",
        width: 26,
        height: 26,
        "border-width": 2,
        "border-color": "#ffffff",
      },
    },
    {
      selector: "edge",
      css: {
        width: 2.5,
        "line-color": (e: cytoscape.EdgeSingular) => edgeColor(e.data("sign")),
        "target-arrow-color": (e: cytoscape.EdgeSingular) => edgeColor(e.data("sign")),
        "target-arrow-shape": "triangle",
        "curve-style": "bezier",
        label: (e: cytoscape.EdgeSingular) => {
          const y = e.data("year");
          return `${signSymbol(e.data("sign"))}${y ? " " + y : ""}`;
        },
        "font-size": 10,
        color: "#64748b",
        "text-background-color": "#ffffff",
        "text-background-opacity": 1,
        "text-background-padding": "2px",
      },
    },
    {
      selector: "edge.selected",
      css: {
        width: 4.5,
        "line-color": "#cd6c4c",
        "target-arrow-color": "#cd6c4c",
        color: "#cd6c4c",
      },
    },
    {
      selector: "node.kpi-pulse",
      css: { "border-color": "#dd8a6c", "border-width": 3 },
    },
  ];
}

export function EvidenceGraph({ hypothesisId }: { hypothesisId: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [graph, setGraph] = useState<GraphPath | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<CyEdgeData | null>(null);

  useEffect(() => {
    let alive = true;
    setPicked(null);
    setError(null);
    setGraph(null);
    api
      .graphPath(hypothesisId)
      .then((g) => alive && setGraph(g))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [hypothesisId]);

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
      layout: { name: "breadthfirst", directed: true, spacingFactor: 1.25, padding: 18 },
      minZoom: 0.4,
      maxZoom: 2.5,
      wheelSensitivity: 0.2,
    });
    cy.nodes('[type = "KPI"]').addClass("kpi-pulse");
    cy.on("tap", "edge", (evt) => {
      cy.edges().removeClass("selected");
      evt.target.addClass("selected");
      setPicked(evt.target.data() as CyEdgeData);
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        cy.edges().removeClass("selected");
        setPicked(null);
      }
    });
    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [graph]);

  return (
    <div className="space-y-2">
      <div className="relative h-72 w-full overflow-hidden rounded-lg border border-line bg-slate-50">
        <div ref={containerRef} className="h-full w-full" />
        {!graph && !error && (
          <div className="absolute inset-0 grid place-items-center text-xs text-slate-400">
            Загрузка цепочки…
          </div>
        )}
        {error && (
          <div className="absolute inset-0 grid place-items-center px-4 text-center text-xs text-rose-500">
            {error}
          </div>
        )}
        <span className="pointer-events-none absolute bottom-1.5 right-2 text-[10px] text-slate-400">
          клик по ребру — цитата
        </span>
      </div>

      {picked ? (
        <div className="animate-fade-in rounded-lg border border-clay-200 bg-clay-50/50 p-3">
          <div className="mb-1 text-xs text-slate-500">
            {picked.source} <span className="text-clay-500">{signSymbol(picked.sign)}</span>{" "}
            {picked.target}
            {picked.year ? ` · ${picked.year}` : ""}
          </div>
          {picked.quote ? (
            <p className="quote">«{picked.quote}»</p>
          ) : (
            <p className="text-xs text-slate-400">цитата не приложена</p>
          )}
          {picked.doc_id && (
            <div className="mt-1.5 text-xs text-slate-500">
              Первоисточник: <span className="src-tag">{picked.doc_id}</span>
            </div>
          )}
        </div>
      ) : (
        <p className="text-xs text-slate-400">
          Выберите ребро на графе, чтобы увидеть дословную цитату и первоисточник.
        </p>
      )}
    </div>
  );
}
