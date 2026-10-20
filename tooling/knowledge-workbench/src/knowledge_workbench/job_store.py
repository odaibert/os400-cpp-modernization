"""Private SQLite conversion history; no graph, source snapshots or bearer tokens."""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from .conversion import ConversionRequest, ConversionResult
from .core import Contract, WorkbenchError

SESSION_SECONDS = 8 * 60 * 60
HISTORY_LIMIT = 100
TERMINAL_CONVERSIONS = {"succeeded", "blocked", "failed", "cancelled", "interrupted"}


def owner_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ConversionRecord(Contract):
    id: str
    repo_id: str
    owner_hash: str
    status: Literal["queued", "running", "succeeded", "blocked", "failed", "cancelled", "interrupted"]
    stage: str
    completed_files: int = Field(ge=0)
    total_files: int = Field(ge=1)
    request: ConversionRequest
    result: ConversionResult | None
    error: dict[str, str] | None
    created_at: float
    updated_at: float


class JobStore:
    def __init__(self, directory: Path) -> None:
        self._runtime_descriptor: int | None = None
        self.path = directory / "conversions.sqlite3"
        if directory.is_symlink() or self.path.is_symlink():
            raise WorkbenchError("forbidden_path", "Job state paths must not be symlinks.")
        try:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
            descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise WorkbenchError("job_store_unavailable", "Cannot open private conversion history.") from exc
        with self.connection() as database:
            version = database.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise WorkbenchError("job_store_invalid", "Unsupported conversion-history schema.")
            database.executescript("""
                CREATE TABLE IF NOT EXISTS conversions (
                    id TEXT PRIMARY KEY, repo_id TEXT NOT NULL, owner_hash TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS conversion_owner ON conversions(owner_hash, repo_id);
                CREATE TABLE IF NOT EXISTS sessions (
                    owner_hash TEXT PRIMARY KEY, expires_at REAL NOT NULL
                );
                PRAGMA user_version = 1;
            """)

    def acquire_runtime(self) -> None:
        path = self.path.with_suffix(".lock")
        if path.is_symlink():
            raise WorkbenchError("forbidden_path", "Job runtime paths must not be symlinks.")
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            raise WorkbenchError("job_store_unavailable", "Cannot open the job runtime lock.") from exc
        try:
            os.fchmod(descriptor, 0o600)
            if os.name == "nt":
                import msvcrt

                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"\0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(descriptor)
            raise WorkbenchError(
                "job_store_busy", "Another workbench server is using this state directory. Stop it first.",
            ) from exc
        self._runtime_descriptor = descriptor

    def release_runtime(self) -> None:
        if self._runtime_descriptor is not None:
            os.close(self._runtime_descriptor)
            self._runtime_descriptor = None

    @contextmanager
    def runtime(self) -> Iterator[None]:
        self.acquire_runtime()
        try:
            yield
        finally:
            self.release_runtime()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        try:
            database = sqlite3.connect(self.path, timeout=5)
            try:
                with database:
                    yield database
            finally:
                database.close()
        except sqlite3.Error as exc:
            raise WorkbenchError(
                "job_store_unavailable", "Cannot read or save conversion history. Check the local state directory.",
            ) from exc

    @staticmethod
    def _decode(payload: str) -> ConversionRecord:
        try:
            return ConversionRecord.model_validate_json(payload)
        except ValidationError as exc:
            raise WorkbenchError("job_store_invalid", "Saved conversion history is invalid.") from exc

    def check_connection(self) -> dict[str, str]:
        with self.connection() as database:
            if database.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise WorkbenchError("job_store_invalid", "Unsupported conversion-history schema.")
            database.execute("SELECT 1 FROM conversions LIMIT 1").fetchone()
            database.execute("SELECT 1 FROM sessions LIMIT 1").fetchone()
        return {"status": "ready", "sqlite": "connected"}

    def save(self, record: ConversionRecord) -> None:
        with self.connection() as database:
            database.execute(
                "INSERT INTO conversions VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (record.id, record.repo_id, record.owner_hash, record.model_dump_json(), record.created_at),
            )
            database.execute(
                "DELETE FROM conversions WHERE id IN "
                "(SELECT id FROM conversions ORDER BY created_at DESC, id DESC LIMIT -1 OFFSET ?)",
                (HISTORY_LIMIT,),
            )

    def get(self, job_id: str, owner: str) -> ConversionRecord:
        with self.connection() as database:
            row = database.execute(
                "SELECT payload FROM conversions WHERE id=? AND owner_hash=?", (job_id, owner),
            ).fetchone()
        if row is None:
            raise WorkbenchError("not_found", "Job was not found in this browser session.")
        return self._decode(row[0])

    def list(self, repo_id: str, owner: str) -> list[ConversionRecord]:
        with self.connection() as database:
            rows = database.execute(
                "SELECT payload FROM conversions WHERE repo_id=? AND owner_hash=? "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (repo_id, owner, HISTORY_LIMIT),
            ).fetchall()
        return [self._decode(row[0]) for row in rows]

    def recover(self) -> None:
        with self.connection() as database:
            rows = database.execute("SELECT payload FROM conversions").fetchall()
            for (payload,) in rows:
                record = self._decode(payload)
                if record.status not in TERMINAL_CONVERSIONS:
                    record.status = "interrupted"
                    record.stage = "finished"
                    record.result = None
                    record.error = {
                        "code": "job_interrupted",
                        "message": "The server stopped before conversion finished. Review the graph and start a new conversion.",
                    }
                    record.updated_at = time.time()
                    database.execute(
                        "UPDATE conversions SET payload=? WHERE id=?", (record.model_dump_json(), record.id),
                    )

    def forget(self, repo_id: str) -> None:
        with self.connection() as database:
            database.execute("DELETE FROM conversions WHERE repo_id=?", (repo_id,))

    def valid_session(self, token: str) -> bool:
        if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
            return False
        with self.connection() as database:
            return database.execute(
                "SELECT 1 FROM sessions WHERE owner_hash=? AND expires_at>?",
                (owner_hash(token), time.time()),
            ).fetchone() is not None

    def session(self, token: str) -> str:
        now = time.time()
        with self.connection() as database:
            database.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
            existing = database.execute(
                "SELECT 1 FROM sessions WHERE owner_hash=?", (owner_hash(token),),
            ).fetchone() if len(token) == 64 else None
            if existing is None:
                if database.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] >= 256:
                    raise WorkbenchError("session_limit", "Local session limit reached.")
                token = secrets.token_hex(32)
            database.execute(
                "INSERT INTO sessions VALUES (?, ?) ON CONFLICT(owner_hash) "
                "DO UPDATE SET expires_at=excluded.expires_at",
                (owner_hash(token), now + SESSION_SECONDS),
            )
        return token
