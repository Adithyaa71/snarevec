"""The capture pipeline. One function, four stages:

  chunk → embed (prefixed) → package points (deterministic IDs) → deliver

Deterministic IDs: uuid5(namespace, f"{url}#{chunk_index}") — re-capturing the
same page UPDATES its points instead of duplicating them. The namespace is
fixed forever; changing it would orphan every previously staged point.
"""
from __future__ import annotations

import time
import uuid
from urllib.parse import urlparse

from backends import get_backend
from chunking import run as run_chunking
from models import CaptureRequest, CaptureResult, DaemonConfig
from targets import get_target
from targets.base import build_manifest

# Fixed forever — see module docstring.
POINT_NS = uuid.UUID("5f0c9b6e-7c1a-5cba-9d3e-c1a3c0de2024")

EMBED_BATCH = 32


def point_id(url: str, chunk_index: int) -> str:
    return str(uuid.uuid5(POINT_NS, f"{url}#{chunk_index}"))


def run_capture(cfg: DaemonConfig, req: CaptureRequest) -> CaptureResult:
    t0 = time.monotonic()
    profile = cfg.profile(req.profile_id)
    if profile is None:
        raise ValueError(f"unknown profile: {req.profile_id}")
    backend_cfg = cfg.backend(profile.backend_id)
    target_cfg = cfg.target(profile.target_id)
    if backend_cfg is None:
        raise ValueError(f"profile '{profile.name}' has no valid backend configured")
    if target_cfg is None:
        raise ValueError(f"profile '{profile.name}' has no valid storage target configured")
    if not profile.collection:
        raise ValueError(f"profile '{profile.name}' has no collection name set")

    backend = get_backend(backend_cfg)
    target = get_target(target_cfg)

    # 1. chunk (semantic strategy borrows the backend for boundary detection)
    chunks = run_chunking(profile.chunking, req.text, embed_fn=backend.embed)
    if not chunks:
        raise ValueError("no text extracted — nothing to capture")

    # 2. embed with the profile prefix — the single place prefixing happens
    vectors: list[list[float]] = []
    prefixed = [f"{profile.prefix}{c}" for c in chunks]
    for i in range(0, len(prefixed), EMBED_BATCH):
        vectors.extend(backend.embed(prefixed[i : i + EMBED_BATCH]))

    # 3. package points
    captured_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    domain = urlparse(req.url).netloc
    tags = sorted(set(profile.default_tags) | set(req.tags))
    points = []
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        payload = {
            "url": req.url,
            "domain": domain,
            "title": req.title,
            "site_name": req.site_name,
            "byline": req.byline,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "tags": tags,
            "captured_at": captured_at,
            "source": "snarevec",
        }
        if profile.store_text:
            payload["text"] = chunk
        points.append({"id": point_id(req.url, i), "vector": vec, "payload": payload})

    # 4. deliver
    manifest = build_manifest(profile, backend_cfg)
    destination = target.deliver(manifest, points, profile)

    return CaptureResult(
        ok=True,
        chunks=len(points),
        dims=backend_cfg.dims,
        collection=profile.collection,
        target_name=target_cfg.name,
        detail=destination,
        elapsed_ms=int((time.monotonic() - t0) * 1000),
    )
