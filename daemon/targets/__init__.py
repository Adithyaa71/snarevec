from __future__ import annotations

from models import TargetConfig

from .base import StorageTarget
from .local_jsonl import LocalJsonlTarget
from .sftp_target import SftpTarget
from .qdrant_http import QdrantHttpTarget

_KINDS = {
    "local_jsonl": LocalJsonlTarget,
    "sftp": SftpTarget,
    "qdrant_http": QdrantHttpTarget,
}


def get_target(cfg: TargetConfig) -> StorageTarget:
    cls = _KINDS.get(cfg.kind)
    if cls is None:
        raise ValueError(f"unknown target kind: {cfg.kind}")
    return cls(cfg)
