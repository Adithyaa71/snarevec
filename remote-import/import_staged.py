#!/usr/bin/env python3
"""Import SnareVec staged JSONL files into a remote host's EMBEDDED Qdrant.

⚠️  RUN ONLY WITH YOUR AGENT/SERVICE PROCESS FULLY STOPPED. Embedded
(path-mode) Qdrant is single-owner: this script takes the same file lock
your service uses. If that process is still running, opening the store
will fail — that failure is your safety net, do not work around it.

Usage:
    python3 import_staged.py --qdrant /path/to/qdrant_data \
                             --staged ~/staged_incoming [--delete-after] [--dry-run]

Behavior:
  * Reads every *.jsonl under --staged (recursively).
  * Validates each file's manifest (first line) before touching Qdrant:
      - collection exists  → vector size must match manifest dims, and the
        collection's stored manifest (sentinel point) must match model/prefix/
        chunking. Mismatch = file skipped loudly, nothing imported from it.
      - collection missing → created (cosine, manifest dims) + sentinel stored.
  * Upserts points in batches. Deterministic IDs mean re-importing the same
    file is idempotent — updates, never duplicates.
  * --delete-after removes successfully imported files; default keeps them
    and writes a .imported marker next to each.

Typical flow, capture machine → remote host:
    rsync -av ~/.snarevec/staged/ user@remote-host:/home/user/staged_incoming/
    ssh user@remote-host
    <stop your agent/service process>
    python3 import_staged.py --qdrant <path> --staged ~/staged_incoming --delete-after
    <restart your agent/service process>
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

BATCH = 128
SENTINEL_NS = uuid.UUID("c1a3c0de-0000-4000-8000-000000000001")
COMPAT_KEYS = ("model", "dims", "prefix", "chunking")


def log(msg: str) -> None:
    print(msg, flush=True)


def sentinel_id(collection: str) -> str:
    return str(uuid.uuid5(SENTINEL_NS, collection))


def load_manifest(path: Path) -> dict | None:
    with path.open("r", encoding="utf-8") as fh:
        line = fh.readline()
    if not line.strip():
        return None
    head = json.loads(line)
    return head if head.get("type") == "manifest" else None


def ensure_collection(client, manifest: dict) -> tuple[bool, str]:
    from qdrant_client import models as qm

    coll = manifest["collection"]
    sid = sentinel_id(coll)
    if not client.collection_exists(coll):
        client.create_collection(
            collection_name=coll,
            vectors_config=qm.VectorParams(size=manifest["dims"], distance=qm.Distance.COSINE),
        )
        client.upsert(
            collection_name=coll,
            points=[qm.PointStruct(id=sid, vector=[0.0] * manifest["dims"],
                                   payload={"_snarevec_manifest": manifest})],
        )
        return True, f"created collection '{coll}' ({manifest['dims']}-dim, cosine)"

    info = client.get_collection(coll)
    size = info.config.params.vectors.size
    if size != manifest["dims"]:
        return False, f"'{coll}' is {size}-dim, file is {manifest['dims']}-dim"
    got = client.retrieve(coll, ids=[sid], with_payload=True)
    if got:
        old = got[0].payload.get("_snarevec_manifest", {})
        for k in COMPAT_KEYS:
            if old.get(k) != manifest.get(k):
                return False, (f"'{coll}' was built with {k}={old.get(k)!r}, "
                               f"file uses {manifest.get(k)!r}")
    else:
        # pre-existing collection without a sentinel (e.g. made by another tool):
        # dims already matched, adopt it and store the manifest for next time
        client.upsert(
            collection_name=coll,
            points=[qm.PointStruct(id=sid, vector=[0.0] * manifest["dims"],
                                   payload={"_snarevec_manifest": manifest})],
        )
    return True, f"collection '{coll}' ok"


def import_file(client, path: Path, dry_run: bool) -> tuple[int, str]:
    from qdrant_client import models as qm

    manifest = load_manifest(path)
    if manifest is None:
        return 0, "no manifest header — skipped"

    ok, why = (True, "dry-run") if dry_run else ensure_collection(client, manifest)
    if not ok:
        return 0, f"REFUSED: {why}"

    coll = manifest["collection"]
    total = 0
    batch: list = []
    with path.open("r", encoding="utf-8") as fh:
        fh.readline()  # manifest
        for line in fh:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line)
            if len(p.get("vector", [])) != manifest["dims"]:
                return total, f"REFUSED at point {total}: vector dim {len(p.get('vector', []))} != {manifest['dims']}"
            if not dry_run:
                batch.append(qm.PointStruct(id=p["id"], vector=p["vector"], payload=p.get("payload", {})))
                if len(batch) >= BATCH:
                    client.upsert(collection_name=coll, points=batch)
                    batch = []
            total += 1
    if batch and not dry_run:
        client.upsert(collection_name=coll, points=batch)
    return total, f"→ '{coll}'"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qdrant", required=True, help="path to embedded qdrant data dir")
    ap.add_argument("--staged", required=True, help="dir containing staged *.jsonl (searched recursively)")
    ap.add_argument("--delete-after", action="store_true", help="delete files after successful import")
    ap.add_argument("--dry-run", action="store_true", help="validate + count only, write nothing")
    args = ap.parse_args()

    staged = Path(args.staged).expanduser()
    files = sorted(staged.rglob("*.jsonl"))
    if not files:
        log(f"nothing to import under {staged}")
        return 0

    client = None
    if not args.dry_run:
        try:
            from qdrant_client import QdrantClient
        except ImportError:
            log("qdrant-client not installed: pip install qdrant-client"); return 1
        try:
            client = QdrantClient(path=args.qdrant)
        except Exception as e:  # noqa: BLE001
            log(f"cannot open embedded qdrant at {args.qdrant}: {e}")
            log("→ is your agent/service process still running? Stop it first (single-owner file lock).")
            return 1

    failures = 0
    for f in files:
        if f.with_suffix(f.suffix + ".imported").exists() and not args.delete_after:
            log(f"skip (already imported): {f.name}")
            continue
        n, msg = import_file(client, f, args.dry_run)
        status = "OK " if not msg.startswith(("REFUSED", "no manifest")) else "!! "
        log(f"{status}{f.relative_to(staged)}: {n} points {msg}")
        if status == "!! ":
            failures += 1
            continue
        if not args.dry_run:
            if args.delete_after:
                f.unlink()
            else:
                f.with_suffix(f.suffix + ".imported").touch()

    if client is not None:
        client.close()
    log(f"done. {len(files)} file(s), {failures} refused/skipped.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
