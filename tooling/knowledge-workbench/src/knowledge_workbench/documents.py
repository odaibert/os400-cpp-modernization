"""Deterministic cited observations and explicitly human-reviewed proposals."""

from __future__ import annotations

from typing import Literal

from .core import Graph, WorkbenchError


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace(
        "<", "&lt;"
    ).replace(">", "&gt;").replace("`", "'").replace("[", "\\[").replace("]", "\\]")


def render_documents(graph: Graph, kind: Literal["as-built", "spec-draft"]) -> dict[str, str]:
    if kind not in {"as-built", "spec-draft"}:
        raise WorkbenchError("invalid_kind", "Document kind must be as-built or spec-draft.")
    sources = {source.id: source for source in graph.sources}
    spans = {evidence.id: evidence for evidence in graph.evidence}

    def citations(ids: list[str]) -> str:
        result = []
        for eid in sorted(ids):
            item = spans[eid]
            source = sources[item.source_id]
            result.append(f"`{_escape(source.path)}:{item.line_start}-{item.line_end}` "
                          f"(SHA-256 `{source.sha256}`)")
        return "; ".join(result) or "Unknown: no repository evidence"

    metadata = (
        f"Repository: `{_escape(graph.repo_id)}`  \n"
        f"Generation: `{graph.generation_id}`  \n"
        f"Schema: {graph.schema_version}; status: **{graph.status}**; "
        f"language: `{graph.profile.standard}`\n\n"
        "Scope: local UTF-8 C++ parsed by Clang under the explicit profile. "
        "No execution, IBM i certification, runtime behavior or business requirements inferred.\n\n"
    )
    manifest = "## Source manifest\n\n| Path | Bytes | SHA-256 |\n|---|---:|---|\n"
    for source in sorted(graph.sources, key=lambda item: item.path):
        manifest += f"| {_escape(source.path)} | {source.size} | `{source.sha256}` |\n"
    observations = "## Observed AST declarations\n\n| Kind | Name | Translation unit | Evidence |\n|---|---|---|---|\n"
    for node in sorted(graph.nodes, key=lambda item: (item.kind, item.name, item.id)):
        if node.kind in {"external", "file"} or not node.evidence_ids:
            continue
        observations += (
            f"| {node.kind} | {_escape(node.name)} | "
            f"{_escape(str(node.properties.get('translation_unit', 'unknown')))} | "
            f"{citations(node.evidence_ids)} |\n"
        )
    names = {node.id: node.name for node in graph.nodes}
    relationships = "## Observed relationships\n\n"
    for edge in sorted(graph.edges, key=lambda item: item.id):
        if edge.kind in {"CALLS", "REFERENCES"}:
            relationships += (
                f"- `{_escape(names[edge.source])}` **{edge.kind}** "
                f"`{_escape(names[edge.target])}`: {citations(edge.evidence_ids)}\n"
            )
    limitations = (
        "## Unknowns and limitations\n\n"
        "- These are parsed facts, not proof of execution or equivalent binary behavior.\n"
        "- External symbols have no retained source evidence; unresolved/unsupported syntax "
        "can make the graph partial.\n"
        "- Only the selected translation units, standard, defines and include roots were assessed.\n"
        "- Requirements, security assurances, production use and IBM extensions remain unverified.\n"
    )
    for diagnostic in graph.diagnostics:
        limitations += f"- `{diagnostic.code}`: {_escape(diagnostic.message)}"
        if diagnostic.path:
            limitations += f" (`{_escape(diagnostic.path)}`)"
        limitations += "\n"
    if kind == "as-built":
        return {"as-built.md": "# As-built: observed source structure\n\n" + metadata
                + manifest + "\n" + observations + "\n" + relationships + "\n" + limitations}
    return {
        "spec-draft.md": (
            "# Specification draft — human review required\n\n"
            "**PROPOSAL, not recovered requirements.** This document is a starting point for "
            "human review, not an executed plan, approved specification or official Spec Kit "
            "certification. No Spec Kit commands have been installed or run.\n\n"
            + metadata
            + "## Proposed review questions (not requirements)\n\n"
            "- Which input encodings, target ABIs and compiler profiles must be supported?\n"
            "- Which observed declarations should be preserved or changed, and why?\n"
            "- What acceptance examples and target-platform tests would establish correctness?\n"
            "- Who approves requirements, migration risks and any implementation work?\n\n"
            + manifest + "\n" + observations + "\n" + limitations
        )
    }
