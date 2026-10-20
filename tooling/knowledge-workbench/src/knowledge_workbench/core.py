"""Validated graph contracts, bounded source inventory and fresh original evidence."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkbenchError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Profile(Contract):
    standard: Literal["c++17", "c++20"] = "c++20"
    defines: list[str] = Field(default_factory=list, max_length=100)
    include_paths: list[str] = Field(default_factory=list, max_length=30)
    max_files: int = Field(default=200, gt=0, le=2000)
    max_file_bytes: int = Field(default=1_000_000, gt=0, le=5_000_000)
    max_total_bytes: int = Field(default=10_000_000, gt=0, le=50_000_000)

    @field_validator("include_paths")
    @classmethod
    def includes(cls, values: list[str]) -> list[str]:
        for value in values:
            safe_relative(value, allow_dot=True)
        return sorted(set(values))

    @field_validator("defines")
    @classmethod
    def macros(cls, values: list[str]) -> list[str]:
        import re

        for value in values:
            if not re.fullmatch(r"[A-Za-z_]\w*(?:=[A-Za-z0-9_+.-]+)?", value):
                raise ValueError("Defines must be simple macro names or scalar values")
        return sorted(set(values))


class Source(Contract):
    id: str
    path: str
    sha256: str
    size: int


NodeKind = Literal["file", "function", "record", "field", "variable", "namespace", "external"]
EdgeKind = Literal["DECLARES", "CONTAINS", "CALLS", "REFERENCES"]


class Node(Contract):
    id: str
    kind: NodeKind
    name: str
    evidence_ids: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class Edge(Contract):
    id: str
    source: str
    target: str
    kind: EdgeKind
    evidence_ids: list[str] = Field(default_factory=list)


class Evidence(Contract):
    id: str
    source_id: str
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=0)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)


class Diagnostic(Contract):
    code: str
    message: str
    path: str | None = None


class Graph(Contract):
    schema_version: Literal[1] = 1
    repo_id: str
    generation_id: str
    profile: Profile
    sources: list[Source] = Field(max_length=2000)
    nodes: list[Node] = Field(max_length=5000)
    edges: list[Edge] = Field(max_length=10000)
    evidence: list[Evidence] = Field(max_length=15000)
    diagnostics: list[Diagnostic] = Field(max_length=200)
    status: Literal["complete", "partial"]


EXCLUDED = {"tooling", ".git", ".squad", "node_modules", "build", "exports"}
CPP_SUFFIXES = {".cpp", ".h", ".hpp", ".cxx", ".cc"}


def stable_id(*parts: Any) -> str:
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def safe_relative(value: str, allow_dot: bool = False) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value or len(value) > 512 or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or path.is_absolute()
        or ".." in path.parts
        or any(p.startswith(".") or p in EXCLUDED for p in path.parts)
        or (str(path) == "." and not allow_dot)
    ):
        raise WorkbenchError("unsafe_path", "Path is outside the permitted source scope.")
    return path


def validate_root(root: Path) -> Path:
    root = Path(root).absolute()
    if any(p.is_symlink() for p in [root, *root.parents]) or not root.is_dir():
        raise WorkbenchError("unsafe_path", "Repository root must be a real local directory.")
    return root


def allowed_path(value: str) -> bool:
    try:
        path = safe_relative(value)
    except WorkbenchError:
        return False
    return path.suffix.lower() in CPP_SUFFIXES


def read_source(root: Path, relative: str, limit: int) -> bytes:
    """Open with directory descriptors so symlink races cannot escape the root."""
    path = safe_relative(relative)
    if not allowed_path(relative):
        raise WorkbenchError("unsafe_path", "File is not an approved source input.")
    descriptor = None
    try:
        descriptor = os.open(validate_root(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in path.parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(fd, "rb") as stream:
            import stat

            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise WorkbenchError("input_limit", "Input is not a bounded regular file.")
            content = stream.read(limit + 1)
        if len(content) > limit:
            raise WorkbenchError("input_limit", "Source file exceeds the byte limit.")
        content.decode("utf-8", errors="strict")
        return content
    except UnicodeError:
        raise WorkbenchError("encoding", "Only strict UTF-8 inputs are supported.") from None
    except OSError:
        raise WorkbenchError("unsafe_path", "Source is unavailable or contains a symlink.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def inventory_sources(root: Path, profile: Profile) -> list[Source]:
    root = validate_root(root)
    sources = []
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        relative_dir = Path(directory).relative_to(root)
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in EXCLUDED
                         and not (relative_dir == Path("docs") and d == "reinvention"))
        for d in dirs:
            if (Path(directory) / d).is_symlink():
                raise WorkbenchError("unsafe_path", "Symlink directories are not supported.")
        for filename in sorted(files):
            relative = (relative_dir / filename).as_posix()
            if not allowed_path(relative):
                continue
            data = read_source(root, relative, profile.max_file_bytes)
            total += len(data)
            if len(sources) >= profile.max_files or total > profile.max_total_bytes:
                raise WorkbenchError("input_limit", "Repository exceeds the input budget.")
            digest = hashlib.sha256(data).hexdigest()
            sources.append(Source(id=stable_id("source", relative, digest), path=relative,
                                  sha256=digest, size=len(data)))
    return sorted(sources, key=lambda s: s.path)


def verify_sources(root: Path, graph: Graph) -> None:
    try:
        current = inventory_sources(root, graph.profile)
    except WorkbenchError:
        raise WorkbenchError("source_changed", "Sources are unavailable or changed; regenerate.") from None
    if current != graph.sources:
        raise WorkbenchError("source_changed", "Source manifest changed; regenerate the graph.")


def evidence_excerpt(root: Path, graph: Graph, evidence_id: str) -> dict:
    verify_sources(root, graph)
    evidence = next((item for item in graph.evidence if item.id == evidence_id), None)
    if evidence is None:
        raise WorkbenchError("not_found", "Evidence was not found.")
    source = next(item for item in graph.sources if item.id == evidence.source_id)
    data = read_source(root, source.path, graph.profile.max_file_bytes)
    if hashlib.sha256(data).hexdigest() != source.sha256:
        raise WorkbenchError("source_changed", "Source changed; regenerate the graph.")
    return {"id": evidence.id, "path": source.path, "line_start": evidence.line_start,
            "line_end": evidence.line_end,
            "text": data[evidence.start_byte:evidence.end_byte].decode("utf-8")}


def build_graph(root: Path, repo_id: str, profile: Profile,
                cancelled: Callable[[], bool] | None = None) -> Graph:
    from .parser import extract_graph

    graph = extract_graph(validate_root(root), repo_id, profile, cancelled)
    verify_sources(root, graph)
    return graph
