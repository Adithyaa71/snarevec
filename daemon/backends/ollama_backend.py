"""Ollama backend. Uses the native /api/embed endpoint (batched).

Note: ollama does NOT add nomic prefixes itself — the pipeline prepends
'search_document: ' before text reaches this backend, which is exactly what
parity requires.
"""
from __future__ import annotations

import httpx

from .base import EmbeddingBackend


class OllamaBackend(EmbeddingBackend):
    @property
    def base(self) -> str:
        return (self.cfg.base_url or "http://localhost:11434").rstrip("/")

    def embed(self, texts: list[str]) -> list[list[float]]:
        with httpx.Client(timeout=120) as client:
            r = client.post(
                f"{self.base}/api/embed",
                json={"model": self.cfg.model, "input": texts},
            )
            r.raise_for_status()
            data = r.json()
        vecs = [list(map(float, v)) for v in data.get("embeddings", [])]
        if len(vecs) != len(texts):
            raise RuntimeError(f"ollama returned {len(vecs)} embeddings for {len(texts)} inputs")
        self.check_dims(vecs)
        return vecs

    def health(self) -> tuple[bool, str]:
        try:
            with httpx.Client(timeout=5) as client:
                r = client.get(f"{self.base}/api/tags")
                r.raise_for_status()
                models = [m.get("name", "") for m in r.json().get("models", [])]
            want = self.cfg.model
            have = any(m == want or m.split(":")[0] == want.split(":")[0] for m in models)
            if not have:
                return False, f"ollama is running but model '{want}' is not pulled"
            return super().health()
        except httpx.ConnectError:
            return False, "ollama server is not running"
        except Exception as e:  # noqa: BLE001
            return False, str(e)
