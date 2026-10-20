from __future__ import annotations

import json
import os
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .core import Graph, Profile, WorkbenchError, build_graph, evidence_excerpt, verify_sources
from .conversion import ConversionRequest, ConversionResult, convert, graph_digest
from .documents import render_documents
from .neo4j_store import Neo4jStore
from .job_store import JobStore


def default_state_dir() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "os400-knowledge-workbench"


@dataclass(frozen=True)
class Repository:
    id: str
    name: str
    root: Path


class Registry:
    def __init__(self, state_dir: Path) -> None:
        self.directory = state_dir
        self.path = state_dir / "repositories.json"
        self._lock = threading.RLock()

    def _read(self) -> list[Repository]:
        if not self.path.exists():
            return []
        if self.path.is_symlink():
            raise WorkbenchError("forbidden_path", "The repository registry must not be a symlink.")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError("invalid registry")
            seen: set[str] = set()
            for row in payload:
                if (
                    not isinstance(row, dict)
                    or set(row) != {"id", "name", "root"}
                    or not all(isinstance(row[key], str) for key in ("id", "name", "root"))
                    or len(row["id"]) != 32
                    or any(char not in "0123456789abcdef" for char in row["id"])
                    or row["id"] in seen
                    or not Path(row["root"]).is_absolute()
                ):
                    raise ValueError("invalid registry entry")
                seen.add(row["id"])
            return [
                Repository(id=row["id"], name=row["name"], root=Path(row["root"]))
                for row in payload
            ]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise WorkbenchError("registry_invalid", "Cannot read the local repository registry.") from exc

    def _write(self, repositories: list[Repository]) -> None:
        if self.directory.is_symlink() or self.path.is_symlink():
            raise WorkbenchError("forbidden_path", "State paths must not be symlinks.")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        temporary = self.directory / f"registry-{secrets.token_hex(12)}.tmp"
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    [
                        {"id": repo.id, "name": repo.name, "root": str(repo.root)}
                        for repo in repositories
                    ],
                    stream,
                    sort_keys=True,
                )
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def list(self) -> list[Repository]:
        with self._lock:
            return self._read()

    def get(self, repo_id: str) -> Repository:
        for repository in self.list():
            if secrets.compare_digest(repository.id, repo_id):
                return repository
        raise WorkbenchError("not_found", "Repository is not registered. Register it with the CLI first.")

    def register(self, root: Path, name: str | None = None) -> Repository:
        if root.is_symlink():
            raise WorkbenchError("forbidden_path", "Repository roots must not be symlinks.")
        try:
            resolved = root.expanduser().resolve(strict=True)
        except OSError as exc:
            raise WorkbenchError("forbidden_path", "Repository root is not accessible.") from exc
        if not resolved.is_dir() or resolved == Path(resolved.anchor) or resolved == Path.home():
            raise WorkbenchError("forbidden_path", "Select a specific local application directory.")
        label = (name or resolved.name).strip()
        if not label or len(label) > 120 or any(ord(char) < 32 for char in label):
            raise WorkbenchError("invalid_name", "Repository name must be 1-120 printable characters.")
        with self._lock:
            repositories = self._read()
            for repository in repositories:
                if repository.root == resolved:
                    return repository
            repository = Repository(id=secrets.token_hex(16), name=label, root=resolved)
            self._write([*repositories, repository])
            return repository

    def remove(self, repo_id: str) -> None:
        with self._lock:
            self.get(repo_id)
            self._write([repository for repository in self._read() if repository.id != repo_id])


class WorkbenchService:
    def __init__(
        self,
        state_dir: Path,
        store_factory: Callable[[], Neo4jStore] | None = None,
    ) -> None:
        self.registry = Registry(state_dir)
        self._store_factory = store_factory or self._configured_store

    @staticmethod
    def _configured_store() -> Neo4jStore:
        mode = os.environ.get("NEO4J_AUTH_MODE", "required").strip().lower()
        if mode not in {"required", "none"}:
            raise WorkbenchError(
                "invalid_database_configuration",
                "NEO4J_AUTH_MODE must be required or none.",
            )
        username = os.environ.get("NEO4J_USERNAME")
        password = os.environ.get("NEO4J_PASSWORD")
        if mode == "required" and (not username or not password):
            raise WorkbenchError(
                "credentials_required",
                "Set NEO4J_USERNAME and NEO4J_PASSWORD, or explicitly set NEO4J_AUTH_MODE=none "
                "for the isolated loopback Docker database. No .env files are read.",
            )
        return Neo4jStore(
            uri=os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
            database=os.environ.get("NEO4J_DATABASE", "neo4j"),
            username=username if mode == "required" else None,
            password=password if mode == "required" else None,
        )

    def check_connection(self) -> dict[str, str]:
        store = self._store_factory()
        try:
            store.check_connection()
        finally:
            store.close()
        return {"status": "ready", "neo4j": "connected"}

    def list_repos(self) -> list[dict[str, str]]:
        return [
            {"id": repository.id, "name": repository.name, "status": "registered"}
            for repository in self.registry.list()
        ]

    def assess(self, repo_id: str, profile: Profile) -> dict:
        from .core import inventory_sources

        repository = self.registry.get(repo_id)
        sources = inventory_sources(repository.root, profile)
        return {
            "sources": [{"path": source.path, "size": source.size} for source in sources],
            "profile": profile.model_dump(),
            "diagnostics": [],
        }

    def convert(
        self, repo_id: str, payload: ConversionRequest,
        cancelled: Callable[[], bool], on_progress: Callable[[str, int, int], None],
    ) -> ConversionResult:
        repository = self.registry.get(repo_id)
        on_progress("loading_graph", 0, len(payload.paths))
        try:
            graph = self.load_graph(repo_id)
        except WorkbenchError as exc:
            if exc.code == "not_found":
                raise WorkbenchError(
                    "graph_required", "Generate a complete Neo4j graph before converting this repository.",
                ) from None
            raise
        result = convert(repository.root, repo_id, payload, cancelled, on_progress, graph=graph)
        self.verify_conversion(repo_id, result)
        return result

    def verify_conversion(self, repo_id: str, result: ConversionResult) -> None:
        graph = self.load_graph(repo_id)
        if graph.generation_id != result.generation_id or graph_digest(graph) != result.graph_digest:
            raise WorkbenchError(
                "graph_changed", "The Neo4j generation changed. Start a new conversion against the current graph.",
            )
        result.verify(self.registry.get(repo_id).root)

    def generate(
        self,
        repo_id: str,
        profile: Profile,
        cancelled: Callable[[], bool] | None = None,
        on_stage: Callable[[str], None] | None = None,
    ) -> Graph:
        repository = self.registry.get(repo_id)
        graph = build_graph(repository.root, repository.id, profile, cancelled=cancelled)
        verify_sources(repository.root, graph)
        if on_stage:
            on_stage("publishing")
        if cancelled and cancelled():
            raise WorkbenchError("cancelled", "Graph generation was cancelled.")
        store = self._store_factory()
        try:
            store.publish(graph)
        finally:
            store.close()
        return graph

    def load_graph(self, repo_id: str) -> Graph:
        repository = self.registry.get(repo_id)
        store = self._store_factory()
        try:
            graph = store.load(repo_id)
        finally:
            store.close()
        verify_sources(repository.root, graph)
        return graph

    def verify_graph(self, repo_id: str, graph: Graph) -> None:
        verify_sources(self.registry.get(repo_id).root, graph)

    def evidence(self, repo_id: str, evidence_id: str) -> dict:
        graph = self.load_graph(repo_id)
        return evidence_excerpt(self.registry.get(repo_id).root, graph, evidence_id)

    def export_documents(
        self, repo_id: str, kind: Literal["as-built", "spec-draft"]
    ) -> dict[str, str]:
        graph = self.load_graph(repo_id)
        documents = render_documents(graph, kind)
        self.verify_graph(repo_id, graph)
        return documents

    def delete(self, repo_id: str) -> None:
        self.registry.get(repo_id)
        history = JobStore(self.registry.directory)
        store = self._store_factory()
        try:
            store.delete(repo_id)
        finally:
            store.close()
        history.forget(repo_id)
        self.registry.remove(repo_id)
