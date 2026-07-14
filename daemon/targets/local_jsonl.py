"""Staged JSONL files on the laptop, one file per collection per day:
    <path>/<collection>/<collection>-YYYYMMDD.jsonl
First line of a new file is the manifest. Appends verify the existing
manifest matches (model, dims, prefix, chunking) before adding points.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from models import ProfileConfig

from .base import StorageTarget

_COMPAT_KEYS = ("model", "dims", "prefix", "chunking", "collection")


def manifest_compatible(a: dict, b: dict) -> tuple[bool, str]:
    for k in _COMPAT_KEYS:
        if a.get(k) != b.get(k):
            return False, f"manifest mismatch on '{k}': file has {a.get(k)!r}, capture has {b.get(k)!r}"
    return True, "ok"


class LocalJsonlTarget(StorageTarget):
    def _file_for(self, collection: str) -> Path:
        root = Path(self.cfg.path).expanduser()
        day = time.strftime("%Y%m%d")
        d = root / collection
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{collection}-{day}.jsonl"

    def write_staged(self, manifest: dict[str, Any], points: list[dict[str, Any]]) -> Path:
        f = self._file_for(manifest["collection"])
        if f.exists() and f.stat().st_size > 0:
            with f.open("r", encoding="utf-8") as fh:
                first = json.loads(fh.readline())
            if first.get("type") != "manifest":
                raise RuntimeError(f"{f} exists but has no manifest header — refusing to append")
            ok, why = manifest_compatible(first, manifest)
            if not ok:
                raise RuntimeError(f"refusing to append to {f.name}: {why}")
            mode = "a"
        else:
            mode = "w"
        with f.open(mode, encoding="utf-8") as fh:
            if mode == "w":
                fh.write(json.dumps(manifest, ensure_ascii=False) + "\n")
            for p in points:
                fh.write(json.dumps(p, ensure_ascii=False) + "\n")
        return f

    def deliver(self, manifest, points, profile: ProfileConfig) -> str:
        f = self.write_staged(manifest, points)
        return str(f)

    def test(self) -> tuple[bool, str]:
        try:
            root = Path(self.cfg.path).expanduser()
            root.mkdir(parents=True, exist_ok=True)
            probe = root / ".snarevec-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return True, f"writable: {root}"
        except Exception as e:  # noqa: BLE001
            return False, str(e)
