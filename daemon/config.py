"""Config persistence. Lives at ~/.snarevec/config.json (override with
SNAREVEC_CONFIG env var). First run writes a starter config with a
fastembed backend and a local JSONL target so captures work out of the box.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from models import BackendConfig, DaemonConfig, ProfileConfig, TargetConfig

_LOCK = threading.Lock()


def config_dir() -> Path:
    override = os.environ.get("SNAREVEC_CONFIG")
    if override:
        return Path(override).expanduser().parent
    return Path.home() / ".snarevec"


def config_path() -> Path:
    override = os.environ.get("SNAREVEC_CONFIG")
    if override:
        return Path(override).expanduser()
    return config_dir() / "config.json"


def _starter_config() -> DaemonConfig:
    cfg = DaemonConfig()
    backend = BackendConfig(
        name="Local fastembed (default)",
        kind="fastembed",
        model="nomic-ai/nomic-embed-text-v1.5",
        dims=768,
    )
    staging = config_dir() / "staged"
    target = TargetConfig(name="Staged JSONL (this laptop)", kind="local_jsonl", path=str(staging))
    profile = ProfileConfig(
        name="General capture",
        backend_id=backend.id,
        target_id=target.id,
        collection="web_capture",
    )
    cfg.backends.append(backend)
    cfg.targets.append(target)
    cfg.profiles.append(profile)
    return cfg


def load() -> DaemonConfig:
    with _LOCK:
        p = config_path()
        if not p.exists():
            cfg = _starter_config()
            _write(cfg)
            return cfg
        data = json.loads(p.read_text(encoding="utf-8"))
        return DaemonConfig.model_validate(data)


def save(cfg: DaemonConfig) -> None:
    with _LOCK:
        _write(cfg)


def _write(cfg: DaemonConfig) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg.model_dump(), indent=2), encoding="utf-8")
    tmp.replace(p)  # atomic on the same filesystem


def queue_dir(cfg: DaemonConfig) -> Path:
    d = Path(cfg.settings.queue_dir) if cfg.settings.queue_dir else config_dir() / "queue"
    d.mkdir(parents=True, exist_ok=True)
    return d
