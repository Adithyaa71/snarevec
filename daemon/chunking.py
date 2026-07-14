"""Chunking strategies.

Consistency rule: whatever strategy/size a profile uses must stay fixed for
the life of its collection. The manifest written with every staged file
records these values so the remote-import script can refuse mismatches.

- fixed:    sliding window over characters, cut on word boundaries, overlap.
- sentence: sentences greedily merged up to chunk_size (no mid-sentence cuts).
- semantic: sentences merged while consecutive sentence embeddings stay
            similar; a similarity drop starts a new chunk. Costs one embedding
            call per sentence, so it is the slow/optional path.
"""
from __future__ import annotations

import math
import re
from typing import Callable

from models import ChunkingConfig

_SENT_SPLIT = re.compile(r"(?<=[.!?।。])\s+|\n{2,}")
_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    # Normalize whitespace but keep paragraph breaks (they matter for chunk boundaries).
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENT_SPLIT.split(text) if s and s.strip()]
    return parts or ([text] if text else [])


def chunk_fixed(text: str, size: int, overlap: int) -> list[str]:
    text = _clean(text)
    if len(text) <= size:
        return [text] if text else []
    overlap = min(overlap, size // 2)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # pull back to the last whitespace so we don't cut words
            back = text.rfind(" ", start + int(size * 0.6), end)
            if back > start:
                end = back
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_sentence(text: str, size: int) -> list[str]:
    sents = _sentences(_clean(text))
    chunks: list[str] = []
    buf = ""
    for s in sents:
        if buf and len(buf) + len(s) + 1 > size:
            chunks.append(buf)
            buf = s
        else:
            buf = f"{buf} {s}".strip()
        # a single sentence longer than size falls back to fixed splitting
        if len(buf) > size * 1.5:
            chunks.extend(chunk_fixed(buf, size, 0))
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def chunk_semantic(
    text: str,
    size: int,
    threshold: float,
    embed_fn: Callable[[list[str]], list[list[float]]],
) -> list[str]:
    """Merge sentences while consecutive-sentence similarity stays >= threshold.
    embed_fn receives raw sentence text (no document prefix — these embeddings
    are throwaway boundary detectors, never stored)."""
    sents = _sentences(_clean(text))
    if len(sents) <= 1:
        return sents
    vecs = embed_fn(sents)
    chunks: list[str] = []
    buf = sents[0]
    for i in range(1, len(sents)):
        sim = _cosine(vecs[i - 1], vecs[i])
        if sim < threshold or len(buf) + len(sents[i]) + 1 > size:
            chunks.append(buf)
            buf = sents[i]
        else:
            buf = f"{buf} {sents[i]}"
    if buf:
        chunks.append(buf)
    return chunks


def run(cfg: ChunkingConfig, text: str, embed_fn: Callable | None = None) -> list[str]:
    if cfg.strategy == "fixed":
        return chunk_fixed(text, cfg.chunk_size, cfg.chunk_overlap)
    if cfg.strategy == "sentence":
        return chunk_sentence(text, cfg.chunk_size)
    if cfg.strategy == "semantic":
        if embed_fn is None:
            return chunk_sentence(text, cfg.chunk_size)
        return chunk_semantic(text, cfg.chunk_size, cfg.semantic_threshold, embed_fn)
    raise ValueError(f"unknown chunk strategy: {cfg.strategy}")
