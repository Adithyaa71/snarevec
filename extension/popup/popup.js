/* Popup flow:
   open → health check → load profiles → inject Readability into active tab
   → user picks profile + tags → Capture → animate the pipeline while the
   daemon chunks/embeds/stores → show result (or queued-for-retry on failure). */

const $ = (id) => document.getElementById(id);
const STAGES = ["extract", "chunk", "embed", "store"];
// packet position (percent) per stage on the 4-node track
const PACKET_POS = { extract: 0, chunk: 33.3, embed: 66.6, store: 100 };

let page = null;      // extraction result from content script
let profiles = [];
let tags = [];

document.addEventListener("DOMContentLoaded", init);

async function init() {
  $("openOptions1").onclick = $("openOptions2").onclick = () => chrome.runtime.openOptionsPage();
  $("queueLink").onclick = () => chrome.runtime.openOptionsPage(); // options opens; queue tab reachable there
  $("retryBtn").onclick = init;
  $("captureBtn").onclick = capture;
  wireTagInput();

  const h = await Snare.health();
  if (!h) return showOffline();

  setPill("ok", "daemon up");
  $("offline").classList.add("hidden");
  $("capturePanel").classList.remove("hidden");

  try {
    const cfg = await Snare.get("/config");
    profiles = cfg.profiles || [];
    renderProfiles(cfg);
    const queue = await Snare.get("/queue");
    const failed = queue.filter((q) => q.status === "failed").length;
    if (failed) { $("queueBadge").textContent = failed; $("queueBadge").classList.remove("hidden"); }
  } catch (e) {
    setPill("err", e.kind === "auth" ? "bad token" : "config error");
    toast(e.message, "err");
    return;
  }

  extractPage();
}

function showOffline() {
  setPill("err", "offline");
  $("offline").classList.remove("hidden");
  $("capturePanel").classList.add("hidden");
}

function setPill(state, text) {
  const pill = $("statusPill");
  pill.className = "pill " + (state === "ok" ? "pill-ok" : "pill-err");
  $("statusText").textContent = text;
}

function renderProfiles(cfg) {
  const sel = $("profileSelect");
  sel.innerHTML = "";
  if (!profiles.length) {
    const o = document.createElement("option");
    o.textContent = "No profiles — open Configure";
    sel.appendChild(o);
    $("captureBtn").disabled = true;
    return;
  }
  for (const p of profiles) {
    const o = document.createElement("option");
    o.value = p.id;
    o.textContent = p.name;
    sel.appendChild(o);
  }
  const update = () => {
    const p = profiles.find((x) => x.id === sel.value) || profiles[0];
    const b = (cfg.backends || []).find((x) => x.id === p.backend_id);
    const t = (cfg.targets || []).find((x) => x.id === p.target_id);
    $("profileSub").textContent =
      `→ ${p.collection || "?"} · ${b ? b.model.split("/").pop() : "no backend"} · ${t ? t.name : "no target"}`;
  };
  sel.onchange = update;
  chrome.storage.local.get({ lastProfile: "" }).then(({ lastProfile }) => {
    if (profiles.some((p) => p.id === lastProfile)) sel.value = lastProfile;
    update();
  });
}

async function extractPage() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !/^https?:/.test(tab.url || "")) {
      $("pageTitle").textContent = "This page can't be captured";
      $("pageDomain").textContent = "only http(s) pages";
      $("captureBtn").disabled = true;
      return;
    }
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["vendor/Readability.js", "content.js"],
    });
    // executeScript with files returns the last script's completion value
    page = result;
    if (!page || !page.ok) throw new Error((page && page.error) || "nothing readable on this page");
    $("pageTitle").textContent = page.title;
    $("pageDomain").textContent = new URL(page.url).hostname;
    $("pageWords").textContent = `${page.words.toLocaleString()} words${page.usedFallback ? " · raw" : ""}`;
    stage("extract", "done");
  } catch (e) {
    $("pageTitle").textContent = "Extraction failed";
    $("pageDomain").textContent = String(e.message || e);
    $("captureBtn").disabled = true;
  }
}

function wireTagInput() {
  const input = $("tagInput");
  $("chips").onclick = () => input.focus();
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && input.value.trim()) {
      addTag(input.value.trim().toLowerCase());
      input.value = "";
    } else if (ev.key === "Backspace" && !input.value && tags.length) {
      removeTag(tags[tags.length - 1]);
    }
  });
}

function addTag(t) {
  if (tags.includes(t)) return;
  tags.push(t);
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.dataset.tag = t;
  chip.innerHTML = `${escapeHtml(t)} <button title="remove">×</button>`;
  chip.querySelector("button").onclick = () => removeTag(t);
  $("chips").insertBefore(chip, $("tagInput"));
}

function removeTag(t) {
  tags = tags.filter((x) => x !== t);
  const el = document.querySelector(`.chip[data-tag="${CSS.escape(t)}"]`);
  if (el) el.remove();
}

/* ---------- pipeline animation ---------- */

function stage(name, state) {
  const el = document.querySelector(`.stage[data-stage="${name}"]`);
  if (!el) return;
  el.classList.remove("active", "done", "fail");
  if (state) el.classList.add(state);
  if (state === "active" || state === "done") {
    $("packet").style.left = PACKET_POS[name] + "%";
  }
}

function resetPipeline() {
  $("pipeline").classList.remove("hidden");
  $("result").classList.add("hidden");
  const packet = $("packet");
  packet.classList.remove("sink");
  packet.style.left = "0%";
  for (const s of STAGES) stage(s, null);
}

async function capture() {
  if (!page || !profiles.length) return;
  const btn = $("captureBtn");
  btn.classList.add("working");
  btn.querySelector(".btn-label").textContent = "Capturing…";
  resetPipeline();

  stage("extract", "done");
  await wait(250);
  stage("chunk", "active");

  const profileId = $("profileSelect").value;
  chrome.storage.local.set({ lastProfile: profileId });

  // The daemon does chunk+embed+store in one call; walk the middle stages on
  // a timer that keeps pace with reality (embed dominates), then land on the
  // response. Failure marks the stage we were visually on.
  const walker = setTimeout(() => { stage("chunk", "done"); stage("embed", "active"); }, 900);

  let res;
  try {
    res = await Snare.post("/capture", {
      profile_id: profileId,
      url: page.url,
      title: page.title,
      text: page.text,
      site_name: page.siteName || "",
      byline: page.byline || "",
      tags,
    });
  } catch (e) {
    clearTimeout(walker);
    failPipeline(String(e.message || e));
    finishBtn(btn);
    return;
  }
  clearTimeout(walker);

  if (!res.ok) {
    failPipeline(res.detail, res.queued);
    finishBtn(btn);
    return;
  }

  stage("chunk", "done");
  stage("embed", "active");
  await wait(350);
  stage("embed", "done");
  stage("store", "active");
  await wait(400);
  stage("store", "done");
  $("packet").classList.add("sink");

  const r = $("result");
  r.className = "result ok";
  r.innerHTML =
    `<div class="headline">Stored ${res.chunks} chunk${res.chunks === 1 ? "" : "s"} → ${escapeHtml(res.collection)}</div>` +
    `<div class="sub">${escapeHtml(res.target_name)} · ${res.dims}-dim · ${res.elapsed_ms}ms<br>${escapeHtml(res.detail)}</div>`;
  r.classList.remove("hidden");
  finishBtn(btn, "Capture again");
}

function failPipeline(message, queued) {
  const current = document.querySelector(".stage.active") || document.querySelector('.stage[data-stage="chunk"]');
  current.classList.remove("active");
  current.classList.add("fail");
  const r = $("result");
  r.className = "result err";
  r.innerHTML =
    `<div class="headline">${queued ? "Failed — saved to queue for retry" : "Capture failed"}</div>` +
    `<div class="sub">${escapeHtml(message)}</div>`;
  r.classList.remove("hidden");
}

function finishBtn(btn, label) {
  btn.classList.remove("working");
  btn.querySelector(".btn-label").textContent = label || "Capture this page";
}

/* ---------- utils ---------- */
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

let toastTimer;
function toast(msg, kind) {
  let t = document.querySelector(".toast");
  if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg;
  t.className = `toast show ${kind || ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
}
