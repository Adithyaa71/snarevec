"""HuggingFace Inference API backend (feature-extraction pipeline).

Works with hosted serverless inference or a dedicated HF endpoint via base_url.
"""
from __future__ import annotations

import httpx

from .base import EmbeddingBackend


class HfApiBackend(EmbeddingBackend):
    @property
    def url(self) -> str:
        if self.cfg.base_url:
            return self.cfg.base_url.rstrip("/")
        return f"https://api-inference.huggingface.co/models/{self.cfg.model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}
        with httpx.Client(timeout=120) as client:
            r = client.post(
                self.url,
                headers=headers,
                json={"inputs": texts, "options": {"wait_for_model": True}},
            )
            r.raise_for_status()
            data = r.json()
        # Serverless returns [[...vec], ...]; some endpoints return token-level
        # [[tokens][dims]] — mean-pool if we detect 3 levels of nesting.
        if data and isinstance(data[0], list) and data[0] and isinstance(data[0][0], list):
            pooled = []
            for tokens in data:
                n = len(tokens)
                pooled.append([sum(col) / n for col in zip(*tokens)])
            data = pooled
        vecs = [list(map(float, v)) for v in data]
        if len(vecs) != len(texts):
            raise RuntimeError(f"HF returned {len(vecs)} embeddings for {len(texts)} inputs")
        self.check_dims(vecs)
        return vecs
