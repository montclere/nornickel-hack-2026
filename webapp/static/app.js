// Локальный UI: health-бейдж, drag-n-drop (файлы И ПАПКИ), сабмит.
(function () {
  // тип файла не режем на фронте — система сама решает, что парсить;
  // пропускаем только скрытые/служебные (.DS_Store и т.п.)
  const fileOk = n => { const b = n.split("/").pop(); return b && !b.startsWith("."); };

  // --- единая всплывающая подсказка: короткий текст + тонкая строка «подробнее» ---
  // (для HTML и SVG; мгновенная, не медленный нативный <title>; отсюда — клик по «?» ведёт в глоссарий)
  (function tooltips() {
    const tip = document.createElement("div");
    tip.id = "tooltip"; tip.hidden = true;
    document.body.appendChild(tip);
    let cur = null;
    const place = el => {
      const r = el.getBoundingClientRect();
      tip.style.left = Math.min(window.innerWidth - 12, Math.max(12, r.left + r.width / 2)) + "px";
      tip.style.top = (r.top - 10) + "px";
    };
    document.addEventListener("mouseover", e => {
      const el = e.target.closest && e.target.closest("[data-tip]");
      if (!el || el === cur) return;
      cur = el;
      const clickable = el.matches("a,button,.qmark") || !!el.closest("a,button");
      tip.innerHTML = `<span class="tt-main"></span>`
        + (clickable ? `<span class="tt-cta">Нажмите, чтобы узнать подробнее</span>` : "");
      tip.querySelector(".tt-main").textContent = el.getAttribute("data-tip");
      tip.hidden = false; place(el);
    });
    document.addEventListener("mouseout", e => {
      const el = e.target.closest && e.target.closest("[data-tip]");
      if (el && el === cur) { tip.hidden = true; cur = null; }
    });
    window.addEventListener("scroll", () => { tip.hidden = true; cur = null; }, true);
  })();

  // --- health ---
  const hEl = document.getElementById("health");
  if (hEl) {
    fetch("/health").then(r => r.json()).then(h => {
      const dot = (ok, name) =>
        `<span class="dot" title="${ok ? "доступен" : "недоступен"}">${name} <i class="${ok ? "ok" : "no"}"></i></span>`;
      hEl.innerHTML = dot(h.llm, "LLM") + dot(h.ocr, "OCR") + `<span class="dot">поиск: ${h.search_backend}</span>`;
      hEl.title = h.note;
      // контекстные предупреждения ПОД зонами (там, где сервис реально используется)
      const setSvc = (role, msg) => {
        const el = document.querySelector(`.dz-svc[data-svc="${role}"]`);
        if (el && msg) { el.textContent = msg; el.classList.add("show"); }
      };
      if (!h.ocr) setSvc("data", "OCR недоступен — сканы/схемы-картинки в данных не распознаются");
      const kw = [];
      if (!h.llm) kw.push("LLM недоступен — литература читаться не будет");
      if (!h.ocr) kw.push("OCR недоступен — сканы не распознаются");
      if (kw.length) setSvc("knowledge", kw.join(" · "));
    }).catch(() => { hEl.textContent = ""; });
  }

  // --- интерактивный граф ветки А (pan/zoom + подсветка соседей по клику) ---
  document.querySelectorAll(".panels .panel svg").forEach(initGraph);
  function initGraph(svg) {
    let vb = (svg.getAttribute("viewBox") || "0 0 900 400").split(/\s+/).map(Number);
    const base = vb.slice();
    const apply = () => svg.setAttribute("viewBox", vb.join(" "));
    const edges = [...svg.querySelectorAll(".gedge")], nodes = [...svg.querySelectorAll(".gnode")];
    const clearOn = () => [...edges, ...nodes].forEach(el => el.classList.remove("on"));
    const clear = () => { svg.classList.remove("hl"); clearOn(); };
    // кнопка сброса — иконкой в углу панели (обе панели: и граф, и кривая)
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
      if (!drag) return; const r = svg.getBoundingClientRect();
      vb[0] = drag.vb[0] - (e.clientX - drag.x) * vb[2] / r.width;
      vb[1] = drag.vb[1] - (e.clientY - drag.y) * vb[3] / r.height; apply();
    });
    svg.addEventListener("pointerup", () => { drag = null; svg.classList.remove("grab"); });
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

  // рекурсивно вычитать FileSystemEntry (файл или ПАПКА со всем содержимым)
  function readEntry(entry, out) {
    return new Promise(res => {
      if (entry.isFile) {
        entry.file(f => { if (fileOk(f.name)) out.push(f); res(); }, () => res());
      } else if (entry.isDirectory) {
        const reader = entry.createReader();
        const batch = () => reader.readEntries(async ents => {
          if (!ents.length) return res();
          for (const e of ents) await readEntry(e, out);
          batch();                              // readEntries отдаёт папку порциями
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
    else { for (const f of dt.files) if (fileOk(f.name)) out.push(f); }  // fallback
    return out;
  }

  document.querySelectorAll(".dz").forEach(dz => {
    const role = dz.dataset.role;
    const input = dz.querySelector(".dz-input");
    // список живёт ВНЕ зоны дропа: клики по нему физически не задевают зону —
    // удаление файла больше не открывает диалог выбора
    const list = document.querySelector(`.dz-list[data-list="${role}"]`);
    const render = () => {
      list.innerHTML = zoneFiles[role].map((f, i) =>
        `<li>${f.name}<button type="button" class="dz-x" data-i="${i}" title="убрать">×</button></li>`).join("")
        + (zoneFiles[role].length > 1
           ? `<li class="dz-tools"><button type="button" class="dz-clear">очистить все (${zoneFiles[role].length})</button></li>` : "");
    };
    const add = files => {
      const seen = new Set(zoneFiles[role].map(f => f.name + f.size));
      for (const f of files) if (fileOk(f.name) && !seen.has(f.name + f.size)) {
        zoneFiles[role].push(f); seen.add(f.name + f.size);
      }
      render();
    };
    dz.addEventListener("click", () => input.click());
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

  // --- сабмит ---
  const statusEl = document.getElementById("status");
  const go = document.getElementById("go");
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const kpi = document.getElementById("kpi").value.trim();
    if (!kpi) { statusEl.textContent = "укажите цель (KPI)"; statusEl.className = "status err"; return; }
    if (!zoneFiles.data.length && !zoneFiles.knowledge.length) {
      statusEl.textContent = "добавьте хотя бы один файл или папку";
      statusEl.className = "status err"; return;
    }
    const constraints = document.getElementById("constraints").value.trim();
    const fd = new FormData();
    fd.append("kpi", kpi);
    fd.append("constraints", constraints);        // отдельно — не сливаем в один промпт
    fd.append("web_search", document.getElementById("web_search").checked);
    fd.append("use_llm", document.getElementById("use_llm").checked);
    fd.append("max_chunks", document.getElementById("max_chunks").value || "14");
    zoneFiles.data.forEach(f => fd.append("data_files", f, f.name));
    zoneFiles.knowledge.forEach(f => fd.append("knowledge_files", f, f.name));

    go.disabled = true; statusEl.className = "status busy";
    statusEl.textContent = "загружаем файлы…";
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
