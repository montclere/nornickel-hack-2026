// Локальный UI: health-бейдж, drag-n-drop (файлы И ПАПКИ из файловой системы), сабмит.
(function () {
  const ALLOWED = new Set(["xlsx", "csv", "pdf", "docx", "txt", "md",
    "png", "jpg", "jpeg", "tif", "tiff", "webp", "bmp"]);
  const extOk = n => { const i = n.lastIndexOf("."); return i >= 0 && ALLOWED.has(n.slice(i + 1).toLowerCase()); };

  // --- health ---
  const hEl = document.getElementById("health");
  if (hEl) {
    fetch("/health").then(r => r.json()).then(h => {
      const dot = (ok, name) =>
        `<span class="dot" title="${ok ? "доступен" : "недоступен"}">${name} <i class="${ok ? "ok" : "no"}"></i></span>`;
      hEl.innerHTML = dot(h.llm, "LLM") + dot(h.ocr, "OCR") + `<span class="dot">поиск: ${h.search_backend}</span>`;
      hEl.title = h.note;
    }).catch(() => { hEl.textContent = ""; });
  }

  const form = document.getElementById("run-form");
  if (!form) return;
  const zoneFiles = { data: [], knowledge: [] };

  // рекурсивно вычитать FileSystemEntry (файл или ПАПКА со всем содержимым)
  function readEntry(entry, out) {
    return new Promise(res => {
      if (entry.isFile) {
        entry.file(f => { if (extOk(f.name)) out.push(f); res(); }, () => res());
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
    else { for (const f of dt.files) if (extOk(f.name)) out.push(f); }  // fallback
    return out;
  }

  document.querySelectorAll(".dz").forEach(dz => {
    const role = dz.dataset.role;
    const input = dz.querySelector(".dz-input");
    const list = dz.querySelector(".dz-list");
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
    // клик по зоне → диалог выбора; клики по списку/кнопкам не открывают диалог
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
    fd.append("kpi", constraints ? `${kpi} ${constraints}` : kpi);
    fd.append("dossier", document.getElementById("dossier").checked);
    fd.append("web", document.getElementById("web").checked);
    zoneFiles.data.forEach(f => fd.append("data_files", f, f.name));
    zoneFiles.knowledge.forEach(f => fd.append("knowledge_files", f, f.name));

    go.disabled = true; statusEl.className = "status busy";
    statusEl.textContent = "анализируем данные — может занять пару минут…";
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
