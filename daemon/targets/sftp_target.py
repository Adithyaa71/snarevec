"""SFTP target — stages JSONL locally (same logic as local_jsonl) then pushes
the whole staged file to a remote directory over SSH. Works from Windows with
no external scp binary (pure-python paramiko).

Remote layout mirrors local: <remote path>/<collection>/<collection>-YYYYMMDD.jsonl
The push replaces the remote file with the full local copy, so repeated
captures on the same day stay consistent (append locally, re-push whole file).
"""
from __future__ import annotations

import posixpath
from pathlib import Path

from models import ProfileConfig, TargetConfig

from .base import StorageTarget
from .local_jsonl import LocalJsonlTarget


def _local_stage_dir(cfg: TargetConfig) -> str:
    import config as cfgmod
    return str(cfgmod.config_dir() / "staged-sftp" / cfg.id)


class SftpTarget(StorageTarget):
    def _connect(self):
        try:
            import paramiko
        except ImportError as e:
            raise RuntimeError("paramiko is not installed. Run: pip install paramiko") from e
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict = {
            "hostname": self.cfg.host,
            "port": self.cfg.port or 22,
            "username": self.cfg.username,
            "timeout": 15,
        }
        if self.cfg.key_path:
            kwargs["key_filename"] = str(Path(self.cfg.key_path).expanduser())
        if self.cfg.password:
            kwargs["password"] = self.cfg.password
        client.connect(**kwargs)
        return client

    def deliver(self, manifest, points, profile: ProfileConfig) -> str:
        # 1. stage locally
        local = LocalJsonlTarget(
            TargetConfig(kind="local_jsonl", name="stage", path=_local_stage_dir(self.cfg))
        )
        staged = local.write_staged(manifest, points)
        # 2. push whole file
        client = self._connect()
        try:
            sftp = client.open_sftp()
            remote_dir = posixpath.join(self.cfg.path or ".", manifest["collection"])
            _mkdirs(sftp, remote_dir)
            remote_file = posixpath.join(remote_dir, staged.name)
            sftp.put(str(staged), remote_file)
            sftp.close()
        finally:
            client.close()
        if not self.cfg.keep_local_copy:
            staged.unlink(missing_ok=True)
        return f"{self.cfg.host}:{remote_file}"

    def test(self) -> tuple[bool, str]:
        try:
            client = self._connect()
            try:
                sftp = client.open_sftp()
                _mkdirs(sftp, self.cfg.path or ".")
                sftp.listdir(self.cfg.path or ".")
                sftp.close()
            finally:
                client.close()
            return True, f"connected to {self.cfg.host}, path ok"
        except Exception as e:  # noqa: BLE001
            return False, str(e)


def _mkdirs(sftp, remote_dir: str) -> None:
    parts = [p for p in remote_dir.split("/") if p]
    cur = "/" if remote_dir.startswith("/") else ""
    for p in parts:
        cur = posixpath.join(cur, p) if cur else p
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)
