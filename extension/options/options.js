/* Options page: profiles / backends / targets / queue / settings.
   All data comes from GET /config on the daemon; edits go back via the CRUD
   routes. Editors expand inside their card; Test buttons run live checks. */

const $ = (id) => document.getElementById(id);
let cfg = { backends: [], targets: [], profiles: [] };

const KIND_LABELS = {
  fastembed: "fastembed · local",
  ollama: "ollama · local server",
  openai_compatible: "openai-compatible",
  nomic_api: "nomic atlas api",
  hf_api: "huggingface api",
  local_jsonl: "staged jsonl",
  sftp: "ssh / sftp",
  qdrant_http: "qdrant server",
};

const BACKEND_PRESETS = {
  fastembed: { model: "nomic-ai/nomic-embed-text-v1.5", dims: 768, base_url: "", api_key: "" },
  ollama: { model: "nomic-embed-text", dims: 768, base_url: "http://localhost:11434", api_key: "" },
  openai_compatible: { model: "text-embedding-nomic-embed-text-v1.5", dims: 768, base_url: "http://localhost:1234/v1", api_key: "" },
  nomic_api: { model: "nomic-embed-text-v1.5", dims: 768, base_url: "", api_key: "" },
  hf_api: { model: "nomic-ai/nomic-embed-text-v1.5", dims: 768, base_url: "", api_key: "" },
};

document.addEventListener("DOMContentLoaded", init);

async function init() {
  // nav
  document.querySelectorAll(".nav-item").forEach((b) => {
    b.onclick = () => switchTab(b.dataset.tab);
  });
  $("addProfile").onclick = () => openProfileEditor(null);
  $("addBackend").onclick = () => openBackendEditor(null);
  $("addTarget").onclick = () => openTargetEditor(null);
  $("refreshQueue").onclick = renderQueue;
  $("saveSettings").onclick = saveSettings;
  $("testConnection").onclick = testConnection;

  const s = await Snare.settings();
  $("daemonUrl").value = s.daemonUrl;
  $("daemonToken").value = s.token;

  await refreshAll();
}

async function refreshAll() {
  const h = await Snare.health();
  setPill(!!h, h ? "daemon up" : "daemon offline");
  if (!h) {
    toast("Daemon unreachable — check Settings tab", "err");
    switchTab("settings");
    return;
  }
  try {
    cfg = await Snare.get("/config");
  } catch (e) {
    setPill(false, e.kind === "auth" ? "bad token" : "error");
    toast(e.message, "err");
    switchTab("settings");
    return;
  }
  renderBackends();
  renderTargets();
  renderProfiles();
  renderQueue();
}

function switchTab(name) {
  document.querySelectorAll(".nav-item").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("hidden", t.id !== "tab-" + name));
}

function setPill(ok, text) {
  const pill = $("statusPill");
  pill.className = "pill " + (ok ? "pill-ok" : "pill-err");
  $("statusText").textContent = text;
}

/* ============================== BACKENDS ============================== */

function renderBackends() {
  const box = $("backendCards");
  box.innerHTML = "";
  if (!cfg.backends.length) {
    box.innerHTML = emptyState("No backends yet", "Add one — fastembed needs zero setup.");
    return;
  }
  for (const b of cfg.backends) {
    const card = el("div", "card");
    card.innerHTML = `
      <div class="card-row">
        <div>
          <div class="card-title">${esc(b.name)} <span class="kind-badge">${KIND_LABELS[b.kind] || b.kind}</span></div>
          <div class="card-sub">${esc(b.model)} · ${b.dims}-dim${b.base_url ? " · " + esc(b.base_url) : ""}</div>
        </div>
        <div class="card-actions">
          <button class="btn" data-act="test">Test</button>
          <button class="btn btn-ghost" data-act="edit">Edit</button>
          <button class="btn btn-danger" data-act="del">Delete</button>
        </div>
      </div>
      <div class="row-end hidden test-row"><span class="test-out mono"></span></div>`;
    card.querySelector('[data-act="test"]').onclick = (ev) =>
      runTest(ev.target, card, `/backends/${b.id}/test`);
    card.querySelector('[data-act="edit"]').onclick = () => openBackendEditor(b, card);
    card.querySelector('[data-act="del"]').onclick = () => delEntity(`/backends/${b.id}`, b.name);
    box.appendChild(card);
  }
}

function openBackendEditor(b, existingCard) {
  const isNew = !b;
  b = b || { name: "", kind: "fastembed", ...BACKEND_PRESETS.fastembed, options: {} };
  const card = editorCard(existingCard, $("backendCards"));

  const render = () => {
    const preset = BACKEND_PRESETS[b.kind] || {};
    card.innerHTML = `
      <div class="card-title">${isNew ? "New backend" : "Edit backend"}</div>
      <div class="editor">
        <div class="grid2">
          <label class="field"><span class="label">Name</span>
            <input type="text" data-k="name" value="${esc(b.name)}" placeholder="e.g. Local fastembed" /></label>
          <label class="field"><span class="label">Kind</span>
            <div class="select-wrap"><select data-k="kind">
              ${["fastembed","ollama","openai_compatible","nomic_api","hf_api"].map((k) =>
                `<option value="${k}" ${b.kind === k ? "selected" : ""}>${KIND_LABELS[k]}</option>`).join("")}
            </select><svg viewBox="0 0 12 8" class="chev"><path d="M1 1l5 5 5-5"/></svg></div></label>
        </div>
        ${kindHint(b.kind)}
        <div class="grid2">
          <label class="field"><span class="label">Model</span>
            <input type="text" data-k="model" value="${esc(b.model || preset.model || "")}" /></label>
          <label class="field"><span class="label">Dimensions</span>
            <input type="number" data-k="dims" value="${b.dims || preset.dims || 768}" /></label>
        </div>
        <div class="grid2">
          <label class="field ${["fastembed"].includes(b.kind) ? "hidden" : ""}"><span class="label">Base URL</span>
            <input type="text" data-k="base_url" value="${esc(b.base_url ?? preset.base_url ?? "")}"
              placeholder="${esc(preset.base_url || "https://…")}" /></label>
          <label class="field ${["fastembed","ollama"].includes(b.kind) ? "hidden" : ""}"><span class="label">API key</span>
            <input type="password" data-k="api_key" value="${esc(b.api_key || "")}" placeholder="stored on the daemon only" /></label>
        </div>
        <div class="wizard hidden" data-wizard></div>
        <div class="row-end">
          <span class="test-out mono"></span>
          <button class="btn" data-act="cancel">Cancel</button>
          <button class="btn btn-primary" data-act="save">${isNew ? "Add backend" : "Save changes"}</button>
        </div>
      </div>`;

    card.querySelector('[data-k="kind"]').onchange = (ev) => {
      collect(card, b);
      const k = ev.target.value;
      b.kind = k;
      Object.assign(b, { ...BACKEND_PRESETS[k] });
      render();
    };
    card.querySelector('[data-act="cancel"]').onclick = () => { card.remove(); renderBackends(); };
    card.querySelector('[data-act="save"]').onclick = async () => {
      collect(card, b);
      b.dims = parseInt(b.dims, 10) || 768;
      if (!b.name.trim()) return toast("Give the backend a name", "err");
      try {
        if (isNew) await Snare.post("/backends", b);
        else await Snare.put(`/backends/${b.id}`, b);
        toast(isNew ? "Backend added" : "Backend saved", "ok");
        await refreshAll();
      } catch (e) { toast(e.message, "err"); }
    };
    if (b.kind === "ollama") mountOllamaWizard(card, () => card.querySelector('[data-k="model"]').value);
    if (b.kind === "openai_compatible") mountLmStudioHint(card);
  };
  render();
}

function kindHint(kind) {
  const hints = {
    fastembed: "Runs inside the daemon — in-process, zero external setup. First use downloads the model (~250MB).",
    ollama: "Local ollama server. The wizard below can install, start it, and pull the model.",
    openai_compatible: "One backend for LM Studio, llama.cpp server, vLLM, OpenAI, Together… anything speaking /v1/embeddings.",
    nomic_api: "Hosted twin of the default local model — same vectors, no local compute. Needs a Nomic Atlas key.",
    hf_api: "HuggingFace serverless inference. Fine for testing; slow/rate-limited for bulk capture.",
  };
  return `<p class="hint">${hints[kind] || ""}</p>`;
}

/* ---- ollama wizard: installed → running → model pulled ---- */
async function mountOllamaWizard(card, getModel) {
  const box = card.querySelector("[data-wizard]");
  box.classList.remove("hidden");
  box.innerHTML = `<div class="wizard-title">Ollama quick setup</div><div class="wizard-body"><span class="spin"></span></div>`;
  const body = box.querySelector(".wizard-body");

  const refresh = async () => {
    let st;
    try {
      st = await Snare.get(`/installers/ollama/status?model=${encodeURIComponent(getModel())}`);
    } catch (e) { body.innerHTML = `<span class="test-out err">${esc(e.message)}</span>`; return; }
    body.innerHTML = "";
    body.appendChild(wstep("Installed", st.installed, "Install", async (btn) => {
      await wizardAction(btn, "/installers/ollama/install"); refresh();
    }));
    body.appendChild(wstep("Server running", st.running, "Start", async (btn) => {
      await wizardAction(btn, "/installers/ollama/start"); refresh();
    }, !st.installed));
    body.appendChild(wstep(`Model pulled (${esc(getModel())})`, st.has_model, "Pull", async (btn) => {
      btn.innerHTML = `<span class="spin"></span> pulling…`;
      await wizardAction(btn, "/installers/ollama/pull", { model: getModel() }); refresh();
    }, !st.running));
    if (st.ready) {
      const done = el("div", "wstep ok");
      done.innerHTML = `<div class="wicon"><div class="ring"></div></div><div class="wlabel">Ready — hit Test above to verify vectors.</div>`;
      body.appendChild(done);
    }
  };
  refresh();
}

function wstep(label, done, actionLabel, onAction, disabled) {
  const row = el("div", "wstep" + (done ? " ok" : ""));
  row.innerHTML = `<div class="wicon"><div class="ring"></div></div><div class="wlabel">${label}</div>`;
  if (!done) {
    const btn = el("button", "btn");
    btn.textContent = actionLabel;
    if (disabled) btn.disabled = true;
    btn.onclick = () => onAction(btn);
    row.appendChild(btn);
  }
  return row;
}

async function wizardAction(btn, path, body) {
  const old = btn.innerHTML;
  btn.innerHTML = `<span class="spin"></span>`;
  btn.disabled = true;
  try {
    const r = await Snare.post(path, body);
    toast(r.detail || "done", r.ok ? "ok" : "err");
  } catch (e) { toast(e.message, "err"); }
  btn.innerHTML = old;
  btn.disabled = false;
}

function mountLmStudioHint(card) {
  const box = card.querySelector("[data-wizard]");
  box.classList.remove("hidden");
  box.innerHTML = `<div class="wizard-title">LM Studio</div><div class="wizard-body"></div>`;
  const body = box.querySelector(".wizard-body");
  Snare.get("/installers/lmstudio/status").then((st) => {
    body.appendChild(wstep("Local server responding on :1234", st.running, "Install", async (btn) => {
      await wizardAction(btn, "/installers/lmstudio/install");
    }));
    if (!st.running) {
      const note = el("p", "hint");
      note.textContent = "After install: open LM Studio → load an embedding model → enable the local server, then Test.";
      body.appendChild(note);
    }
  }).catch(() => {});
}

/* ============================== TARGETS ============================== */

function renderTargets() {
  const box = $("targetCards");
  box.innerHTML = "";
  if (!cfg.targets.length) {
    box.innerHTML = emptyState("No storage targets", "Add one — staged JSONL is the safest start.");
    return;
  }
  for (const t of cfg.targets) {
    const sub = t.kind === "local_jsonl" ? t.path
      : t.kind === "sftp" ? `${t.username}@${t.host}:${t.path}`
      : t.url;
    const card = el("div", "card");
    card.innerHTML = `
      <div class="card-row">
        <div>
          <div class="card-title">${esc(t.name)} <span class="kind-badge warm">${KIND_LABELS[t.kind] || t.kind}</span></div>
          <div class="card-sub">${esc(sub || "")}</div>
        </div>
        <div class="card-actions">
          <button class="btn" data-act="test">Test</button>
          <button class="btn btn-ghost" data-act="edit">Edit</button>
          <button class="btn btn-danger" data-act="del">Delete</button>
        </div>
      </div>
      <div class="row-end hidden test-row"><span class="test-out mono"></span></div>`;
    card.querySelector('[data-act="test"]').onclick = (ev) =>
      runTest(ev.target, card, `/targets/${t.id}/test`);
    card.querySelector('[data-act="edit"]').onclick = () => openTargetEditor(t, card);
    card.querySelector('[data-act="del"]').onclick = () => delEntity(`/targets/${t.id}`, t.name);
    box.appendChild(card);
  }
}

function openTargetEditor(t, existingCard) {
  const isNew = !t;
  t = t || { name: "", kind: "local_jsonl", path: "", host: "", port: 22, username: "",
             password: "", key_path: "", keep_local_copy: true, url: "", api_key: "" };
  const card = editorCard(existingCard, $("targetCards"));

  const render = () => {
    card.innerHTML = `
      <div class="card-title">${isNew ? "New storage target" : "Edit storage target"}</div>
      <div class="editor">
        <div class="grid2">
          <label class="field"><span class="label">Name</span>
            <input type="text" data-k="name" value="${esc(t.name)}" placeholder="e.g. Remote host staging over SSH" /></label>
          <label class="field"><span class="label">Kind</span>
            <div class="select-wrap"><select data-k="kind">
              ${["local_jsonl","sftp","qdrant_http"].map((k) =>
                `<option value="${k}" ${t.kind === k ? "selected" : ""}>${KIND_LABELS[k]}</option>`).join("")}
            </select><svg viewBox="0 0 12 8" class="chev"><path d="M1 1l5 5 5-5"/></svg></div></label>
        </div>
        ${targetHint(t.kind)}
        ${t.kind === "local_jsonl" ? `
          <label class="field"><span class="label">Folder path (on the daemon machine)</span>
            <input type="text" data-k="path" value="${esc(t.path)}" placeholder="C:\\Users\\you\\.snarevec\\staged" /></label>` : ""}
        ${t.kind === "sftp" ? `
          <div class="grid3">
            <label class="field"><span class="label">Host</span><input type="text" data-k="host" value="${esc(t.host)}" placeholder="192.168.1.50" /></label>
            <label class="field"><span class="label">Port</span><input type="number" data-k="port" value="${t.port || 22}" /></label>
            <label class="field"><span class="label">Username</span><input type="text" data-k="username" value="${esc(t.username)}" placeholder="youruser" /></label>
          </div>
          <div class="grid2">
            <label class="field"><span class="label">Password <em class="dim">(or use a key)</em></span>
              <input type="password" data-k="password" value="${esc(t.password)}" /></label>
            <label class="field"><span class="label">Private key path</span>
              <input type="text" data-k="key_path" value="${esc(t.key_path)}" placeholder="C:\\Users\\you\\.ssh\\id_ed25519" /></label>
          </div>
          <label class="field"><span class="label">Remote folder</span>
            <input type="text" data-k="path" value="${esc(t.path)}" placeholder="/home/youruser/staged_incoming" /></label>
          <label class="toggle-field"><span class="toggle"><input type="checkbox" data-k="keep_local_copy" ${t.keep_local_copy ? "checked" : ""} /><span class="slider"></span></span>
            <span class="toggle-label">Keep a local copy after pushing</span></label>` : ""}
        ${t.kind === "qdrant_http" ? `
          <div class="grid2">
            <label class="field"><span class="label">Qdrant URL</span>
              <input type="text" data-k="url" value="${esc(t.url)}" placeholder="http://192.168.1.50:6333" /></label>
            <label class="field"><span class="label">API key <em class="dim">(if set)</em></span>
              <input type="password" data-k="api_key" value="${esc(t.api_key)}" /></label>
          </div>` : ""}
        <div class="row-end">
          <span class="test-out mono"></span>
          <button class="btn" data-act="cancel">Cancel</button>
          <button class="btn btn-primary" data-act="save">${isNew ? "Add target" : "Save changes"}</button>
        </div>
      </div>`;

    card.querySelector('[data-k="kind"]').onchange = (ev) => { collect(card, t); t.kind = ev.target.value; render(); };
    card.querySelector('[data-act="cancel"]').onclick = () => { card.remove(); renderTargets(); };
    card.querySelector('[data-act="save"]').onclick = async () => {
      collect(card, t);
      t.port = parseInt(t.port, 10) || 22;
      if (!t.name.trim()) return toast("Give the target a name", "err");
      try {
        if (isNew) await Snare.post("/targets", t);
        else await Snare.put(`/targets/${t.id}`, t);
        toast(isNew ? "Target added" : "Target saved", "ok");
        await refreshAll();
      } catch (e) { toast(e.message, "err"); }
    };
  };
  render();
}

function targetHint(kind) {
  const hints = {
    local_jsonl: "Vectors land as JSONL files (one folder per collection, manifest first line). Move them to your remote host with rsync/scp and run remote-import/import_staged.py.",
    sftp: "Stages locally, then pushes the file over SSH after every capture. Perfect for a remote host with embedded Qdrant — import script still runs on that host.",
    qdrant_http: "Writes straight into a Qdrant SERVER — instant, no files. Will NOT work for embedded/path-mode Qdrant.",
  };
  return `<p class="hint">${hints[kind] || ""}</p>`;
}

/* ============================== PROFILES ============================== */

function renderProfiles() {
  const box = $("profileCards");
  box.innerHTML = "";
  if (!cfg.profiles.length) {
    box.innerHTML = emptyState("No profiles", "A profile bundles backend + target + collection for one-click capture.");
    return;
  }
  for (const p of cfg.profiles) {
    const b = cfg.backends.find((x) => x.id === p.backend_id);
    const t = cfg.targets.find((x) => x.id === p.target_id);
    const card = el("div", "card");
    card.innerHTML = `
      <div class="card-row">
        <div>
          <div class="card-title">${esc(p.name)} <span class="kind-badge">${esc(p.collection || "no collection")}</span></div>
          <div class="card-sub">${b ? esc(b.name) : "⚠ backend missing"} → ${t ? esc(t.name) : "⚠ target missing"}
            · ${esc(p.chunking.strategy)} ${p.chunking.chunk_size} · ${p.store_text ? "text stored" : "vectors only"}</div>
          ${p.locked ? `<div class="lock-note">🔒 Locked after first capture — changing chunking or backend would corrupt this collection's consistency.</div>` : ""}
        </div>
        <div class="card-actions">
          <button class="btn btn-ghost" data-act="edit">Edit</button>
          <button class="btn btn-danger" data-act="del">Delete</button>
        </div>
      </div>`;
    card.querySelector('[data-act="edit"]').onclick = () => openProfileEditor(p, card);
    card.querySelector('[data-act="del"]').onclick = () => delEntity(`/profiles/${p.id}`, p.name);
    box.appendChild(card);
  }
}

function openProfileEditor(p, existingCard) {
  const isNew = !p;
  p = p ? JSON.parse(JSON.stringify(p)) : {
    name: "", backend_id: cfg.backends[0]?.id || "", target_id: cfg.targets[0]?.id || "",
    collection: "", prefix: "search_document: ",
    chunking: { strategy: "fixed", chunk_size: 1200, chunk_overlap: 200, semantic_threshold: 0.55 },
    store_text: true, default_tags: [], locked: false,
  };
  const card = editorCard(existingCard, $("profileCards"));

  const render = () => {
    card.innerHTML = `
      <div class="card-title">${isNew ? "New profile" : "Edit profile"}</div>
      ${p.locked ? `<div class="lock-note">🔒 This profile has captured data. Model/chunking edits below will make new
        captures incompatible with what's already in <b>${esc(p.collection)}</b> — only change them if you're re-building the collection.</div>` : ""}
      <div class="editor">
        <div class="grid2">
          <label class="field"><span class="label">Name</span>
            <input type="text" data-k="name" value="${esc(p.name)}" placeholder="e.g. Support docs KB" /></label>
          <label class="field"><span class="label">Collection</span>
            <input type="text" data-k="collection" value="${esc(p.collection)}" placeholder="e.g. support_docs_kb" /></label>
        </div>
        <div class="grid2">
          <label class="field"><span class="label">Embedding backend</span>
            <div class="select-wrap"><select data-k="backend_id">
              ${cfg.backends.map((b) => `<option value="${b.id}" ${p.backend_id === b.id ? "selected" : ""}>${esc(b.name)}</option>`).join("")}
            </select><svg viewBox="0 0 12 8" class="chev"><path d="M1 1l5 5 5-5"/></svg></div></label>
          <label class="field"><span class="label">Storage target</span>
            <div class="select-wrap"><select data-k="target_id">
              ${cfg.targets.map((t) => `<option value="${t.id}" ${p.target_id === t.id ? "selected" : ""}>${esc(t.name)}</option>`).join("")}
            </select><svg viewBox="0 0 12 8" class="chev"><path d="M1 1l5 5 5-5"/></svg></div></label>
        </div>
        <div class="grid3">
          <label class="field"><span class="label">Chunking</span>
            <div class="select-wrap"><select data-k="chunking.strategy">
              ${["fixed","sentence","semantic"].map((s) => `<option value="${s}" ${p.chunking.strategy === s ? "selected" : ""}>${s}</option>`).join("")}
            </select><svg viewBox="0 0 12 8" class="chev"><path d="M1 1l5 5 5-5"/></svg></div></label>
          <label class="field"><span class="label">Chunk size (chars)</span>
            <input type="number" data-k="chunking.chunk_size" value="${p.chunking.chunk_size}" /></label>
          <label class="field" data-overlap><span class="label">Overlap</span>
            <input type="number" data-k="chunking.chunk_overlap" value="${p.chunking.chunk_overlap}" /></label>
        </div>
        <p class="hint" data-chunkhint></p>
        <div class="grid2">
          <label class="field"><span class="label">Embedding prefix</span>
            <input type="text" data-k="prefix" value="${esc(p.prefix)}" /></label>
          <label class="field"><span class="label">Default tags <em class="dim">(comma separated)</em></span>
            <input type="text" data-k="default_tags" value="${esc((p.default_tags || []).join(", "))}" /></label>
        </div>
        <label class="toggle-field"><span class="toggle"><input type="checkbox" data-k="store_text" ${p.store_text ? "checked" : ""} /><span class="slider"></span></span>
          <span class="toggle-label">Store raw chunk text in the payload (recommended — enables re-embedding + MMR debugging)</span></label>
        <div class="row-end">
          <button class="btn" data-act="cancel">Cancel</button>
          <button class="btn btn-primary" data-act="save">${isNew ? "Create profile" : "Save profile"}</button>
        </div>
      </div>`;

    const hintEl = card.querySelector("[data-chunkhint]");
    const overlapField = card.querySelector("[data-overlap]");
    const chunkHints = {
      fixed: "Sliding window with overlap. The safe default.",
      sentence: "Whole sentences merged up to size. No mid-sentence cuts, no overlap.",
      semantic: "Splits where topic similarity drops (uses the backend per sentence — slower, often cleaner chunks).",
    };
    const updateChunkUi = () => {
      const s = card.querySelector('[data-k="chunking.strategy"]').value;
      hintEl.textContent = chunkHints[s];
      overlapField.style.opacity = s === "fixed" ? 1 : 0.35;
    };
    card.querySelector('[data-k="chunking.strategy"]').onchange = updateChunkUi;
    updateChunkUi();

    card.querySelector('[data-act="cancel"]').onclick = () => { card.remove(); renderProfiles(); };
    card.querySelector('[data-act="save"]').onclick = async () => {
      collect(card, p);
      p.chunking.chunk_size = parseInt(p.chunking.chunk_size, 10) || 1200;
      p.chunking.chunk_overlap = parseInt(p.chunking.chunk_overlap, 10) || 0;
      p.default_tags = String(p.default_tags || "").split(",").map((s) => s.trim()).filter(Boolean);
      if (!p.name.trim()) return toast("Give the profile a name", "err");
      if (!p.collection.trim()) return toast("Set a collection name", "err");
      if (!p.backend_id || !p.target_id) return toast("Profile needs a backend and a target", "err");
      try {
        if (isNew) await Snare.post("/profiles", p);
        else await Snare.put(`/profiles/${p.id}`, p);
        toast(isNew ? "Profile created" : "Profile saved", "ok");
        await refreshAll();
      } catch (e) { toast(e.message, "err"); }
    };
  };
  render();
}

/* ============================== QUEUE ============================== */

async function renderQueue() {
  const box = $("queueCards");
  let items = [];
  try { items = await Snare.get("/queue"); } catch (e) { box.innerHTML = emptyState("Queue unavailable", e.message); return; }
  const failed = items.filter((i) => i.status === "failed").length;
  const badge = $("queueBadge");
  badge.textContent = failed;
  badge.classList.toggle("hidden", !failed);

  box.innerHTML = "";
  if (!items.length) {
    box.innerHTML = emptyState("Queue is clear", "Failed captures land here for retry — nothing is ever silently dropped.");
    return;
  }
  for (const q of items) {
    const card = el("div", "card qcard");
    const when = new Date(q.created_at * 1000).toLocaleString();
    card.innerHTML = `
      <div class="card-row">
        <div>
          <div class="card-title">${esc(q.title || q.url)}</div>
          <div class="card-sub">${esc(q.profile_name)} · ${when} · ${q.attempts} attempt${q.attempts === 1 ? "" : "s"}</div>
          ${q.error ? `<div class="qerr">${esc(q.error)}</div>` : ""}
        </div>
        <div class="card-actions">
          <button class="btn" data-act="retry">Retry</button>
          <button class="btn btn-danger" data-act="del">Discard</button>
        </div>
      </div>`;
    card.querySelector('[data-act="retry"]').onclick = async (ev) => {
      const btn = ev.target;
      btn.innerHTML = `<span class="spin"></span>`;
      try {
        const r = await Snare.post(`/queue/${q.id}/retry`);
        toast(r.ok ? `Delivered ${r.chunks} chunks → ${r.collection}` : r.detail, r.ok ? "ok" : "err");
      } catch (e) { toast(e.message, "err"); }
      renderQueue();
    };
    card.querySelector('[data-act="del"]').onclick = async () => {
      await Snare.del(`/queue/${q.id}`);
      renderQueue();
    };
    box.appendChild(card);
  }
}

/* ============================== SETTINGS ============================== */

async function saveSettings() {
  await Snare.saveSettings({
    daemonUrl: $("daemonUrl").value.trim() || "http://127.0.0.1:8756",
    token: $("daemonToken").value.trim(),
  });
  toast("Settings saved", "ok");
  await refreshAll();
}

async function testConnection() {
  const out = $("settingsTestOut");
  out.className = "test-out mono";
  out.innerHTML = `<span class="spin"></span>`;
  await Snare.saveSettings({
    daemonUrl: $("daemonUrl").value.trim() || "http://127.0.0.1:8756",
    token: $("daemonToken").value.trim(),
  });
  const h = await Snare.health();
  if (!h) { out.textContent = "✗ daemon unreachable"; out.classList.add("err"); setPill(false, "daemon offline"); return; }
  try {
    await Snare.get("/config");
    out.textContent = `✓ connected — snarevec ${h.version}`;
    out.classList.add("ok");
    setPill(true, "daemon up");
    await refreshAll();
  } catch (e) {
    out.textContent = e.kind === "auth" ? "✗ reachable, but token rejected" : `✗ ${e.message}`;
    out.classList.add("err");
    setPill(false, e.kind === "auth" ? "bad token" : "error");
  }
}

/* ============================== helpers ============================== */

function el(tag, cls) { const e = document.createElement(tag); if (cls) e.className = cls; return e; }

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function emptyState(title, sub) {
  return `<div class="empty"><b>${esc(title)}</b>${esc(sub)}</div>`;
}

function editorCard(existingCard, container) {
  const card = el("div", "card editing");
  if (existingCard) existingCard.replaceWith(card);
  else container.prepend(card);
  return card;
}

// Collect [data-k] fields into obj; supports one level of nesting ("chunking.chunk_size")
function collect(card, obj) {
  card.querySelectorAll("[data-k]").forEach((input) => {
    const val = input.type === "checkbox" ? input.checked : input.value;
    const key = input.dataset.k;
    if (key.includes(".")) {
      const [a, b] = key.split(".");
      obj[a] = obj[a] || {};
      obj[a][b] = val;
    } else obj[key] = val;
  });
}

async function runTest(btn, card, path) {
  const row = card.querySelector(".test-row");
  const out = row.querySelector(".test-out");
  row.classList.remove("hidden");
  out.className = "test-out mono";
  out.innerHTML = `<span class="spin"></span> testing…`;
  btn.disabled = true;
  try {
    const r = await Snare.post(path);
    out.textContent = (r.ok ? "✓ " : "✗ ") + r.detail + (r.latency_ms ? ` (${r.latency_ms}ms)` : "");
    out.classList.add(r.ok ? "ok" : "err");
  } catch (e) {
    out.textContent = "✗ " + e.message;
    out.classList.add("err");
  }
  btn.disabled = false;
}

let toastTimer;
function toast(msg, kind) {
  const t = $("toast");
  t.textContent = msg;
  t.className = `toast show ${kind || ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
}
