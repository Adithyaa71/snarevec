from __future__ import annotations

import abc
import time
from typing import Any

from models import BackendConfig, ProfileConfig, TargetConfig

SCHEMA_VERSION = 1


def build_manifest(profile: ProfileConfig, backend: BackendConfig) -> dict[str, Any]:
    """First line of every staged JSONL file. The remote-import script validates
    this against the destination collection before upserting anything —
    it is the safety net against mixing incompatible vectors."""
    return {
        "type": "manifest",
        "schema_version": SCHEMA_VERSION,
        "created_by": "snarevec/0.1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "collection": profile.collection,
        "model": backend.model,
        "backend_kind": backend.kind,
        "dims": backend.dims,
        "prefix": profile.prefix,
        "chunking": profile.chunking.model_dump(),
    }


class StorageTarget(abc.ABC):
    def __init__(self, cfg: TargetConfig):
        self.cfg = cfg

    @abc.abstractmethod
    def deliver(
        self,
        manifest: dict[str, Any],
        points: list[dict[str, Any]],
        profile: ProfileConfig,
    ) -> str:
        """Persist points. Returns a human-readable destination string.
        Must raise on failure — the pipeline queues failed captures."""

    @abc.abstractmethod
    def test(self) -> tuple[bool, str]:
        """Connectivity/permission check without writing capture data."""
