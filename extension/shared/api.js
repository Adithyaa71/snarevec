// Shared daemon client. The daemon URL + token live in chrome.storage.local
// (set on the options → Settings tab). API keys and SSH secrets never live
// here — they stay in the daemon's config file on disk.
const Snare = (() => {
  const DEFAULTS = { daemonUrl: "http://127.0.0.1:8756", token: "" };

  async function settings() {
    const got = await chrome.storage.local.get(DEFAULTS);
    return { ...DEFAULTS, ...got };
  }

  async function saveSettings(patch) {
    await chrome.storage.local.set(patch);
  }

  async function call(method, path, body) {
    const { daemonUrl, token } = await settings();
    const res = await fetch(daemonUrl.replace(/\/$/, "") + path, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-Snarevec-Token": token,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 401) throw new SnareError("auth", "Daemon rejected the token — check Settings.");
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (_) { /* keep statusText */ }
      throw new SnareError("http", detail);
    }
    return res.json();
  }

  class SnareError extends Error {
    constructor(kind, message) { super(message); this.kind = kind; }
  }

  async function health() {
    const { daemonUrl } = await settings();
    try {
      const res = await fetch(daemonUrl.replace(/\/$/, "") + "/health", { signal: AbortSignal.timeout(2500) });
      return res.ok ? await res.json() : null;
    } catch (_) {
      return null;
    }
  }

  return {
    settings, saveSettings, health, SnareError,
    get: (p) => call("GET", p),
    post: (p, b) => call("POST", p, b ?? {}),
    put: (p, b) => call("PUT", p, b),
    del: (p) => call("DELETE", p),
  };
})();
