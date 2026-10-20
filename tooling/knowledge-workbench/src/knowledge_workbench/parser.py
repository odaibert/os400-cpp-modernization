"""libclang AST extraction in a bounded, disposable subprocess (never compilation)."""

from __future__ import annotations

import json
import hashlib
import re
import shutil
import subprocess
import sys
import platform
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .core import (
    CPP_SUFFIXES, Diagnostic, Edge, Evidence, Graph, Node, Profile, Source, WorkbenchError,
    inventory_sources, read_source, safe_relative, stable_id,
)

MAX_NODES = 5000
MAX_EDGES = 10000
MAX_EVIDENCE = 15000
PARSER_SECONDS = 45


def extract_graph(root: Path, repo_id: str, profile: Profile,
                  cancelled: Callable[[], bool] | None = None, *,
                  overrides: dict[str, str] | None = None) -> Graph:
    import time

    if cancelled and cancelled():
        raise WorkbenchError("cancelled", "Generation was cancelled.")
    payload = json.dumps({"root": str(root), "repo_id": repo_id, "profile": profile.model_dump(),
                          "overrides": overrides}, ensure_ascii=False)
    if len(payload.encode("utf-8")) > 4_000_000:
        raise WorkbenchError("input_limit", "In-memory parser input exceeds its budget.")
    process = subprocess.Popen(
        [sys.executable, "-m", "knowledge_workbench.parser"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    deadline = time.monotonic() + PARSER_SECONDS
    try:
        first = True
        while True:
            if time.monotonic() >= deadline:
                raise WorkbenchError("parser_timeout", "Parser exceeded its time budget.")
            try:
                output, _ = process.communicate(input=payload if first else None, timeout=0.15)
                if time.monotonic() >= deadline:
                    raise WorkbenchError("parser_timeout", "Parser exceeded its time budget.")
                break
            except subprocess.TimeoutExpired:
                first = False
                if cancelled and cancelled():
                    raise WorkbenchError("cancelled", "Generation was cancelled.")
                if time.monotonic() >= deadline:
                    raise WorkbenchError("parser_timeout", "Parser exceeded its time budget.")
        try:
            result = json.loads(output)
            if "error" in result:
                raise WorkbenchError(result["error"]["code"], result["error"]["message"])
            if process.returncode:
                raise ValueError
            return Graph.model_validate(result)
        except (ValueError, KeyError):
            raise WorkbenchError("parser_failed", "Native AST parser did not complete safely.") from None
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def _compiler_paths() -> tuple[list[str], str]:
    compiler = shutil.which("clang++")
    if compiler is None:
        raise WorkbenchError("compiler_unavailable", "A local clang++ toolchain is required.")
    try:
        probe = subprocess.run(
            [compiler, "-E", "-x", "c++", "-", "-v"], input="", capture_output=True,
            text=True, timeout=8, check=False,
        )
        resource = subprocess.run(
            [compiler, "-print-resource-dir"], capture_output=True, text=True,
            timeout=5, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise WorkbenchError("compiler_unavailable", "Cannot inspect the local compiler.") from None
    roots = []
    active = False
    for line in probe.stderr.splitlines():
        if "#include <...> search starts here:" in line:
            active = True
        elif "End of search list." in line:
            active = False
        elif active:
            candidate = Path(line.strip().replace(" (framework directory)", ""))
            if candidate.is_absolute() and candidate.is_dir():
                roots.append(str(candidate.resolve()))
    if not roots or not Path(resource).is_dir():
        raise WorkbenchError("compiler_unavailable", "Local compiler system headers are unavailable.")
    return roots, resource


def _audit_includes(content: str, relative: str, root: Path, local_roots: list[Path],
                    source_paths: set[str], system_roots: list[str]) -> None:
    """This is a conservative input safety gate, not semantic extraction."""
    # Remove comments before inspecting directives; reject computed or continued directives.
    if "\x00" in content or "\ufeff" in content.removeprefix("\ufeff"):
        raise WorkbenchError("unsupported_input", "Embedded NUL/BOM source characters are unsupported.")
    if re.search(r"\\[ \t\v\f]*[\r\n]", content) or "??/" in content:
        raise WorkbenchError("unsupported_input", "Continued preprocessing input is not supported.")
    raw_prefix = r'(?<!\w)(?:u8|u|U|L)?R"'
    token_pattern = (
        raw_prefix + r'|"(?:\\.|[^"\\\r\n])*"|\'(?:\\.|[^\'\\\r\n])*\''
        r'|/\*.*?\*/|//[^\r\n]*|\b_Pragma\b'
    )

    def clean_token(match):
        token = match[0]
        if token == "_Pragma" or re.fullmatch(raw_prefix, token):
            raise WorkbenchError("unsupported_input", "Raw strings and computed pragmas are unsupported.")
        return re.sub(r"[^\r\n]", " ", token) if token.startswith(("//", "/*")) else token

    clean = re.sub(
        token_pattern, clean_token, content.removeprefix("\ufeff"), flags=re.S,
    )
    for line in clean.splitlines():
        if not re.match(r"^\s*(#|%:)", line):
            continue
        if re.match(r"^\s*%:", line):
            raise WorkbenchError("unsupported_input", "Alternative preprocessing tokens are unsupported.")
        match = re.match(r"^\s*#\s*(\w+)(.*)$", line)
        if not match:
            continue
        directive, body = match.groups()
        if directive in {"include_next", "import", "embed", "line"}:
            raise WorkbenchError("unsupported_input", "Unsupported preprocessing directive.")
        if directive == "pragma" and not re.fullmatch(r"\s*(once|pack\s*\([^)]*\))\s*", body):
            raise WorkbenchError("unsupported_input", "Only once/pack pragmas are supported.")
        if directive != "include":
            continue
        include = re.fullmatch(r'\s*([<"])([^>"]+)[>"]\s*', body)
        if include is None:
            raise WorkbenchError("unsafe_include", "Computed include paths are unsupported.")
        delimiter, name = include.groups()
        safe_relative(name)
        search = ([root / relative.parent] if delimiter == '"' else []) + local_roots
        resolved = False
        for directory in search:
            candidate = directory / name
            if candidate.exists() or candidate.is_symlink():
                try:
                    key = candidate.relative_to(root).as_posix()
                except ValueError:
                    raise WorkbenchError("unsafe_include", "Include escapes the repository.") from None
                if key not in source_paths or candidate.is_symlink():
                    raise WorkbenchError("unsafe_include", "Include is not an inventoried C++ input.")
                resolved = True
                break
        # Missing headers are intentionally left to Clang diagnostics. System search roots
        # are installed compiler metadata, never user-provided arbitrary directories.
        if not resolved:
            for directory in system_roots:
                if (Path(directory) / name).is_file():
                    break


def _extract(root: Path, repo_id: str, profile: Profile,
             overrides: dict[str, str] | None = None) -> Graph:
    try:
        from clang import cindex

        if sys.platform == "darwin":
            tool = subprocess.run(["xcrun", "--find", "clang++"], capture_output=True,
                                  text=True, check=True, timeout=5).stdout.strip()
            native = Path(tool).parent.parent / "lib" / "libclang.dylib"
            if native.is_file():
                cindex.Config.set_library_file(str(native))
        index = cindex.Index.create()
    except Exception:
        raise WorkbenchError("parser_unavailable", "The installed libclang cannot be loaded.") from None
    sources = inventory_sources(root, profile)
    contents = {}
    for source in sources:
        if Path(source.path).suffix.lower() not in CPP_SUFFIXES:
            continue
        data = read_source(root, source.path, profile.max_file_bytes)
        if hashlib.sha256(data).hexdigest() != source.sha256:
            raise WorkbenchError("source_changed", "Input changed while preparing the AST.")
        contents[source.path] = data.decode("utf-8")
    if overrides:
        if not set(overrides) <= set(contents):
            raise WorkbenchError("unsafe_input", "Overrides must refer to inventoried C++ inputs.")
        for name, content in overrides.items():
            if not isinstance(content, str) or len(content.encode("utf-8")) > profile.max_file_bytes:
                raise WorkbenchError("input_limit", "Generated source exceeds its byte budget.")
            contents[name] = content
        if sum(len(content.encode("utf-8")) for content in contents.values()) > profile.max_total_bytes:
            raise WorkbenchError("input_limit", "Generated inputs exceed the total byte budget.")
        sources = [
            Source(id=stable_id("source", source.path, hashlib.sha256(
                contents[source.path].encode("utf-8")).hexdigest()),
                   path=source.path, size=len(contents[source.path].encode("utf-8")),
                   sha256=hashlib.sha256(contents[source.path].encode("utf-8")).hexdigest())
            for source in sources
        ]
    system_roots, resource = _compiler_paths()
    local_roots = []
    for name in profile.include_paths:
        directory = root / str(safe_relative(name, allow_dot=True))
        if not directory.is_dir() or directory.is_symlink():
            raise WorkbenchError("unsafe_include", "Include roots must be real repository directories.")
        if any(p.is_symlink() for p in directory.parents if p != root.parent):
            raise WorkbenchError("unsafe_include", "Include roots cannot contain symlinks.")
        local_roots.append(directory)
    for name, content in contents.items():
        _audit_includes(content, Path(name), root, local_roots, set(contents), system_roots)
    # Remap every local input in memory. Clang never opens the original repository:
    # missing/new local includes cannot bypass preflight through filesystem races.
    virtual_base = Path(__file__).resolve().parents[2] / ".ast-inputs"
    if virtual_base.exists() or virtual_base.is_symlink():
        raise WorkbenchError("unsafe_input", "The in-memory AST namespace must not exist on disk.")
    virtual_root = virtual_base / uuid4().hex
    args = [
        "-x", "c++", f"-std={profile.standard}", "-nostdinc", "-nostdinc++",
        "-fno-modules", "-fno-implicit-modules", "-fno-implicit-module-maps",
        f"-fmacro-prefix-map={virtual_root}={root}",
        "-resource-dir", resource,
        *[f"-D{value}" for value in profile.defines],
    ]
    for path in system_roots:
        args += ["-isystem", path]
    for path in local_roots:
        args += ["-I", str(virtual_root / path.relative_to(root))]
    if sys.platform == "darwin":
        try:
            sdk = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True,
                                 text=True, check=True, timeout=5).stdout.strip()
            if Path(sdk).is_dir():
                args += ["-isysroot", sdk]
        except (OSError, subprocess.SubprocessError):
            raise WorkbenchError("compiler_unavailable", "macOS SDK is unavailable.") from None

    profile_key = stable_id(profile.model_dump())
    native_target = platform.machine() + "-" + sys.platform
    generation = stable_id("generation-v4", repo_id, profile_key, Path(resource).name, native_target,
                           [(s.path, s.sha256) for s in sources])
    nodes: dict[str, Node] = {}
    edges: dict[str, Edge] = {}
    evidence: dict[str, Evidence] = {}
    diagnostics: list[Diagnostic] = []
    source_by_path = {str(virtual_root / source.path): source for source in sources}
    for source in sources:
        nodes[source.id] = Node(id=source.id, kind="file", name=source.path,
                                properties={"sha256": source.sha256, "size": source.size})

    def bound() -> None:
        if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES or len(evidence) > MAX_EVIDENCE:
            raise WorkbenchError("graph_limit", "Extracted graph exceeds the entity budget.")

    def span(cursor) -> str | None:
        start, end = cursor.extent.start, cursor.extent.end
        source = source_by_path.get(str(start.file)) if start.file else None
        if not source or str(end.file) != str(start.file):
            return None
        if not (0 <= start.offset <= end.offset <= source.size):
            return None
        key = stable_id("evidence", source.id, start.offset, end.offset)
        evidence[key] = Evidence(id=key, source_id=source.id, start_byte=start.offset,
                                 end_byte=end.offset, line_start=start.line, line_end=end.line)
        bound()
        return key

    kinds = {
        cindex.CursorKind.FUNCTION_DECL: "function",
        cindex.CursorKind.CXX_METHOD: "function",
        cindex.CursorKind.CONSTRUCTOR: "function",
        cindex.CursorKind.DESTRUCTOR: "function",
        cindex.CursorKind.FUNCTION_TEMPLATE: "function",
        cindex.CursorKind.STRUCT_DECL: "record",
        cindex.CursorKind.CLASS_DECL: "record",
        cindex.CursorKind.CLASS_TEMPLATE: "record",
        cindex.CursorKind.UNION_DECL: "record",
        cindex.CursorKind.FIELD_DECL: "field",
        cindex.CursorKind.NAMESPACE: "namespace",
    }

    def symbol(cursor, tu_key: str, external: bool = False) -> str:
        usr = cursor.get_usr().replace(str(virtual_root), "")
        return stable_id("symbol", repo_id, tu_key, usr or (
            str(cursor.location.file).replace(str(virtual_root), ""),
            cursor.location.offset, cursor.kind.name, cursor.spelling
        ), "external" if external else "local")

    def connect(source: str, target: str, kind: str, eid: str | None) -> None:
        if not eid:
            return
        key = stable_id("edge", source, target, kind, eid)
        edges[key] = Edge(id=key, source=source, target=target, kind=kind, evidence_ids=[eid])
        bound()

    translation_units = [name for name in contents if Path(name).suffix.lower() in
                         {".cpp", ".cxx", ".cc"}]
    if not translation_units and contents:
        translation_units = sorted(contents)
    unsaved = [(str(virtual_root / name), content) for name, content in contents.items()]
    encoded_sources = {name: content.encode("utf-8") for name, content in contents.items()}
    for name in sorted(translation_units):
        tu_key = stable_id(name, profile_key)
        try:
            tu = index.parse(str(virtual_root / name), args=args, unsaved_files=unsaved,
                             options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
        except Exception:
            raise WorkbenchError("parser_failed", "Clang could not parse a translation unit.") from None
        for diagnostic in tu.diagnostics:
            if diagnostic.severity >= cindex.Diagnostic.Warning:
                # Never persist Clang spelling: it can contain arbitrary source or secrets.
                diagnostics.append(Diagnostic(
                    code="compiler_error" if diagnostic.severity >= cindex.Diagnostic.Error
                    else "compiler_warning",
                    message=f"Clang reported severity {diagnostic.severity}; AST may be incomplete.",
                    path=name,
                ))
                if len(diagnostics) > 200:
                    raise WorkbenchError("diagnostic_limit", "Compiler diagnostic budget exceeded.")

        def record_contains_reference(record_type) -> bool:
            seen: set[int] = set()
            stack = [record_type]
            while stack:
                current = stack.pop().get_canonical()
                while current.kind in {
                    cindex.TypeKind.CONSTANTARRAY, cindex.TypeKind.INCOMPLETEARRAY,
                    cindex.TypeKind.VARIABLEARRAY, cindex.TypeKind.DEPENDENTSIZEDARRAY,
                }:
                    current = current.get_array_element_type().get_canonical()
                if current.kind in {
                    cindex.TypeKind.LVALUEREFERENCE, cindex.TypeKind.RVALUEREFERENCE,
                }:
                    return True
                declaration = current.get_declaration()
                if declaration.kind not in {
                    cindex.CursorKind.STRUCT_DECL, cindex.CursorKind.CLASS_DECL,
                    cindex.CursorKind.UNION_DECL,
                }:
                    continue
                if not declaration.is_definition():
                    return True
                key = declaration.hash
                if key in seen:
                    continue
                seen.add(key)
                for item in declaration.get_children():
                    if item.kind in {
                        cindex.CursorKind.FIELD_DECL, cindex.CursorKind.CXX_BASE_SPECIFIER,
                    }:
                        stack.append(item.type)
            return False

        def callable_parameter_types(call_cursor):
            arguments = list(call_cursor.get_arguments())
            referenced = call_cursor.referenced
            if referenced is not None:
                canonical = referenced.type.get_canonical()
                if canonical.kind in {
                    cindex.TypeKind.POINTER, cindex.TypeKind.LVALUEREFERENCE,
                    cindex.TypeKind.RVALUEREFERENCE,
                }:
                    canonical = canonical.get_pointee().get_canonical()
                if canonical.kind == cindex.TypeKind.FUNCTIONPROTO:
                    parameters = list(canonical.argument_types())
                    if (referenced.kind == cindex.CursorKind.CXX_METHOD
                            and not referenced.is_static_method()
                            and len(arguments) == len(parameters) + 1):
                        arguments = arguments[1:]
                    return arguments, parameters, canonical.is_function_variadic()
            children = list(call_cursor.get_children())
            if children:
                callee = children[0].type.get_canonical()
                if callee.kind in {
                    cindex.TypeKind.POINTER, cindex.TypeKind.LVALUEREFERENCE,
                    cindex.TypeKind.RVALUEREFERENCE,
                }:
                    callee = callee.get_pointee().get_canonical()
                if callee.kind == cindex.TypeKind.FUNCTIONPROTO:
                    return arguments, list(callee.argument_types()), callee.is_function_variadic()
            return arguments, None, False

        def record_access(cursor, ancestors) -> tuple[str, str | None]:
            parent = next(
                (item for item in reversed(ancestors)
                 if item.kind not in {cindex.CursorKind.UNEXPOSED_EXPR, cindex.CursorKind.PAREN_EXPR}),
                None,
            )
            member = parent.referenced.spelling if (
                parent and parent.kind == cindex.CursorKind.MEMBER_REF_EXPR and parent.referenced
            ) else None
            if member is None:
                return "escape", None
            mode = "read"
            for ancestor in reversed(ancestors):
                if ancestor.kind == cindex.CursorKind.UNARY_OPERATOR:
                    tokens = list(ancestor.get_tokens())
                    if tokens and (tokens[0].spelling == "&"):
                        return "escape", member
                    if tokens and ({tokens[0].spelling, tokens[-1].spelling} & {"++", "--"}):
                        mode = "write"
                elif ancestor.kind in {
                    cindex.CursorKind.BINARY_OPERATOR, cindex.CursorKind.COMPOUND_ASSIGNMENT_OPERATOR,
                }:
                    children = list(ancestor.get_children())
                    if len(children) == 2 and (
                        children[0].extent.start.offset <= cursor.location.offset <
                        children[0].extent.end.offset
                    ):
                        operation = encoded_sources[source_by_path[str(cursor.location.file)].path][
                            children[0].extent.end.offset:children[1].extent.start.offset
                        ].decode("utf-8")
                        operation = re.sub(r"/\*.*?\*/|//[^\r\n]*", "", operation, flags=re.S).strip()
                        if operation in {"=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>="}:
                            mode = "write"
                elif ancestor.kind == cindex.CursorKind.VAR_DECL and (
                    ancestor.type.kind in {
                        cindex.TypeKind.LVALUEREFERENCE, cindex.TypeKind.RVALUEREFERENCE,
                    }
                    or record_contains_reference(ancestor.type)
                ):
                    return "escape", member
                elif ancestor.kind == cindex.CursorKind.INIT_LIST_EXPR and record_contains_reference(
                    ancestor.type,
                ):
                    return "escape", member
                elif ancestor.kind == cindex.CursorKind.CALL_EXPR:
                    arguments, parameters, variadic = callable_parameter_types(ancestor)
                    matched = False
                    for index_arg, argument in enumerate(arguments):
                        if not (argument.extent.start.offset <= cursor.location.offset <
                                argument.extent.end.offset):
                            continue
                        matched = True
                        if parameters is None or (index_arg >= len(parameters) and not variadic):
                            return "escape", member
                        if index_arg >= len(parameters):
                            continue
                        unwrapped = argument
                        while unwrapped.kind in {
                            cindex.CursorKind.UNEXPOSED_EXPR, cindex.CursorKind.PAREN_EXPR,
                        }:
                            children = list(unwrapped.get_children())
                            if len(children) != 1:
                                break
                            unwrapped = children[0]
                        if (unwrapped.kind == cindex.CursorKind.MEMBER_REF_EXPR
                                and parameters[index_arg].get_canonical().kind in {
                                    cindex.TypeKind.POINTER, cindex.TypeKind.LVALUEREFERENCE,
                                    cindex.TypeKind.RVALUEREFERENCE,
                                }):
                            return "escape", member
                    if not matched:
                        return "escape", member
                elif ancestor.kind == cindex.CursorKind.LAMBDA_EXPR:
                    return "escape", member
            return mode, member

        def visit(cursor, owner: str | None = None, ancestors=()) -> None:
            source = source_by_path.get(str(cursor.location.file)) if cursor.location.file else None
            if cursor.kind != cindex.CursorKind.TRANSLATION_UNIT and source is None:
                return
            eid = None
            new_owner = owner
            if cursor.kind in kinds and cursor.spelling:
                eid = span(cursor)
                node_id = symbol(cursor, tu_key)
                type_name = cursor.type.get_canonical().spelling
                if any(character in type_name for character in "\"'"):
                    type_name = cursor.type.kind.name
                type_name = type_name.replace(str(virtual_root) + "/", "").replace(str(root) + "/", "")
                props = {"translation_unit": name, "standard": profile.standard, "target": native_target,
                         "type": type_name[:500], "definition": cursor.is_definition()}
                if kinds[cursor.kind] == "function":
                    props["conversion_analysis"] = 2
                existing = nodes.get(node_id)
                ids = sorted(set((existing.evidence_ids if existing else []) + ([eid] if eid else [])))
                nodes[node_id] = Node(id=node_id, kind=kinds[cursor.kind],
                                     name=cursor.spelling[:300], evidence_ids=ids, properties=props)
                connect(source.id, node_id, "DECLARES", eid)
                if owner:
                    connect(owner, node_id, "CONTAINS", eid)
                new_owner = node_id
            elif cursor.kind in {cindex.CursorKind.CALL_EXPR, cindex.CursorKind.MEMBER_REF_EXPR}:
                referenced = cursor.referenced
                if owner and referenced:
                    eid = span(cursor)
                    local = (referenced.location.file is not None and
                             str(referenced.location.file) in source_by_path)
                    target = symbol(referenced, tu_key, external=not local)
                    if target not in nodes:
                        nodes[target] = Node(
                            id=target, kind=kinds.get(referenced.kind, "external") if local
                            else "external",
                            name=referenced.spelling[:300] or "(unnamed)",
                            properties={"translation_unit": name, "external": not local},
                        )
                    connect(owner, target, "CALLS" if cursor.kind == cindex.CursorKind.CALL_EXPR
                            else "REFERENCES", eid)
                    if cursor.kind == cindex.CursorKind.CALL_EXPR and referenced.spelling == "memcpy":
                        arguments = list(cursor.get_arguments())
                        if arguments:
                            destination = arguments[0]
                            while destination.kind == cindex.CursorKind.UNEXPOSED_EXPR:
                                children = list(destination.get_children())
                                if len(children) != 1:
                                    break
                                destination = children[0]
                            if destination.kind == cindex.CursorKind.UNARY_OPERATOR:
                                record = destination.type.get_pointee().get_declaration()
                                if record.kind == cindex.CursorKind.STRUCT_DECL:
                                    variables = [
                                        child.referenced for child in destination.walk_preorder()
                                        if child.kind == cindex.CursorKind.DECL_REF_EXPR and child.referenced
                                    ]
                                    nodes[owner].properties.setdefault("record_copies", []).append({
                                        "evidence_id": eid, "record_id": symbol(record, tu_key),
                                        "variable_id": symbol(variables[0], tu_key) if len(variables) == 1 else None,
                                        "local_destination": len(variables) == 1 and (
                                            variables[0].semantic_parent.kind in kinds
                                            and kinds[variables[0].semantic_parent.kind] == "function"
                                            and variables[0].storage_class not in {
                                                cindex.StorageClass.STATIC, cindex.StorageClass.EXTERN,
                                            }
                                            and variables[0].type.get_canonical().kind == cindex.TypeKind.RECORD
                                        ),
                                    })
            elif cursor.kind == cindex.CursorKind.DECL_REF_EXPR and owner and cursor.referenced:
                referenced_type = cursor.referenced.type.get_canonical()
                while referenced_type.kind in {
                    cindex.TypeKind.POINTER, cindex.TypeKind.LVALUEREFERENCE, cindex.TypeKind.RVALUEREFERENCE,
                }:
                    referenced_type = referenced_type.get_pointee()
                if referenced_type.get_declaration().kind == cindex.CursorKind.STRUCT_DECL:
                    access_span = span(cursor)
                    if access_span:
                        mode, member = record_access(cursor, ancestors)
                        accesses = nodes[owner].properties.setdefault("record_accesses", [])
                        if len(accesses) >= 2000:
                            raise WorkbenchError("graph_limit", "Record-access analysis exceeds its budget.")
                        accesses.append({
                            "variable_id": symbol(cursor.referenced, tu_key),
                            "evidence_id": access_span, "mode": mode, "member": member,
                        })
            bound()
            for child in cursor.get_children():
                visit(child, new_owner, (*ancestors, cursor))

        visit(tu.cursor)
    if not translation_units:
        diagnostics.append(Diagnostic(code="no_cpp", message="No C++ translation units were found."))
    return Graph(
        repo_id=repo_id, generation_id=generation, profile=profile, sources=sources,
        nodes=sorted(nodes.values(), key=lambda n: n.id),
        edges=sorted(edges.values(), key=lambda e: e.id),
        evidence=sorted(evidence.values(), key=lambda e: e.id),
        diagnostics=diagnostics, status="partial" if diagnostics else "complete",
    )


if __name__ == "__main__":
    try:
        payload = sys.stdin.read(4_000_001)
        if len(payload.encode("utf-8")) > 4_000_000:
            raise WorkbenchError("input_limit", "Parser request exceeds its budget.")
        request = json.loads(payload)
        graph = _extract(Path(request["root"]), request["repo_id"],
                         Profile.model_validate(request["profile"]), request.get("overrides"))
        print(graph.model_dump_json())
    except WorkbenchError as error:
        print(json.dumps({"error": {"code": error.code, "message": str(error)}}))
    except Exception:
        print(json.dumps({"error": {"code": "parser_failed",
                                    "message": "Native AST extraction failed safely."}}))
