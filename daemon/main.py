"""SnareVec companion daemon.

Run:  python main.py        (or scripts/run-daemon.bat on Windows)
Listens on 127.0.0.1 only. Every route except /health requires the shared
token (X-Snarevec-Token header) printed at startup and stored in config.json —
this is what stops random web pages from poking the daemon via localhost.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config as cfgmod
import installers
import queue_store
from backends import get_backend
from capture import run_capture
from models import (
    BackendConfig, CaptureRequest, CaptureResult, DaemonConfig,
    ProfileConfig, TargetConfig, TestResult,
)
from targets import get_target

VERSION = "0.1.0"

app = FastAPI(title="SnareVec daemon", version=VERSION)

# CORS is open because auth is the token, not the origin — extension IDs vary
# per install and non-browser clients ignore CORS anyway.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def token_guard(request: Request, call_next):
    if request.url.path == "/health" or request.method == "OPTIONS":
        return await call_next(request)
    cfg = cfgmod.load()
    if request.headers.get("x-snarevec-token") != cfg.settings.token:
        return JSONResponse({"detail": "missing or invalid X-Snarevec-Token"}, status_code=401)
    return await call_next(request)


# ------------------------------------------------------------------ meta ---

@app.get("/health")
def health():
    return {"ok": True, "app": "snarevec", "version": VERSION}


@app.get("/config")
def get_config():
    cfg = cfgmod.load()
    return cfg.model_dump()


@app.put("/settings")
def put_settings(body: dict):
    cfg = cfgmod.load()
    for k in ("port", "queue_dir", "log_level"):
        if k in body:
            setattr(cfg.settings, k, body[k])
    cfgmod.save(cfg)
    return {"ok": True}


# -------------------------------------------------------------- backends ---

@app.post("/backends")
def add_backend(body: BackendConfig):
    cfg = cfgmod.load()
    cfg.backends.append(body)
    cfgmod.save(cfg)
    return body


@app.put("/backends/{bid}")
def update_backend(bid: str, body: BackendConfig):
    cfg = cfgmod.load()
    for i, b in enumerate(cfg.backends):
        if b.id == bid:
            body.id = bid
            cfg.backends[i] = body
            cfgmod.save(cfg)
            return body
    raise HTTPException(404, "backend not found")


@app.delete("/backends/{bid}")
def delete_backend(bid: str):
    cfg = cfgmod.load()
    used_by = [p.name for p in cfg.profiles if p.backend_id == bid]
    if used_by:
        raise HTTPException(409, f"backend is used by profile(s): {', '.join(used_by)}")
    cfg.backends = [b for b in cfg.backends if b.id != bid]
    cfgmod.save(cfg)
    return {"ok": True}


@app.post("/backends/{bid}/test")
def test_backend(bid: str) -> TestResult:
    import time
    cfg = cfgmod.load()
    b = cfg.backend(bid)
    if b is None:
        raise HTTPException(404, "backend not found")
    t0 = time.monotonic()
    ok, detail = get_backend(b).health()
    return TestResult(ok=ok, detail=detail, dims=b.dims, latency_ms=int((time.monotonic() - t0) * 1000))


# --------------------------------------------------------------- targets ---

@app.post("/targets")
def add_target(body: TargetConfig):
    cfg = cfgmod.load()
    cfg.targets.append(body)
    cfgmod.save(cfg)
    return body


@app.put("/targets/{tid}")
def update_target(tid: str, body: TargetConfig):
    cfg = cfgmod.load()
    for i, t in enumerate(cfg.targets):
        if t.id == tid:
            body.id = tid
            cfg.targets[i] = body
            cfgmod.save(cfg)
            return body
    raise HTTPException(404, "target not found")


@app.delete("/targets/{tid}")
def delete_target(tid: str):
    cfg = cfgmod.load()
    used_by = [p.name for p in cfg.profiles if p.target_id == tid]
    if used_by:
        raise HTTPException(409, f"target is used by profile(s): {', '.join(used_by)}")
    cfg.targets = [t for t in cfg.targets if t.id != tid]
    cfgmod.save(cfg)
    return {"ok": True}


@app.post("/targets/{tid}/test")
def test_target(tid: str) -> TestResult:
    import time
    cfg = cfgmod.load()
    t = cfg.target(tid)
    if t is None:
        raise HTTPException(404, "target not found")
    t0 = time.monotonic()
    ok, detail = get_target(t).test()
    return TestResult(ok=ok, detail=detail, latency_ms=int((time.monotonic() - t0) * 1000))


# -------------------------------------------------------------- profiles ---

@app.post("/profiles")
def add_profile(body: ProfileConfig):
    cfg = cfgmod.load()
    cfg.profiles.append(body)
    cfgmod.save(cfg)
    return body


@app.put("/profiles/{pid}")
def update_profile(pid: str, body: ProfileConfig):
    cfg = cfgmod.load()
    for i, p in enumerate(cfg.profiles):
        if p.id == pid:
            body.id = pid
            cfg.profiles[i] = body
            cfgmod.save(cfg)
            return body
    raise HTTPException(404, "profile not found")


@app.delete("/profiles/{pid}")
def delete_profile(pid: str):
    cfg = cfgmod.load()
    cfg.profiles = [p for p in cfg.profiles if p.id != pid]
    cfgmod.save(cfg)
    return {"ok": True}


# --------------------------------------------------------------- capture ---

@app.post("/capture")
def capture(req: CaptureRequest) -> CaptureResult:
    cfg = cfgmod.load()
    qid = queue_store.journal(cfg, req)
    try:
        result = run_capture(cfg, req)
    except Exception as e:  # noqa: BLE001
        queue_store.mark_failed(cfg, qid, str(e))
        return CaptureResult(ok=False, queued=True, queue_id=qid, detail=str(e))
    queue_store.mark_done(cfg, qid, result.chunks)
    # lock the profile after first successful capture (UI warns on later edits)
    profile = cfg.profile(req.profile_id)
    if profile and not profile.locked:
        profile.locked = True
        cfgmod.save(cfg)
    return result


# ----------------------------------------------------------------- queue ---

@app.get("/queue")
def get_queue():
    cfg = cfgmod.load()
    return [i.model_dump() for i in queue_store.list_items(cfg)]


@app.post("/queue/{qid}/retry")
def retry_queue(qid: str) -> CaptureResult:
    cfg = cfgmod.load()
    _, req = queue_store.read(cfg, qid)
    if req is None:
        raise HTTPException(404, "queue item not found")
    try:
        result = run_capture(cfg, req)
    except Exception as e:  # noqa: BLE001
        queue_store.mark_failed(cfg, qid, str(e))
        return CaptureResult(ok=False, queued=True, queue_id=qid, detail=str(e))
    queue_store.mark_done(cfg, qid, result.chunks)
    return result


@app.delete("/queue/{qid}")
def delete_queue(qid: str):
    cfg = cfgmod.load()
    queue_store.delete(cfg, qid)
    return {"ok": True}


# ------------------------------------------------------------ installers ---

@app.get("/installers/ollama/status")
def ollama_status(model: str = ""):
    return installers.ollama_status(model)


@app.post("/installers/ollama/install")
def ollama_install():
    return installers.ollama_install()


@app.post("/installers/ollama/start")
def ollama_start():
    return installers.ollama_start()


@app.post("/installers/ollama/pull")
def ollama_pull(body: dict):
    return installers.ollama_pull(body.get("model", ""))


@app.get("/installers/lmstudio/status")
def lmstudio_status():
    return installers.lmstudio_status()


@app.post("/installers/lmstudio/install")
def lmstudio_install():
    return installers.lmstudio_install()


# ------------------------------------------------------------------- run ---

if __name__ == "__main__":
    import uvicorn

    cfg = cfgmod.load()
    print()
    print("  SnareVec daemon", VERSION)
    print(f"  config : {cfgmod.config_path()}")
    print(f"  listen : http://127.0.0.1:{cfg.settings.port}")
    print(f"  token  : {cfg.settings.token}")
    print("  → paste this token into the extension's Settings tab")
    print()
    uvicorn.run(app, host="127.0.0.1", port=cfg.settings.port, log_level=cfg.settings.log_level)
