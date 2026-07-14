"""OpenAI-compatible /v1/embeddings backend.

One backend covers: LM Studio (http://localhost:1234/v1), llama.cpp server
(http://localhost:8080/v1), vLLM, OpenAI itself (https://api.openai.com/v1),
Together, Fireworks, and anything else speaking the same dialect.
"""
from __future__ import annotations

import httpx

from .base import EmbeddingBackend


class OpenAICompatBackend(EmbeddingBackend):
    @property
    def base(self) -> str:
        b = (self.cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        return b if b.endswith("/v1") or "/v1/" in b else b + "/v1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        with httpx.Client(timeout=120) as client:
            r = client.post(
                f"{self.base}/embeddings",
                headers=headers,
                json={"model": self.cfg.model, "input": texts},
            )
            r.raise_for_status()
            data = r.json()
        rows = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
        vecs = [list(map(float, row["embedding"])) for row in rows]
        if len(vecs) != len(texts):
            raise RuntimeError(f"provider returned {len(vecs)} embeddings for {len(texts)} inputs")
        self.check_dims(vecs)
        return vecs
