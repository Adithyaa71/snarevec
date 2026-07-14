"""In-process fastembed backend — a common local embedding stack,
so vectors staged here are byte-compatible with any other host running the same model.

fastembed is an optional heavy dependency (pulls ONNX runtime + model weights
on first use); import lazily so the daemon starts without it when the user
only uses API backends.
"""
from __future__ import annotations

import threading

from .base import EmbeddingBackend

_model_lock = threading.Lock()
_models: dict[str, object] = {}


class FastembedBackend(EmbeddingBackend):
    def _model(self):
        name = self.cfg.model
        with _model_lock:
            m = _models.get(name)
            if m is None:
                try:
                    from fastembed import TextEmbedding
                except ImportError as e:
                    raise RuntimeError(
                        "fastembed is not installed. Run: pip install fastembed "
                        "(or switch this backend to ollama / an API provider)"
                    ) from e
                m = TextEmbedding(model_name=name)  # downloads weights on first use
                _models[name] = m
        return m

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._model()
        vecs = [list(map(float, v)) for v in model.embed(texts)]
        self.check_dims(vecs)
        return vecs
