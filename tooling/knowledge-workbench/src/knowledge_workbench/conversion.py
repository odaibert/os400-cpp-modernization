"""Guarded endian migration drafts; never execute or overwrite application sources."""

from __future__ import annotations

import hashlib
import platform
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from pydantic import Field, field_validator

from .core import (
    Contract, Diagnostic, Graph, Profile, Source, WorkbenchError,
    inventory_sources, read_source, safe_relative, stable_id, verify_sources,
)
from .parser import extract_graph

MAX_BYTES = 1_000_000
MAX_FILE_BYTES = 250_000
MAX_FILES = 20
CONVERSION_VERSION = 3
IDENTIFIER = r"[A-Za-z_][A-Za-z_0-9]*"
FIELD = re.compile(
    rf"\s*(?P<type>(?:std::)?u?int(?:8|16|32|64)_t|char)\s+"
    rf"(?P<name>{IDENTIFIER})(?:\s*\[\s*(?P<count>[1-9][0-9]*)\s*\])?\s*;"
)
COPY = re.compile(
    rf"(?:std::)?memcpy\s*\(\s*&\s*(?P<variable>{IDENTIFIER})\s*,\s*"
    rf"(?P<buffer>{IDENTIFIER})\s*,\s*sizeof\s*\(\s*(?P<record>{IDENTIFIER})\s*\)\s*\)"
)
HELPER = """// Migration draft for Linux x86-64 / C++20. Human review required.
// Original comments below may describe pre-conversion behavior.
// Record layout and target-compatible text encoding were confirmed by the operator.
#include <bit>
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace kw_migration_detail {
template<class T> constexpr T from_big_endian(T value) noexcept {
    static_assert(std::is_integral_v<T>);
    static_assert(std::endian::native == std::endian::little ||
                  std::endian::native == std::endian::big);
    if constexpr (std::endian::native == std::endian::little) {
        using U = std::make_unsigned_t<T>;
        U input = std::bit_cast<U>(value);
        U output = 0;
        for (std::size_t byte = 0; byte < sizeof(T); ++byte) {
            output = static_cast<U>((output << 8) | (input & 0xffu));
            input >>= 8;
        }
        return std::bit_cast<T>(output);
    }
    return value;
}
}

"""


class ConversionRequest(Contract):
    paths: list[str] = Field(min_length=1, max_length=MAX_FILES)
    profile: Profile = Field(default_factory=Profile)
    confirmed_big_endian_layout: Literal[True]
    target: Literal["linux-x86_64-c++20"] = "linux-x86_64-c++20"

    @field_validator("paths")
    @classmethod
    def paths_are_cpp(cls, values: list[str]) -> list[str]:
        for value in values:
            if safe_relative(value).suffix.lower() not in {".cpp", ".cc", ".cxx"}:
                raise ValueError("Select C++ translation units, not headers or documents")
        return sorted(set(values))


@dataclass(frozen=True)
class RecordField:
    name: str
    width: int
    count: int


@dataclass(frozen=True)
class Rewrite:
    start: int
    end: int
    variable: str
    record: str
    fields: list[RecordField]


@dataclass
class ConversionFile:
    path: str
    rewrites: list[Rewrite] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    already_modernized_copies: int = 0
    layout_checks: list[Rewrite] = field(default_factory=list)

    def public(self) -> dict:
        return {
            "path": self.path, "status": (
                "blocked" if self.diagnostics else "ready" if self.rewrites else "unchanged"
            ),
            "changes": len(self.rewrites),
            "diagnostics": [item.model_dump() for item in self.diagnostics],
        }


@dataclass
class ConversionResult:
    sources: list[Source]
    profile: Profile
    files: list[ConversionFile]
    generation_id: str
    graph_digest: str
    validated: bool = False
    validation_platform: str = ""
    recipe_version: int = 0

    @property
    def blocked(self) -> bool:
        return any(item.diagnostics for item in self.files)

    def public(self) -> dict:
        return {
            "target": "linux-x86_64-c++20", "requires_review": True,
            "generation_id": self.generation_id, "graph_digest": self.graph_digest,
            "recipe_version": self.recipe_version,
            "profile": self.profile.model_dump(),
            "validation_status": "passed" if self.validated else "blocked",
            "validation": (
                f"Native Clang syntax/layout checks passed ({self.validation_platform}). "
                if self.validated else "Generated syntax/layout validation was blocked or failed. "
            ) + "Linux x86-64 build and execution not performed.",
            "files": [item.public() for item in self.files],
        }

    def verify(self, root: Path) -> None:
        if self.recipe_version != CONVERSION_VERSION:
            raise WorkbenchError(
                "conversion_outdated", "Conversion safety checks have changed. Regenerate the graph and start a new conversion.",
            )
        try:
            current = inventory_sources(root, self.profile)
        except WorkbenchError:
            raise WorkbenchError("source_changed", "Conversion inputs are unavailable. Start a new conversion.") from None
        if current != self.sources:
            raise WorkbenchError("source_changed", "Conversion inputs changed. Start a new conversion.")

    def preview(self, root: Path, path: str) -> dict:
        self.verify(root)
        item = next((item for item in self.files if item.path == path), None)
        if item is None:
            raise WorkbenchError("not_found", "This file is not part of the conversion job.")
        before = self._read(root, path)
        after = render(before, item.rewrites) if not item.diagnostics else None
        self.verify(root)
        return {**item.public(), "before": before.decode("utf-8"), "after": after,
                "requires_review": True}

    def _read(self, root: Path, path: str) -> bytes:
        source = next(item for item in self.sources if item.path == path)
        data = read_source(root, path, self.profile.max_file_bytes)
        if hashlib.sha256(data).hexdigest() != source.sha256:
            raise WorkbenchError("source_changed", "Conversion inputs changed. Start a new conversion.")
        return data

    def output_files(self, root: Path) -> dict[str, str]:
        self.verify(root)
        if self.blocked or not self.validated:
            raise WorkbenchError("conversion_blocked", "Resolve conversion blockers before downloading.")
        output = {
            f"converted/{item.path}": render(self._read(root, item.path), item.rewrites)
            for item in self.files
        }
        for source in self.sources:
            if Path(source.path).suffix.lower() in {".h", ".hpp"}:
                output[f"converted/{source.path}"] = self._read(root, source.path).decode("utf-8")
        self.verify(root)
        return output


def mask_comments(text: str) -> str:
    def replace(match: re.Match) -> str:
        value = match[0]
        if value.startswith(("//", "/*")):
            return re.sub(r"[^\r\n]", " ", value)
        return value

    return re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\r\n]*|/\*.*?\*/',
                  replace, text, flags=re.S)


def record_fields(text: str, name: str) -> list[RecordField] | None:
    match = re.fullmatch(rf"struct\s+{re.escape(name)}\s*\{{(.*)\}}",
                         mask_comments(text).strip(), re.S)
    if not match:
        return None
    body = match[1]
    fields = []
    offset = 0
    while body[offset:].strip():
        field_match = FIELD.match(body, offset)
        if not field_match:
            return None
        type_name, field_name, count = field_match.group("type", "name", "count")
        width_match = re.search(r"(8|16|32|64)", type_name)
        width = int(width_match[0]) // 8 if width_match else 1
        if count and width != 1:
            return None
        fields.append(RecordField(field_name, width, int(count or "1")))
        if len(fields) > 64:
            return None
        offset = field_match.end()
    if not fields or not any(item.width > 1 for item in fields):
        return None
    return fields


def render(before: bytes, rewrites: list[Rewrite], *, layout_checks: list[Rewrite] | None = None) -> str:
    edits = [(item, True) for item in rewrites] + [(item, False) for item in layout_checks or []]
    if not edits:
        return before.decode("utf-8")
    output = before
    for rewrite, swap in sorted(edits, key=lambda item: item[0].start, reverse=True):
        statement = before[rewrite.start:rewrite.end].decode("utf-8")
        size = sum(item.width * item.count for item in rewrite.fields)
        lines = ["{", f'    static_assert(sizeof({rewrite.record}) == {size}, "Review record padding");']
        offset = 0
        for item in rewrite.fields:
            lines.append(f'    static_assert(offsetof({rewrite.record}, {item.name}) == {offset}, '
                         '"Review wire-field offsets");')
            offset += item.width * item.count
        lines.append(f"    {statement}")
        for item in rewrite.fields:
            if swap and item.width > 1:
                member = f"{rewrite.variable}.{item.name}"
                lines.append(f"    {member} = kw_migration_detail::from_big_endian({member});")
        lines.append("}")
        replacement = "\n".join(lines).encode("utf-8")
        output = output[:rewrite.start] + replacement + output[rewrite.end:]
    return (HELPER if rewrites else "#include <cstddef>\n") + output.decode("utf-8")


def supported_preprocessing(content: str, path: str) -> bool:
    directives = list(re.finditer(r"^[ \t]*#[ \t]*([^\r\n]+)", content, re.M))
    allowed_guard_positions: set[int] = set()
    header = Path(path).suffix.lower() in {".h", ".hpp"}
    if header and len(directives) >= 3:
        guard = re.fullmatch(r"ifndef\s+([A-Za-z][A-Za-z_0-9]*)\s*", directives[0][1])
        if (
            guard and "__" not in guard[1] and not content[:directives[0].start()].strip()
            and " ".join(directives[1][1].split()) == f"define {guard[1]}"
            and not content[directives[0].end():directives[1].start()].strip()
            and directives[-1][1].strip() == "endif" and not content[directives[-1].end():].strip()
        ):
            allowed_guard_positions = {0, 1, len(directives) - 1}
    for position, directive in enumerate(directives):
        value = " ".join(directive[1].split())
        if position in allowed_guard_positions or re.match(r'include\s*[<"]', value):
            continue
        if header and value == "pragma once":
            continue
        return False
    return True


def reviewed_endian_helper(text: str) -> int | None:
    clean = mask_comments(text).strip()
    signature = re.match(
        rf"(?P<inline>inline\s+)?(?P<type>(?:std::)?uint(?P<bits>16|32)_t)\s+"
        rf"(?P<name>{IDENTIFIER})\s*\(\s*(?P=type)\s+(?P<arg>{IDENTIFIER})\s*\)\s*\{{",
        clean,
    )
    if not signature:
        return None
    bits, name, arg, type_name = signature.group("bits", "name", "arg", "type")
    fallback = (
        f"(({arg} >> 24) & 0x000000FF) | (({arg} >> 8) & 0x0000FF00) | "
        f"(({arg} << 8) & 0x00FF0000) | (({arg} << 24) & 0xFF000000)"
        if bits == "32" else f"static_cast<{type_name}>(({arg} >> 8) | ({arg} << 8))"
    )
    intrinsic = "_byteswap_ulong" if bits == "32" else "_byteswap_ushort"
    expected = f"""
        {'inline ' if signature['inline'] else ''}{type_name} {name}({type_name} {arg}) {{
            if constexpr (std::endian::native == std::endian::big) return {arg};
            #if defined(__GNUC__) || defined(__clang__)
                return __builtin_bswap{bits}({arg});
            #elif defined(_MSC_VER)
                return {intrinsic}({arg});
            #else
                return {fallback};
            #endif
        }}
    """
    token = r"0[xX][0-9A-Fa-f]+|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|::|>>|<<|==|\|\||&&|[^\s]"
    return int(bits) // 8 if re.findall(token, clean) == re.findall(token, expected) else None


def decoded_prefix_end(
    text: str, offset: int, variable: str, fields: list[RecordField],
    helper_calls: dict[tuple[int, int], int],
    *, consumed_calls: set[tuple[int, int]] | None = None,
) -> tuple[int, set[tuple[int, int]], set[tuple[int, int]]] | None:
    clean = mask_comments(text)
    expected = {item.name: item.width for item in fields if item.width > 1}
    seen = set()
    used_calls: set[tuple[int, int]] = set()
    used_writes: set[tuple[int, int]] = set()
    position = 0
    assignment = re.compile(
        rf"\s*(?P<target>{re.escape(variable)})\s*\.\s*(?P<field>{IDENTIFIER})\s*=\s*"
        rf"(?P<call>{IDENTIFIER}\s*\(\s*{re.escape(variable)}\s*\.\s*(?P=field)\s*\))\s*;"
    )
    for _ in expected:
        match = assignment.match(clean, position)
        if not match or match["field"] not in expected or match["field"] in seen:
            return None
        call_span = (
            offset + len(text[:match.start("call")].encode("utf-8")),
            offset + len(text[:match.end("call")].encode("utf-8")),
        )
        if (
            (consumed_calls is not None and call_span in consumed_calls)
            or helper_calls.get(call_span) != expected[match["field"]]
        ):
            return None
        target_span = (
            offset + len(text[:match.start("target")].encode("utf-8")),
            offset + len(text[:match.end("target")].encode("utf-8")),
        )
        seen.add(match["field"])
        used_calls.add(call_span)
        used_writes.add(target_span)
        position = match.end()
    return offset + len(text[:position].encode("utf-8")), used_calls, used_writes


def standalone_copy_end(
    data: bytes, text: str, masked: str, start_byte: int, end_byte: int,
) -> int | None:
    prefix_chars = len(data[:start_byte].decode("utf-8"))
    expr_chars = len(data[start_byte:end_byte].decode("utf-8"))
    line_start = masked.rfind("\n", 0, prefix_chars) + 1
    if masked[line_start:prefix_chars].strip():
        return None
    suffix_start = prefix_chars + expr_chars
    tail = re.match(r"\s*;", masked[suffix_start:])
    if not tail:
        return None
    return end_byte + len(text[suffix_start:suffix_start + tail.end()].encode("utf-8"))


def plan_file(path: str, data: bytes, graph: Graph, root: Path) -> ConversionFile:
    result = ConversionFile(path)
    source_text = data.decode("utf-8")
    text = mask_comments(source_text)

    def block(code: str, message: str) -> None:
        if len(result.diagnostics) < 20:
            result.diagnostics.append(Diagnostic(code=code, message=message, path=path))

    if data.startswith(b"\xef\xbb\xbf") or re.search(r"\bkw_migration_detail\b", text):
        block("unsupported_source", "BOM-prefixed or previously generated input requires manual review.")
        return result
    evidence = {item.id: item for item in graph.evidence}
    sources = {item.id: item for item in graph.sources}
    nodes = {item.id: item for item in graph.nodes}
    local = {node.id for node in graph.nodes if node.properties.get("translation_unit") == path}
    contents = {path: data}

    def source_bytes(relative: str) -> bytes:
        if relative not in contents:
            contents[relative] = read_source(root, relative, graph.profile.max_file_bytes)
        return contents[relative]

    helpers = {}
    helper_spans: dict[str, list[tuple[int, int]]] = {}
    if not graph.profile.defines:
        for node in graph.nodes:
            if node.id not in local or node.kind != "function" or not node.evidence_ids:
                continue
            for eid in node.evidence_ids:
                span = evidence[eid]
                relative = sources[span.source_id].path
                content = source_bytes(relative)
                width = reviewed_endian_helper(content[span.start_byte:span.end_byte].decode("utf-8"))
                calls = [edge for edge in graph.edges if edge.kind == "CALLS" and edge.source == node.id]
                if width and calls and all(
                    nodes[edge.target].name == f"__builtin_bswap{width * 8}"
                    and nodes[edge.target].properties.get("definition") is not True
                    for edge in calls
                ):
                    helpers[node.id] = width
                    helper_spans.setdefault(relative, []).append((span.start_byte, span.end_byte))
                    break
    # Conversion does not reinterpret macros or inactive compiler branches.
    relevant = {path}
    relevant.update(source.path for source in graph.sources if Path(source.path).suffix.lower() in {".h", ".hpp"})
    relevant.update(sources[evidence[eid].source_id].path
                    for node in graph.nodes if node.id in local for eid in node.evidence_ids)
    for relative in sorted(relevant):
        raw = source_bytes(relative)
        for start, end in sorted(helper_spans.get(relative, []), reverse=True):
            raw = raw[:start] + re.sub(rb"[^\r\n]", b" ", raw[start:end]) + raw[end:]
        content = mask_comments(raw.decode("utf-8"))
        if not supported_preprocessing(content, relative):
            block("unsupported_preprocessing", "Only verified whole-header guards and pragma once are supported; conditional code or macros require review.")
    copies = []
    for edge in graph.edges:
        if edge.kind != "CALLS" or edge.source not in local:
            continue
        target = nodes[edge.target]
        if edge.source in helpers:
            continue
        external = target.properties.get("external")
        if (external and target.name not in {"memcpy", "operator<<", "write"}
                or not external and target.properties.get("definition") is False):
            block("unsupported_call", "An unreviewed external or declaration-only call needs a porting adapter.")
        if target.name == "memcpy":
            if not external:
                block("unsupported_copy", "A custom memcpy implementation requires manual review.")
                continue
            copies.extend((edge.source, eid) for eid in edge.evidence_ids)
    consumed_helper_calls: dict[str, set[tuple[int, int]]] = {}
    variable_copy_sites: dict[tuple[str, str], list[tuple[int, int, Rewrite, bool, set[tuple[int, int]]]]] = {}
    ordered_copies = sorted(
        set(copies), key=lambda item: (evidence[item[1]].start_byte, evidence[item[1]].end_byte, item[0], item[1]),
    )
    for owner_id, eid in ordered_copies:
        if len(result.rewrites) + result.already_modernized_copies >= 100:
            block("conversion_limit", "More than 100 record copies in one file require a narrower selection.")
            break
        span = evidence[eid]
        if sources[span.source_id].path != path:
            block("header_rewrite", "A record copy in a header requires a separate reviewed migration.")
            continue
        expression = mask_comments(data[span.start_byte:span.end_byte].decode("utf-8"))
        match = COPY.fullmatch(expression)
        statement_end = standalone_copy_end(data, source_text, text, span.start_byte, span.end_byte)
        if not match or statement_end is None:
            block("unsupported_copy", "Only standalone memcpy(&record, buffer, sizeof(Record)) statements are supported.")
            continue
        owner = nodes[owner_id]
        sites = [site for site in owner.properties.get("record_copies", []) if site["evidence_id"] == eid]
        if (owner.properties.get("conversion_analysis") != 2 or len(sites) != 1
                or not sites[0].get("variable_id")):
            block("conversion_analysis_required", "Regenerate the Neo4j graph with current record-access analysis before converting.")
            continue
        if not sites[0].get("local_destination"):
            block("record_escape", "Only local value records are supported. Global, static or reference-bound destinations need manual review.")
            continue
        record_ids = {site["record_id"] for site in sites}
        records = [nodes[key] for key in record_ids if key in nodes
                   and nodes[key].name == match["record"] and nodes[key].evidence_ids]
        if len(records) != 1:
            block("unresolved_record", "The copy destination must resolve to a named plain struct.")
            continue
        record_span = evidence[records[0].evidence_ids[0]]
        record_path = sources[record_span.source_id].path
        record_data = source_bytes(record_path)
        fields = record_fields(
            record_data[record_span.start_byte:record_span.end_byte].decode("utf-8"), match["record"],
        )
        if fields is None:
            block("unsupported_record", "Records require fixed-width integers and byte arrays; other layouts need review.")
            continue
        owner_end = max(evidence[key].end_byte for key in owner.evidence_ids)
        original_remaining = data[statement_end:owner_end].decode("utf-8")
        helper_calls = {
            (evidence[key].start_byte, evidence[key].end_byte): helpers[edge.target]
            for edge in graph.edges if edge.kind == "CALLS" and edge.source == owner_id
            and edge.target in helpers for key in edge.evidence_ids
            if sources[evidence[key].source_id].path == path
        }
        owner_consumed = consumed_helper_calls.setdefault(owner_id, set())
        decoded = decoded_prefix_end(
            original_remaining, statement_end, match["variable"], fields, helper_calls,
            consumed_calls=owner_consumed,
        )
        used_writes: set[tuple[int, int]] = set()
        if decoded is not None:
            _, used_calls, used_writes = decoded
            owner_consumed.update(used_calls)
        rewrite = Rewrite(span.start_byte, statement_end, match["variable"], match["record"], fields)
        variable_copy_sites.setdefault((owner_id, sites[0]["variable_id"]), []).append(
            (span.start_byte, statement_end, rewrite, decoded is not None, used_writes)
        )
    for (owner_id, variable_id), copy_entries in variable_copy_sites.items():
        owner = nodes[owner_id]
        fields = copy_entries[0][2].fields
        numeric_fields = {item.name for item in fields if item.width > 1}
        copy_ranges = [(start, end) for start, end, *_ in copy_entries]
        all_used_writes = set().union(*(entry[4] for entry in copy_entries))
        accesses = [
            access for access in owner.properties.get("record_accesses", [])
            if access["variable_id"] == variable_id
            and sources[evidence[access["evidence_id"]].source_id].path == path
            and not any(
                start <= evidence[access["evidence_id"]].start_byte < end
                for start, end in copy_ranges
            )
            and (access["member"] is None or access["member"] in numeric_fields)
        ]
        if any(access["mode"] == "escape" for access in accesses):
            block("record_escape", "The record or a numeric field escapes through an alias, address or call. Review existing decoding before conversion.")
            continue
        if any(
            access["mode"] == "write"
            and (
                evidence[access["evidence_id"]].start_byte,
                evidence[access["evidence_id"]].end_byte,
            ) not in all_used_writes
            for access in accesses
        ):
            block("post_copy_mutation", "Numeric fields are modified after the copy; review existing conversion or business logic first.")
            continue
        for _, _, rewrite, is_decoded, _ in copy_entries:
            if is_decoded:
                result.already_modernized_copies += 1
                result.layout_checks.append(rewrite)
            else:
                result.rewrites.append(rewrite)
    for edge in graph.edges:
        if (edge.kind != "CALLS" or edge.source not in local
                or edge.source in helpers or edge.target not in helpers):
            continue
        owner_consumed = consumed_helper_calls.get(edge.source, set())
        if any(
            sources[evidence[eid].source_id].path != path
            or (evidence[eid].start_byte, evidence[eid].end_byte) not in owner_consumed
            for eid in edge.evidence_ids
        ):
            block(
                "unsupported_call",
                "Reviewed endian helpers are only supported in an immediate complete in-place record decode.",
            )
            break
    if result.diagnostics:
        result.rewrites.clear()
        result.layout_checks.clear()
        result.already_modernized_copies = 0
    if not result.rewrites and not result.already_modernized_copies and not result.diagnostics:
        block("no_supported_conversion", "No supported big-endian record-copy pattern was found; no conversion was claimed.")
    return result


def graph_digest(graph: Graph) -> str:
    return stable_id(graph.model_dump(mode="json"))


def verify_conversion_graph(root: Path, repo_id: str, request: ConversionRequest, graph: Graph) -> None:
    if graph.repo_id != repo_id:
        raise WorkbenchError("graph_mismatch", "The stored graph belongs to another repository.")
    if graph.profile != request.profile:
        raise WorkbenchError(
            "graph_profile_mismatch",
            "The conversion profile differs from the Neo4j graph. Generate a graph with matching settings.",
        )
    if graph.status != "complete":
        raise WorkbenchError("incomplete_graph", "Resolve graph diagnostics and regenerate before conversion.")
    verify_sources(root, graph)


def convert(root: Path, repo_id: str, request: ConversionRequest,
            cancelled: Callable[[], bool], progress: Callable[[str, int, int], None],
            *, graph: Graph) -> ConversionResult:
    total = len(request.paths)
    progress("assessing", 0, total)
    if cancelled():
        raise WorkbenchError("cancelled", "Conversion was cancelled.")
    verify_conversion_graph(root, repo_id, request, graph)
    sources = inventory_sources(root, request.profile)
    by_path = {source.path: source for source in sources}
    if not set(request.paths) <= set(by_path):
        raise WorkbenchError("not_found", "Select files from the current approved assessment.")
    if sum(source.size for source in sources) > MAX_BYTES or any(
        by_path[path].size > MAX_FILE_BYTES for path in request.paths
    ):
        raise WorkbenchError("budget_exceeded", "Conversion supports 1 MB of inputs and 250 KB per selected file.")
    progress("analysing", 0, total)
    if graph.sources != sources:
        raise WorkbenchError("source_changed", "Inputs changed during conversion assessment.")
    files = []
    for index, path in enumerate(request.paths):
        if cancelled():
            raise WorkbenchError("cancelled", "Conversion was cancelled.")
        progress("rewriting", index, total)
        if graph.status != "complete":
            item = ConversionFile(path, diagnostics=[Diagnostic(
                code="incomplete_analysis", path=path,
                message="Resolve compiler diagnostics and missing inputs before converting.",
            )])
        else:
            item = plan_file(path, read_source(root, path, MAX_FILE_BYTES), graph, root)
        files.append(item)
        progress("rewriting", index + 1, total)
    result = ConversionResult(
        sources, request.profile, files, graph.generation_id, graph_digest(graph),
        recipe_version=CONVERSION_VERSION,
    )
    progress("validating", total, total)
    if not result.blocked:
        overrides = {
            item.path: render(result._read(root, item.path), item.rewrites, layout_checks=item.layout_checks)
            for item in files
        }
        output_profile = request.profile.model_copy(update={"standard": "c++20"})
        checked = extract_graph(root, repo_id, output_profile, cancelled=cancelled, overrides=overrides)
        if checked.status != "complete":
            for item in files:
                item.diagnostics.append(Diagnostic(
                    code="output_validation_failed", path=item.path,
                    message="Generated C++ failed native syntax/layout checks. Review record padding and compiler diagnostics.",
                ))
        else:
            result.validated = True
            result.validation_platform = f"{platform.machine()} / {sys.platform}"
    result.verify(root)
    if cancelled():
        raise WorkbenchError("cancelled", "Conversion was cancelled.")
    return result
