from __future__ import annotations

import abc

from models import BackendConfig


class EmbeddingBackend(abc.ABC):
    def __init__(self, cfg: BackendConfig):
        self.cfg = cfg

    @abc.abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed already-prefixed texts. Must raise on failure (pipeline queues it)."""

    def health(self) -> tuple[bool, str]:
        """Cheap reachability check. Default: try embedding one short string."""
        try:
            vecs = self.embed(["snarevec health check"])
            got = len(vecs[0])
            if self.cfg.dims and got != self.cfg.dims:
                return False, f"dimension mismatch: backend returned {got}, config says {self.cfg.dims}"
            return True, f"ok ({got}-dim)"
        except Exception as e:  # noqa: BLE001 — surfaced verbatim to the UI
            return False, str(e)

    def check_dims(self, vecs: list[list[float]]) -> None:
        if vecs and self.cfg.dims and len(vecs[0]) != self.cfg.dims:
            raise ValueError(
                f"backend '{self.cfg.name}' returned {len(vecs[0])}-dim vectors "
                f"but is configured for {self.cfg.dims} — refusing to store incompatible vectors"
            )
