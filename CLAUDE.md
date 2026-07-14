# CLAUDE.md — SnareVec

You are helping set up and extend **SnareVec**: a browser extension + local companion daemon that captures web pages, embeds them locally, and ships the vectors into a self-hosted RAG (Qdrant) — on this machine or a remote host.

## Your role

Setup assistant and maintainer for this repo. The code is complete and tested — your first job is getting it *running*, not rewriting it. Prefer minimal, surgical changes. Communication may be casual and via voice-to-text (expect transcription artifacts); prefer complete final code over incremental fragments, and ask before guessing on ambiguous requests.

## System context (the world around this repo)

- **Capture machine** — where this repo runs: the daemon + the browser extension. Any OS.
- **Remote host (optional)** — if your RAG runs elsewhere (e.g. a home server, a small board like a Raspberry Pi, a NAS), it may use **embedded (path-mode) Qdrant** — single-owner file lock, only ONE process may open `qdrant_data` at a time. This is why the capture machine can't write to it directly and why `remote-import/import_staged.py` must run **only with that host's agent/service process fully stopped**.
- If your embedding backend is `fastembed` with `nomic-embed-text-v1.5` (768-dim, `search_document: ` prefix — the default), vectors produced here are byte-compatible with any other host running the same model/library, so mixing capture machine and remote host is safe.

## Architecture (one paragraph)

Extension (MV3, vanilla JS, no build step) extracts page text with Readability.js and POSTs it to the daemon at `http://127.0.0.1:8756` with an `X-Snarevec-Token` header. The daemon (FastAPI) chunks → embeds (prefix applied centrally in `capture.py`, so all backends get identical input) → packages points with deterministic IDs `uuid5(POINT_NS, f"{url}#{chunk_index}")` → delivers to a storage target. Staged JSONL files carry a **manifest first line** (model/dims/prefix/chunking/collection); every append, upsert, and import validates it and refuses mismatches. Profiles bundle backend+target+collection and lock after first capture.

## File map

```
daemon/main.py          FastAPI routes + token middleware; run with `python main.py`
daemon/models.py        all pydantic schemas (config + API bodies)
daemon/config.py        ~/.snarevec/config.json load/save; starter config on first run
daemon/capture.py       the pipeline; POINT_NS lives here — NEVER change it
daemon/chunking.py      fixed / sentence / semantic strategies
daemon/backends/        fastembed, ollama, openai_compat (LM Studio/llama.cpp/vLLM/OpenAI), nomic_api, hf_api
daemon/targets/         local_jsonl (manifest logic), sftp (paramiko), qdrant_http (server-mode only)
daemon/queue_store.py   journal-before-process retry queue (one JSON per item)
daemon/installers.py    winget install/start/pull for ollama; LM Studio install
extension/manifest.json MV3; permissions: activeTab, scripting, storage; host: localhost
extension/content.js    Readability on cloned DOM + raw-text fallback
extension/shared/api.js Snare client (daemon URL + token from chrome.storage.local)
extension/popup/        capture UI with the 4-stage pipeline animation
extension/options/      Profiles / Backends / Targets / Queue / Settings tabs, ollama wizard
remote-import/import_staged.py  runs ON THE REMOTE HOST; validates manifests, idempotent upserts
```

## Setup tasks (in order)

1. `cd daemon && pip install -r requirements.txt` — if fastembed fails to build, install the rest and note it; API backends still work.
2. `python main.py` (or `scripts\run-daemon.bat`). Copy the printed token.
3. Load `extension/` unpacked at `chrome://extensions` (Developer mode).
4. Options → Daemon settings → paste token → Test connection.
5. Test capture on any article page with the default "General capture" profile; confirm a JSONL appears under `~/.snarevec/staged/web_capture/`.
6. When target collections are decided, create profiles accordingly (e.g. "Support docs KB" → collection `support_docs_kb`).
7. Optional: set the daemon to auto-start at login (see README's "run automatically at login" section) — not required, purely a convenience for whoever's running it.

## Gotchas / invariants — do not violate

- **`POINT_NS` and the sentinel namespace UUIDs are fixed forever.** Changing them orphans every previously staged point.
- **Never mix models/chunking within one collection.** The manifest checks exist to stop this; don't weaken them to "fix" a refused import — the refusal is correct.
- **Embedded Qdrant = single process.** Import script only with the destination's agent/service process stopped. The file-lock error when it's running is a feature.
- **Prefixing happens once**, in `capture.py`. Backends must NOT add their own (nomic_api strips-and-converts to `task_type` — that's intentional, it prevents double-prefixing).
- Secrets (API keys, SSH creds, token) live in `~/.snarevec/config.json` — gitignored. Never move them into extension storage.
- `qdrant_http` target is for **server-mode** Qdrant only; an embedded/path-mode store goes through staged files.
- Extension is deliberately buildless vanilla JS — don't introduce npm/bundlers.

## Testing

Daemon logic can be smoke-tested without a browser:
```bash
cd daemon
python -c "import chunking; from models import ChunkingConfig; print(chunking.run(ChunkingConfig(), 'test '*500))"
```
Full pipeline: start the daemon, then curl `/capture` with the token and a fake page body. `fastapi.testclient` works too. `remote-import` can be tested locally against a throwaway path (`--qdrant /tmp/qd --dry-run` first).

## Likely next features (ask before building)

- Background/context-menu capture without opening the popup
- PDF capture path (daemon downloads URL → extracts text)
- Additional targets (S3/WebDAV) or backends — follow the existing base-class patterns in `backends/base.py` / `targets/base.py`
- Deciding which collection browser captures should default to (open question)
