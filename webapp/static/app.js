(function () {
  const ALLOWED = new Set(["xlsx", "csv", "pdf", "docx", "txt", "md",
    "png", "jpg", "jpeg", "tif", "tiff", "webp", "bmp"]);
  const extOk = n => { const i = n.lastIndexOf("."); return i >= 0 && ALLOWED.has(n.slice(i + 1).toLowerCase()); };

  const hEl = document.getElementById("health");
  if (hEl) {
    fetch("/health").then(r => r.json()).then(h => {
      const dot = (ok, name) =>
        `<span class="dot" title="${ok ? "доступен" : "недоступен"}">${name} <i class="${ok ? "ok" : "no"}"></i></span>`;
      hEl.innerHTML = dot(h.llm, "LLM") + dot(h.ocr, "OCR") + `<span class="dot">поиск: ${h.search_backend}</span>`;
      hEl.title = h.note;
    }).catch(() => { hEl.textContent = ""; });
  }

  document.querySelectorAll("[data-materials]").forEach(m => {
    const body = m.querySelector(".mat-body"), btn = m.querySelector(".mat-more");
    if (!body || !btn) return;
    if (body.scrollHeight > body.clientHeight + 4) {
      body.classList.add("clamped");
      btn.hidden = false;
      btn.addEventListener("click", () => {
        const open = body.classList.toggle("open");
        btn.textContent = open ? "свернуть" : "показать все";
      });
    }
  });

  document.querySelectorAll(".panels .panel svg").forEach(initGraph);
  function initGraph(svg) {
    let vb = (svg.getAttribute("viewBox") || "0 0 900 400").split(/\s+/).map(Number);
    const base = vb.slice();
    const apply = () => svg.setAttribute("viewBox", vb.join(" "));
    const edges = [...svg.querySelectorAll(".gedge")], nodes = [...svg.querySelectorAll(".gnode")];
    const clearOn = () => [...edges, ...nodes].forEach(el => el.classList.remove("on"));
    const clear = () => { svg.classList.remove("hl"); clearOn(); };

    const knodes = [...svg.querySelectorAll(".knode")], kedges = [...svg.querySelectorAll(".kedge")];
    const npos = new Map();
    knodes.forEach(g => {
      const m = /translate\(\s*([-\d.]+)[ ,]+([-\d.]+)\s*\)/.exec(g.getAttribute("transform") || "");
      npos.set(g.dataset.id, { el: g, x: m ? +m[1] : 0, y: m ? +m[2] : 0 });
    });
    let ndrag = null;
    knodes.forEach(g => g.addEventListener("pointerdown", e => {
      e.stopPropagation();
      const p = npos.get(g.dataset.id);
      ndrag = { id: g.dataset.id, sx: e.clientX, sy: e.clientY, ox: p.x, oy: p.y };
      g.classList.add("dragging"); svg.setPointerCapture(e.pointerId);
    }));

    const panel = svg.closest(".panel");
    if (panel) {
      panel.style.position = "relative";
      const btn = document.createElement("button"); btn.type = "button"; btn.className = "greset";
      btn.title = "вернуть исходный вид"; btn.setAttribute("aria-label", "сброс вида");
      btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        + 'stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/>'
        + '<path d="M3 3v5h5"/></svg>';
      btn.addEventListener("click", () => { vb = base.slice(); apply(); clear(); });
      panel.appendChild(btn);
    }
    let drag = null;
    svg.addEventListener("pointerdown", e => {
      if (e.target.closest(".gnode")) return;
      drag = { x: e.clientX, y: e.clientY, vb: vb.slice() };
      svg.classList.add("grab"); svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener("pointermove", e => {
      const r = svg.getBoundingClientRect();
      if (ndrag) {
        const nx = ndrag.ox + (e.clientX - ndrag.sx) * vb[2] / r.width;
        const ny = ndrag.oy + (e.clientY - ndrag.sy) * vb[3] / r.height;
        const p = npos.get(ndrag.id); p.x = nx; p.y = ny;
        p.el.setAttribute("transform", `translate(${nx.toFixed(1)},${ny.toFixed(1)})`);
        kedges.forEach(ed => {
          if (ed.dataset.a === ndrag.id) { ed.setAttribute("x1", nx.toFixed(1)); ed.setAttribute("y1", ny.toFixed(1)); }
          if (ed.dataset.b === ndrag.id) { ed.setAttribute("x2", nx.toFixed(1)); ed.setAttribute("y2", ny.toFixed(1)); }
        });
        return;
      }
      if (!drag) return;
      vb[0] = drag.vb[0] - (e.clientX - drag.x) * vb[2] / r.width;
      vb[1] = drag.vb[1] - (e.clientY - drag.y) * vb[3] / r.height; apply();
    });
    svg.addEventListener("pointerup", () => {
      drag = null; svg.classList.remove("grab");
      if (ndrag) { npos.get(ndrag.id).el.classList.remove("dragging"); ndrag = null; }
    });
    svg.addEventListener("wheel", e => {
      e.preventDefault(); const r = svg.getBoundingClientRect();
      const mx = vb[0] + vb[2] * (e.clientX - r.left) / r.width;
      const my = vb[1] + vb[3] * (e.clientY - r.top) / r.height;
      const f = e.deltaY < 0 ? 0.88 : 1.14;
      vb[2] *= f; vb[3] *= f; vb[0] = mx - (mx - vb[0]) * f; vb[1] = my - (my - vb[1]) * f; apply();
    }, { passive: false });
    svg.addEventListener("dblclick", () => { vb = base.slice(); apply(); clear(); });
    nodes.forEach(n => n.addEventListener("click", e => {
      e.stopPropagation(); const id = n.dataset.id; const nb = new Set([id]);
      svg.classList.add("hl"); clearOn(); n.classList.add("on");
      edges.forEach(ed => { if (ed.dataset.a === id || ed.dataset.b === id) {
        ed.classList.add("on"); nb.add(ed.dataset.a); nb.add(ed.dataset.b); } });
      nodes.forEach(nd => { if (nb.has(nd.dataset.id)) nd.classList.add("on"); });
    }));
    svg.addEventListener("click", e => { if (!e.target.closest(".gnode")) clear(); });
  }

  const form = document.getElementById("run-form");
  if (!form) return;
  const zoneFiles = { data: [], knowledge: [] };

  function readEntry(entry, out) {
    return new Promise(res => {
      if (entry.isFile) {
        entry.file(f => { if (extOk(f.name)) out.push(f); res(); }, () => res());
      } else if (entry.isDirectory) {
        const reader = entry.createReader();
        const batch = () => reader.readEntries(async ents => {
          if (!ents.length) return res();
          for (const e of ents) await readEntry(e, out);
          batch();
        }, () => res());
        batch();
      } else res();
    });
  }

  async function fromDrop(dt) {
    const out = [];
    const entries = dt.items ? Array.from(dt.items)
      .map(it => it.webkitGetAsEntry && it.webkitGetAsEntry()).filter(Boolean) : [];
    if (entries.length) { for (const en of entries) await readEntry(en, out); }
    else { for (const f of dt.files) if (extOk(f.name)) out.push(f); }
    return out;
  }

  document.querySelectorAll(".dz").forEach(dz => {
    const role = dz.dataset.role;
    const input = dz.querySelector(".dz-input");
    const list = document.querySelector(`.dz-list[data-list="${role}"]`);
    const render = () => {
      list.innerHTML = zoneFiles[role].map((f, i) =>
        `<li>${f.name}<button type="button" class="dz-x" data-i="${i}" title="убрать">×</button></li>`).join("")
        + (zoneFiles[role].length ? `<button type="button" class="dz-clear">очистить (${zoneFiles[role].length})</button>` : "");
    };
    const add = files => {
      const seen = new Set(zoneFiles[role].map(f => f.name + f.size));
      for (const f of files) if (extOk(f.name) && !seen.has(f.name + f.size)) {
        zoneFiles[role].push(f); seen.add(f.name + f.size);
      }
      render();
    };

    dz.addEventListener("click", e => { if (!e.target.closest(".dz-list")) input.click(); });
    input.addEventListener("change", () => { add(input.files); input.value = ""; });
    list.addEventListener("click", e => {
      if (e.target.classList.contains("dz-x")) { zoneFiles[role].splice(+e.target.dataset.i, 1); render(); }
      if (e.target.classList.contains("dz-clear")) { zoneFiles[role] = []; render(); }
    });
    ["dragenter", "dragover"].forEach(ev =>
      dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("over"); }));
    ["dragleave", "dragend"].forEach(ev =>
      dz.addEventListener(ev, () => dz.classList.remove("over")));
    dz.addEventListener("drop", async e => {
      e.preventDefault(); dz.classList.remove("over");
      add(await fromDrop(e.dataTransfer));
    });
  });

  const breadthEl = document.getElementById("breadth");
  const breadthVal = document.getElementById("breadth-val");
  if (breadthEl && breadthVal) {
    const label = v => v <= 15 ? "точечно" : v <= 45 ? "сбалансировано"
      : v <= 75 ? "шире" : "разнообразно";
    const upd = () => { breadthVal.textContent = label(+breadthEl.value); };
    breadthEl.addEventListener("input", upd); upd();
  }

  const statusEl = document.getElementById("status");
  const go = document.getElementById("go");
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const kpi = document.getElementById("kpi").value.trim();
    if (!kpi) { statusEl.textContent = "укажите цель (KPI)"; statusEl.className = "status err"; return; }
    if (!zoneFiles.data.length && !zoneFiles.knowledge.length) {
      statusEl.textContent = "добавьте хотя бы один файл или папку (данные и/или знания)";
      statusEl.className = "status err"; return;
    }
    const constraints = document.getElementById("constraints").value.trim();
    const fd = new FormData();
    fd.append("kpi", kpi);
    fd.append("constraints", constraints);
    fd.append("web_search", document.getElementById("web_search").checked);
    fd.append("use_llm", document.getElementById("use_llm").checked);
    fd.append("max_chunks", document.getElementById("max_chunks").value || "18");
    fd.append("breadth", ((+(breadthEl ? breadthEl.value : 30)) / 100).toFixed(2));
    zoneFiles.data.forEach(f => fd.append("data_files", f, f.name));
    zoneFiles.knowledge.forEach(f => fd.append("knowledge_files", f, f.name));

    go.disabled = true; statusEl.className = "status busy";
    statusEl.textContent = "идёт прогон — детерминированные ветки + обогащение (может занять минуты)…";
    try {
      const r = await fetch("/api/runs", { method: "POST", body: fd });
      if (!r.ok) { const t = await r.json().catch(() => ({})); throw new Error(t.detail || `ошибка ${r.status}`); }
      const data = await r.json();
      window.location.href = data.redirect || `/runs/${data.run_id}`;
    } catch (err) {
      statusEl.textContent = "не удалось: " + err.message;
      statusEl.className = "status err"; go.disabled = false;
    }
  });
})();
