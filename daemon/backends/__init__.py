"""Embedding backend registry.

Every backend implements embed(texts) -> list[vector] and health().
Prefixing ("search_document: ") is done by the capture pipeline BEFORE text
reaches a backend, so all backends receive identical input. That is the
parity guarantee across fastembed / ollama / hosted APIs.
"""
from __future__ import annotations

from models import BackendConfig

from .base import EmbeddingBackend
from .fastembed_backend import FastembedBackend
from .ollama_backend import OllamaBackend
from .openai_compat import OpenAICompatBackend
from .nomic_api import NomicApiBackend
from .hf_api import HfApiBackend

_KINDS = {
    "fastembed": FastembedBackend,
    "ollama": OllamaBackend,
    "openai_compatible": OpenAICompatBackend,
    "nomic_api": NomicApiBackend,
    "hf_api": HfApiBackend,
}

# Backends are cached per config id + fingerprint so fastembed models load once.
_cache: dict[str, EmbeddingBackend] = {}


def _fingerprint(cfg: BackendConfig) -> str:
    return f"{cfg.id}:{cfg.kind}:{cfg.model}:{cfg.base_url}:{cfg.dims}"


def get_backend(cfg: BackendConfig) -> EmbeddingBackend:
    key = _fingerprint(cfg)
    inst = _cache.get(key)
    if inst is None:
        cls = _KINDS.get(cfg.kind)
        if cls is None:
            raise ValueError(f"unknown backend kind: {cfg.kind}")
        inst = cls(cfg)
        _cache[key] = inst
    return inst
