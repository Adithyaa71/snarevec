"""Nomic Atlas hosted API — serves the same nomic-embed-text-v1.5 as fastembed,
which makes it the natural 'remote' twin of the default local backend.

Nomic's API takes task_type instead of inline prefixes. The pipeline prefixes
text with 'search_document: ' for every backend; Nomic treats an explicit
prefix + task_type as double-prefixing, so this backend STRIPS the pipeline
prefix and passes task_type=search_document instead. Net result: identical
vectors, one code path in the pipeline.
"""
from __future__ import annotations

import httpx

from .base import EmbeddingBackend

_PREFIXES = ("search_document: ", "search_query: ", "classification: ", "clustering: ")


class NomicApiBackend(EmbeddingBackend):
    def embed(self, texts: list[str]) -> list[list[float]]:
        task = "search_document"
        cleaned = []
        for t in texts:
            for p in _PREFIXES:
                if t.startswith(p):
                    task = p.rstrip(": ").strip()
                    t = t[len(p):]
                    break
            cleaned.append(t)
        with httpx.Client(timeout=120) as client:
            r = client.post(
                "https://api-atlas.nomic.ai/v1/embedding/text",
                headers={"Authorization": f"Bearer {self.cfg.api_key}"},
                json={
                    "model": self.cfg.model or "nomic-embed-text-v1.5",
                    "texts": cleaned,
                    "task_type": task,
                    "dimensionality": self.cfg.dims or 768,
                },
            )
            r.raise_for_status()
            data = r.json()
        vecs = [list(map(float, v)) for v in data.get("embeddings", [])]
        if len(vecs) != len(texts):
            raise RuntimeError(f"nomic returned {len(vecs)} embeddings for {len(texts)} inputs")
        self.check_dims(vecs)
        return vecs
