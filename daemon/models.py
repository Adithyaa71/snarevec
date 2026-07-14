"""SnareVec daemon — configuration and API schemas.

Everything the extension configures lives in these models. The config file on
disk is a serialized DaemonConfig. Secrets (API keys, SSH passwords) stay in
this file on the laptop and are never synced into extension storage.
"""
from __future__ import annotations

import secrets
import time
import uuid
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------
# Embedding backends
# --------------------------------------------------------------------------

BackendKind = Literal[
    "fastembed",          # in-process, zero setup (default)
    "ollama",             # local ollama server
    "openai_compatible",  # LM Studio, llama.cpp server, vLLM, OpenAI, anything /v1/embeddings
    "nomic_api",          # Nomic Atlas hosted API
    "hf_api",             # HuggingFace Inference API
]


class BackendConfig(BaseModel):
    id: str = Field(default_factory=_new_id)
    name: str = "Unnamed backend"
    kind: BackendKind = "fastembed"
    model: str = "nomic-ai/nomic-embed-text-v1.5"
    # For server-type backends:
    base_url: str = ""            # e.g. http://localhost:11434 or http://localhost:1234/v1
    api_key: str = ""             # provider key; stored daemon-side only
    # Expected vector size. Validated against the first real embedding.
    dims: int = 768
    # Extra provider options (e.g. truncate, batch size)
    options: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# Storage targets
# --------------------------------------------------------------------------

TargetKind = Literal[
    "local_jsonl",   # staged JSONL files on this machine
    "sftp",          # staged JSONL pushed to a remote path over SSH
    "qdrant_http",   # direct upsert into a Qdrant server (server mode only)
]


class TargetConfig(BaseModel):
    id: str = Field(default_factory=_new_id)
    name: str = "Unnamed target"
    kind: TargetKind = "local_jsonl"
    # local_jsonl + sftp
    path: str = ""                # local staging dir / remote dir for sftp
    # sftp
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""            # or use key_path
    key_path: str = ""            # path to private key file on the laptop
    keep_local_copy: bool = True  # sftp: also keep the staged file locally
    # qdrant_http
    url: str = ""                 # e.g. http://192.168.1.50:6333
    api_key: str = ""


# --------------------------------------------------------------------------
# Profiles — the unit the popup selects
# --------------------------------------------------------------------------

ChunkStrategy = Literal["fixed", "sentence", "semantic"]


class ChunkingConfig(BaseModel):
    strategy: ChunkStrategy = "fixed"
    chunk_size: int = 1200        # characters (fixed/sentence)
    chunk_overlap: int = 200      # characters, fixed strategy only
    semantic_threshold: float = 0.55  # cosine sim below this starts a new chunk


class ProfileConfig(BaseModel):
    id: str = Field(default_factory=_new_id)
    name: str = "New profile"
    backend_id: str = ""
    target_id: str = ""
    collection: str = ""          # Qdrant collection this feeds
    prefix: str = "search_document: "  # prepended to every chunk before embedding
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    store_text: bool = True       # keep raw chunk text in payload (recommended)
    default_tags: list[str] = Field(default_factory=list)
    locked: bool = False          # set true after first capture; chunking/model edits then warn


class DaemonSettings(BaseModel):
    port: int = 8756
    token: str = Field(default_factory=lambda: secrets.token_urlsafe(24))
    queue_dir: str = ""           # defaults to <config dir>/queue
    log_level: str = "info"


class DaemonConfig(BaseModel):
    settings: DaemonSettings = Field(default_factory=DaemonSettings)
    backends: list[BackendConfig] = Field(default_factory=list)
    targets: list[TargetConfig] = Field(default_factory=list)
    profiles: list[ProfileConfig] = Field(default_factory=list)

    def backend(self, backend_id: str) -> Optional[BackendConfig]:
        return next((b for b in self.backends if b.id == backend_id), None)

    def target(self, target_id: str) -> Optional[TargetConfig]:
        return next((t for t in self.targets if t.id == target_id), None)

    def profile(self, profile_id: str) -> Optional[ProfileConfig]:
        return next((p for p in self.profiles if p.id == profile_id), None)


# --------------------------------------------------------------------------
# API request/response bodies
# --------------------------------------------------------------------------

class CaptureRequest(BaseModel):
    profile_id: str
    url: str
    title: str = ""
    text: str
    tags: list[str] = Field(default_factory=list)
    site_name: str = ""
    byline: str = ""


class CaptureResult(BaseModel):
    ok: bool
    queued: bool = False
    queue_id: str = ""
    chunks: int = 0
    dims: int = 0
    collection: str = ""
    target_name: str = ""
    detail: str = ""
    elapsed_ms: int = 0


class TestResult(BaseModel):
    ok: bool
    detail: str = ""
    dims: int = 0
    latency_ms: int = 0


class QueueItem(BaseModel):
    id: str
    created_at: float = Field(default_factory=time.time)
    profile_id: str
    profile_name: str = ""
    url: str = ""
    title: str = ""
    status: Literal["pending", "failed", "done"] = "pending"
    error: str = ""
    attempts: int = 0
    chunks: int = 0
