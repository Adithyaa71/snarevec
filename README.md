# SnareVec

Capture any web page from your browser, embed it **locally on your machine**, and feed the vectors into your self-hosted RAG (Qdrant). Works with any Qdrant setup — server mode or embedded/path-mode.

```
┌─────────────┐   text    ┌──────────────────┐   vectors   ┌─────────────────┐
│  Extension   │──────────▶│  Companion daemon │────────────▶│  Storage target  │
│  (browser)   │  localhost│  (FastAPI, local) │             │  jsonl / ssh /   │
│  Readability │  + token  │  chunk → embed    │             │  qdrant server   │
└─────────────┘           └──────────────────┘             └─────────────────┘
                                                                    │ (staged files)
                                                                    ▼
                                                     remote-import/import_staged.py
                                                     → embedded Qdrant on a remote host
```

**Why a daemon?** Browsers sandbox extensions — they can't run embedding models, touch arbitrary paths, SSH anywhere, or install software. The extension handles capture + UI; the daemon does everything real. Your API keys and SSH credentials live only in the daemon's config file on disk, never in browser storage.

---

## 1. Install & run the daemon

Requires Python 3.10+.

```bash
cd daemon
pip install -r requirements.txt   # fastembed is the default local embedder (~250MB on first model load)
python main.py                    # or scripts/run-daemon.bat on Windows
```

On startup it prints:

```
  SnareVec daemon 0.1.0
  config : C:\Users\you\.snarevec\config.json
  listen : http://127.0.0.1:8756
  token  : Xy3f...   ← paste this into the extension
```

The daemon listens on **127.0.0.1 only**. Every request must carry that token (`X-Snarevec-Token` header) — this is what stops random web pages from poking your localhost.

First run writes a starter config: a fastembed backend (`nomic-embed-text-v1.5`, 768-dim), a local JSONL target, and a "General capture" profile. You can capture immediately.

### Optional: run the daemon automatically at login

By default you start the daemon manually each time (`python main.py`). If you'd rather it just be there whenever you open your browser, you can set it to launch silently at login instead — entirely your choice, nothing about the tool requires it.

**Windows:**
1. Create a small VBScript launcher next to the daemon, e.g. `scripts/run-daemon-hidden.vbs`:
   ```vbs
   Set WshShell = CreateObject("WScript.Shell")
   WshShell.CurrentDirectory = "C:\path\to\snarevec\daemon"
   WshShell.Run "python main.py", 0, False
   ```
2. Right-click it → **Create shortcut**.
3. Press `Win+R` → `shell:startup` → drop the shortcut in that folder.
4. Right-click the `.vbs` file itself → **Properties** → check **Unblock** if present (removes the "downloaded from the internet" warning that would otherwise pop up every login).

It'll now start invisibly every time you log in — check it's alive via Task Manager (look for `python.exe` under Background processes) or by hitting `http://127.0.0.1:8756/health` in a browser tab (no token needed for that one endpoint).

**macOS / Linux:** use a `launchd` plist or a `systemd --user` service pointing at `python3 main.py` in the `daemon/` folder — same idea, OS-native equivalent.

Prefer to start it manually each session instead? Totally fine — just run `python main.py` (or `scripts/run-daemon.bat` / `run-daemon.sh`) whenever you want to capture something.

## 2. Load the extension

Chrome / Edge / Brave (any Chromium, MV3):

1. `chrome://extensions` → enable **Developer mode**
2. **Load unpacked** → select the `extension/` folder
3. Click the SnareVec icon → **⚙ Configure** → **Daemon settings** tab
4. Paste the token, **Test connection**, **Save**

## 3. Capture

Open any article → click the icon → pick a profile → optional tags → **Capture this page**. Watch the pipeline: Extract → Chunk → Embed → Store. Failures aren't lost — they land in the **Queue** tab for retry.

## 4. Configure (options page)

- **Profiles** — backend + storage target + collection + chunking, bundled. The popup is just a profile dropdown. Profiles **lock after the first capture**: changing the model or chunking mid-collection corrupts search consistency, so the UI warns loudly.
- **Embedding backends** — where vectors are computed:
  | Kind | What it covers |
  |---|---|
  | `fastembed` | In-process, zero setup. Same model everywhere → **byte-compatible vectors across every machine you run it on**. |
  | `ollama` | Local ollama server. Built-in wizard: install (winget, Windows) → start → pull model. |
  | `openai_compatible` | LM Studio, llama.cpp server, vLLM, OpenAI, Together… anything with `/v1/embeddings`. |
  | `nomic_api` | Hosted twin of the default model — same vectors, no local compute. |
  | `hf_api` | HuggingFace Inference API. Fine for testing. |
- **Storage targets**:
  | Kind | When |
  |---|---|
  | `local_jsonl` | Staged files on this machine. Safest start. |
  | `sftp` | Stages locally, then pushes over SSH after every capture (pure-Python, no scp needed on Windows). |
  | `qdrant_http` | Direct upsert into a Qdrant **server**. Instant, no files. **Does not work for embedded/path-mode Qdrant** — that's single-process; use staged files + the import script. |

## 5. Getting vectors into an embedded-Qdrant remote host

```bash
# on the capture machine (or let the sftp target do this automatically)
rsync -av ~/.snarevec/staged/ user@remote-host:/home/user/staged_incoming/

# on the remote host — ⚠ your agent/service process must be FULLY STOPPED (embedded Qdrant is single-owner)
python3 remote-import/import_staged.py \
    --qdrant /path/to/qdrant_data \
    --staged ~/staged_incoming --delete-after
# restart your agent/service process
```

If your agent/service process is still running, opening the store fails — that failure is the safety net, don't work around it. The script validates every file's manifest (model, dims, prefix, chunking) against the destination collection and **refuses mismatches**. Re-importing the same file is idempotent: point IDs are `uuid5(url + chunk_index)`, so re-captures update instead of duplicating.

## The consistency rules (read once, save yourself a rebuilt collection)

1. **One model per collection, forever.** Vectors from different embedding models are mutually meaningless. The manifest system enforces this end to end.
2. **Same prefix, same chunking, both sides.** `search_document: ` prefixing happens centrally in the daemon pipeline, so every backend produces parity output. Chunking is fixed per profile.
3. **Keep `store_text` on.** Raw chunk text in the payload means you can always re-embed into a new collection if you ever switch models — and MMR/debugging needs it.
4. Backends serving the *same* model (fastembed vs ollama vs Nomic API `nomic-embed-text-v1.5`) produce near-identical vectors (cosine ≈ 1.0) and are safe to mix. Verify with each backend's **Test** button before trusting it.

## Known limitations

- **PDFs in the browser tab can't be captured** (Chrome's PDF viewer exposes no DOM to Readability). Save the file and ingest it with your existing document tooling instead.
- Ollama/LM Studio one-click install is **Windows-only** (winget); other OSes get the command to run.
- Paywalled or ToS-restricted content: what you capture is on you, not the tool.

## Repo layout

```
daemon/          FastAPI companion daemon (chunking, backends, targets, queue, installers)
extension/       MV3 extension (popup capture UI, options/config UI, Readability)
remote-import/   import_staged.py — staged JSONL → embedded Qdrant, manifest-validated
scripts/         run-daemon launchers
CLAUDE.md        onboarding doc for AI coding assistants working on this repo
```
