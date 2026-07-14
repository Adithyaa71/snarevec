"""Failed-capture queue. Every capture request is journaled to disk BEFORE
processing; success deletes the journal, failure keeps it with the error so
nothing is ever lost to a dead backend or an offline remote host. The extension's
Queue tab lists and retries these.

One JSON file per item: <queue dir>/<id>.json holding {meta, request}.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from models import CaptureRequest, DaemonConfig, QueueItem
import config as cfgmod


def _dir(cfg: DaemonConfig) -> Path:
    return cfgmod.queue_dir(cfg)


def journal(cfg: DaemonConfig, req: CaptureRequest) -> str:
    qid = uuid.uuid4().hex[:12]
    profile = cfg.profile(req.profile_id)
    item = QueueItem(
        id=qid,
        profile_id=req.profile_id,
        profile_name=profile.name if profile else "?",
        url=req.url,
        title=req.title,
        status="pending",
    )
    _write(cfg, qid, item, req)
    return qid


def mark_done(cfg: DaemonConfig, qid: str, chunks: int) -> None:
    # success = remove the journal; the staged file/collection is the record
    p = _dir(cfg) / f"{qid}.json"
    p.unlink(missing_ok=True)


def mark_failed(cfg: DaemonConfig, qid: str, error: str) -> None:
    item, req = read(cfg, qid)
    if item is None:
        return
    item.status = "failed"
    item.error = error[:500]
    item.attempts += 1
    _write(cfg, qid, item, req)


def read(cfg: DaemonConfig, qid: str) -> tuple[QueueItem | None, CaptureRequest | None]:
    p = _dir(cfg) / f"{qid}.json"
    if not p.exists():
        return None, None
    data = json.loads(p.read_text(encoding="utf-8"))
    return QueueItem.model_validate(data["meta"]), CaptureRequest.model_validate(data["request"])


def list_items(cfg: DaemonConfig) -> list[QueueItem]:
    items = []
    for p in sorted(_dir(cfg).glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            items.append(QueueItem.model_validate(data["meta"]))
        except Exception:  # noqa: BLE001 — a corrupt journal shouldn't kill the list
            continue
    items.sort(key=lambda i: i.created_at, reverse=True)
    return items


def delete(cfg: DaemonConfig, qid: str) -> None:
    (_dir(cfg) / f"{qid}.json").unlink(missing_ok=True)


def _write(cfg: DaemonConfig, qid: str, item: QueueItem, req: CaptureRequest | None) -> None:
    p = _dir(cfg) / f"{qid}.json"
    data = {"meta": item.model_dump(), "request": req.model_dump() if req else None}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
