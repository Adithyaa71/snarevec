"""Direct upsert into a Qdrant SERVER over HTTP — the zero-file path for
people running Qdrant in server mode. (An embedded/path-mode Qdrant setup
cannot accept remote writes this way; use local_jsonl or sftp instead and
import with remote-import/import_staged.py.)

Creates the collection on first use (cosine, dims from the manifest) and
stores the manifest in a sentinel point payload so later captures with a
different model/chunking are refused instead of silently mixed.
"""
from __future__ import annotations

import uuid
from typing import Any

from models import ProfileConfig

from .base import StorageTarget

_SENTINEL_NS = uuid.UUID("c1a3c0de-0000-4000-8000-000000000001")
_COMPAT_KEYS = ("model", "dims", "prefix", "chunking")


class QdrantHttpTarget(StorageTarget):
    def _client(self):
        try:
            from qdrant_client import QdrantClient
        except ImportError as e:
            raise RuntimeError("qdrant-client is not installed. Run: pip install qdrant-client") from e
        return QdrantClient(url=self.cfg.url, api_key=self.cfg.api_key or None, timeout=30)

    def deliver(self, manifest: dict[str, Any], points: list[dict[str, Any]], profile: ProfileConfig) -> str:
        from qdrant_client import models as qm

        client = self._client()
        coll = manifest["collection"]
        sentinel_id = str(uuid.uuid5(_SENTINEL_NS, coll))

        if not client.collection_exists(coll):
            client.create_collection(
                collection_name=coll,
                vectors_config=qm.VectorParams(size=manifest["dims"], distance=qm.Distance.COSINE),
            )
            client.upsert(
                collection_name=coll,
                points=[qm.PointStruct(
                    id=sentinel_id,
                    vector=[0.0] * manifest["dims"],
                    payload={"_snarevec_manifest": manifest},
                )],
            )
        else:
            info = client.get_collection(coll)
            size = info.config.params.vectors.size
            if size != manifest["dims"]:
                raise RuntimeError(
                    f"collection '{coll}' is {size}-dim but this profile produces "
                    f"{manifest['dims']}-dim vectors — refusing to upsert"
                )
            got = client.retrieve(coll, ids=[sentinel_id], with_payload=True)
            if got:
                old = got[0].payload.get("_snarevec_manifest", {})
                for k in _COMPAT_KEYS:
                    if old.get(k) != manifest.get(k):
                        raise RuntimeError(
                            f"collection '{coll}' was built with {k}={old.get(k)!r}, "
                            f"this profile uses {manifest.get(k)!r} — refusing to mix"
                        )

        client.upsert(
            collection_name=coll,
            points=[qm.PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"]) for p in points],
        )
        return f"{self.cfg.url} → {coll} ({len(points)} points)"

    def test(self) -> tuple[bool, str]:
        try:
            client = self._client()
            colls = [c.name for c in client.get_collections().collections]
            return True, f"connected, {len(colls)} collection(s): {', '.join(colls[:8]) or 'none yet'}"
        except Exception as e:  # noqa: BLE001
            return False, str(e)
