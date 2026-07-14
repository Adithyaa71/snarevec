"""One-click local provider setup.

Honest scope: fully automated install + start + model pull for OLLAMA on
Windows (winget) / macOS+Linux (official script hint), and install for
LM STUDIO via winget. llama.cpp and everything else get a 'point me at your
server URL' path instead — auto-building llama.cpp per-GPU is a trap.

All steps are exposed individually so the extension can render a live
checklist: installed? → running? → model pulled? → ready.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import time

import httpx

OLLAMA_URL = "http://localhost:11434"


def _run(cmd: list[str], timeout: int = 900) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"{cmd[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


# ---------------------------------------------------------------- ollama ---

def ollama_status(model: str = "") -> dict:
    installed = shutil.which("ollama") is not None
    running, models = False, []
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        r.raise_for_status()
        running = True
        models = [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:  # noqa: BLE001
        pass
    has_model = bool(model) and any(
        m == model or m.split(":")[0] == model.split(":")[0] for m in models
    )
    return {
        "installed": installed,
        "running": running,
        "models": models,
        "has_model": has_model,
        "ready": installed and running and (has_model or not model),
    }


def ollama_install() -> dict:
    system = platform.system()
    if shutil.which("ollama"):
        return {"ok": True, "detail": "ollama already installed"}
    if system == "Windows":
        code, out = _run(
            ["winget", "install", "--id", "Ollama.Ollama", "-e",
             "--accept-source-agreements", "--accept-package-agreements"]
        )
        if code == 0:
            return {"ok": True, "detail": "installed via winget — a new terminal may be needed for PATH"}
        return {"ok": False, "detail": f"winget failed ({code}): {out[-400:]}"}
    # macOS / Linux: don't pipe curl|sh from a daemon — tell the user the command.
    return {
        "ok": False,
        "detail": "Automatic install is Windows-only. Run: curl -fsSL https://ollama.com/install.sh | sh "
                  "(Linux) or download from ollama.com (macOS), then click Start.",
    }


def ollama_start() -> dict:
    st = ollama_status()
    if st["running"]:
        return {"ok": True, "detail": "already running"}
    if not st["installed"]:
        return {"ok": False, "detail": "ollama is not installed"}
    creationflags = 0
    if platform.system() == "Windows":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    for _ in range(20):  # ~10s
        time.sleep(0.5)
        if ollama_status()["running"]:
            return {"ok": True, "detail": "server started"}
    return {"ok": False, "detail": "started process but server did not come up within 10s"}


def ollama_pull(model: str) -> dict:
    if not model:
        return {"ok": False, "detail": "no model name given"}
    code, out = _run(["ollama", "pull", model], timeout=3600)
    if code == 0:
        return {"ok": True, "detail": f"pulled {model}"}
    return {"ok": False, "detail": f"pull failed ({code}): {out[-400:]}"}


# ------------------------------------------------------------- lm studio ---

def lmstudio_status() -> dict:
    running = False
    try:
        r = httpx.get("http://localhost:1234/v1/models", timeout=3)
        running = r.status_code == 200
    except Exception:  # noqa: BLE001
        pass
    return {"running": running}


def lmstudio_install() -> dict:
    if platform.system() != "Windows":
        return {"ok": False, "detail": "Automatic install is Windows-only — download from lmstudio.ai"}
    code, out = _run(
        ["winget", "install", "--id", "ElementLabs.LMStudio", "-e",
         "--accept-source-agreements", "--accept-package-agreements"]
    )
    if code == 0:
        return {"ok": True, "detail": "installed — open LM Studio once, load a model, enable the local server"}
    return {"ok": False, "detail": f"winget failed ({code}): {out[-400:]}"}
