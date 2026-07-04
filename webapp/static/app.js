// Локальный UI: health-бейдж, drag-n-drop (файлы И ПАПКИ), сабмит.
(function () {
  // тип файла не режем на фронте — система сама решает, что парсить;
  // пропускаем только скрытые/служебные (.DS_Store и т.п.)
  const fileOk = n => { const b = n.split("/").pop(); return b && !b.startsWith("."); };

  // --- health ---
  const hEl = document.getElementById("health");
  if (hEl) {
    fetch("/health").then(r => r.json()).then(h => {
      const dot = (ok, name) =>
        `<span class="dot" title="${ok ? "доступен" : "недоступен"}">${name} <i class="${ok ? "ok" : "no"}"></i></span>`;
      hEl.innerHTML = dot(h.llm, "LLM") + dot(h.ocr, "OCR") + `<span class="dot">поиск: ${h.search_backend}</span>`;
      hEl.title = h.note;
      // распознавание сканов недоступно → честно предупредить в зоне схем
      const sw = document.getElementById("schemes-warn");
      if (sw && !h.ocr) sw.textContent =
        "распознавание сканов сейчас недоступно (нет ключа OCR) — схемы будут пропущены";
    }).catch(() => { hEl.textContent = ""; });
  }

  const form = document.getElementById("run-form");
  if (!form) return;
  const zoneFiles = { data: [], knowledge: [], schemes: [] };

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
    if (!zoneFiles.data.length && !zoneFiles.knowledge.length && !zoneFiles.schemes.length) {
      statusEl.textContent = "добавьте хотя бы один файл или папку";
      statusEl.className = "status err"; return;
    }
    const constraints = document.getElementById("constraints").value.trim();
    const fd = new FormData();
    fd.append("kpi", constraints ? `${kpi} ${constraints}` : kpi);
    fd.append("web_search", document.getElementById("web_search").checked);
    fd.append("use_llm", document.getElementById("use_llm").checked);
    fd.append("max_chunks", document.getElementById("max_chunks").value || "14");
    zoneFiles.data.forEach(f => fd.append("data_files", f, f.name));
    zoneFiles.knowledge.forEach(f => fd.append("knowledge_files", f, f.name));
    zoneFiles.schemes.forEach(f => fd.append("schemes_files", f, f.name));

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
