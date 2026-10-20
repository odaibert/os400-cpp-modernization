"""Local registry-backed CLI; no alternate graph store or runtime cloud provider."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import zipfile
from pathlib import Path

from pydantic import ValidationError

from .core import Profile, WorkbenchError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="knowledge-workbench")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--prompt-password", action="store_true",
                        help="Read the Neo4j password using a hidden terminal prompt.")
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register", help="Register an explicit local repository root.")
    register.add_argument("root", type=Path)
    register.add_argument("--name")
    commands.add_parser("list", help="List registered repositories (no absolute paths).")
    commands.add_parser("check", help="Verify the configured local Neo4j connection.")
    for command in ("assess", "generate"):
        sub = commands.add_parser(command)
        sub.add_argument("repo_id")
        sub.add_argument("--standard", choices=("c++17", "c++20"), default="c++20")
        sub.add_argument("--define", action="append", default=[])
        sub.add_argument("--include", action="append", default=[])
        sub.add_argument("--max-files", type=int, default=200)
        sub.add_argument("--max-file-bytes", type=int, default=1_000_000)
        sub.add_argument("--max-total-bytes", type=int, default=10_000_000)
    query = commands.add_parser("query", help="Search published metadata, optionally call edges.")
    query.add_argument("repo_id")
    query.add_argument("--name", default="")
    query.add_argument("--kind", choices=("file", "function", "record", "field", "namespace", "external"))
    query.add_argument("--calls", action="store_true")
    evidence = commands.add_parser("evidence")
    evidence.add_argument("repo_id")
    evidence.add_argument("evidence_id")
    for command in ("docs", "export"):
        sub = commands.add_parser(command)
        sub.add_argument("repo_id")
        sub.add_argument("--kind", choices=("as-built", "spec-draft"), default="as-built")
        if command == "export":
            sub.add_argument("--output", type=Path, required=True,
                             help="Create a new ZIP, refusing to overwrite an existing path.")
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    remove = commands.add_parser("remove")
    remove.add_argument("repo_id")
    remove.add_argument("--yes", action="store_true", required=True)
    return parser


def _json(value) -> None:
    print(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    previous_password = os.environ.get("NEO4J_PASSWORD")
    try:
        from .service import WorkbenchService, default_state_dir
        from .job_store import JobStore

        if args.prompt_password:
            os.environ["NEO4J_PASSWORD"] = getpass.getpass("Neo4j password: ")
        service = WorkbenchService(args.state_dir or default_state_dir())
        if args.command == "register":
            with JobStore(service.registry.directory).runtime():
                repo = service.registry.register(args.root, args.name)
            _json({"id": repo.id, "name": repo.name})
        elif args.command == "list":
            _json({"repos": service.list_repos()})
        elif args.command == "check":
            _json(service.check_connection())
        elif args.command in {"assess", "generate"}:
            profile = Profile(
                standard=args.standard, defines=args.define, include_paths=args.include,
                max_files=args.max_files, max_file_bytes=args.max_file_bytes,
                max_total_bytes=args.max_total_bytes,
            )
            if args.command == "assess":
                _json(service.assess(args.repo_id, profile))
            else:
                with JobStore(service.registry.directory).runtime():
                    graph = service.generate(args.repo_id, profile)
                _json({"generation_id": graph.generation_id, "status": graph.status,
                       "sources": len(graph.sources), "nodes": len(graph.nodes),
                       "edges": len(graph.edges),
                       "diagnostics": [d.model_dump() for d in graph.diagnostics]})
        elif args.command == "query":
            graph = service.load_graph(args.repo_id)
            nodes = [node for node in graph.nodes
                     if args.name.casefold() in node.name.casefold()
                     and (not args.kind or node.kind == args.kind)]
            ids = {node.id for node in nodes}
            edges = [edge for edge in graph.edges
                     if (edge.source in ids or edge.target in ids)
                     and (not args.calls or edge.kind == "CALLS")]
            _json({"generation_id": graph.generation_id, "status": graph.status,
                   "nodes": [node.model_dump() for node in nodes],
                   "edges": [edge.model_dump() for edge in edges]})
        elif args.command == "evidence":
            _json(service.evidence(args.repo_id, args.evidence_id))
        elif args.command == "docs":
            _json(service.export_documents(args.repo_id, args.kind))
        elif args.command == "export":
            from .documents import render_documents

            graph = service.load_graph(args.repo_id)
            documents = render_documents(graph, args.kind)
            service.verify_graph(args.repo_id, graph)
            try:
                with args.output.open("xb") as stream:
                    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                        # Fixed ZIP timestamps keep repeat exports deterministic.
                        files = dict(documents)
                        files["manifest.json"] = json.dumps({
                            "repo_id": graph.repo_id, "generation_id": graph.generation_id,
                            "kind": args.kind, "sources": [s.model_dump() for s in graph.sources],
                        }, sort_keys=True, indent=2)
                        for name, content in sorted(files.items()):
                            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                            info.compress_type = zipfile.ZIP_DEFLATED
                            archive.writestr(info, content.encode("utf-8"))
            except FileExistsError:
                raise WorkbenchError("exists", "Export destination already exists; nothing overwritten.") from None
            except OSError:
                raise WorkbenchError("export_failed", "Cannot write the requested export destination.") from None
            _json({"generation_id": graph.generation_id, "files": sorted(documents)})
        elif args.command == "remove":
            with JobStore(service.registry.directory).runtime():
                service.delete(args.repo_id)
            _json({"removed": args.repo_id})
        elif args.command == "serve":
            import uvicorn

            from .api import create_app

            if not 1024 <= args.port <= 65535:
                raise WorkbenchError("invalid_port", "Port must be between 1024 and 65535.")
            uvicorn.run(create_app(service), host="127.0.0.1", port=args.port,
                        workers=1, access_log=False)
        return 0
    except WorkbenchError as error:
        print(json.dumps({"error": {"code": error.code, "message": str(error)}}), file=sys.stderr)
        return 1
    except ValidationError:
        print(json.dumps({"error": {"code": "invalid_profile",
                                    "message": "Profile contains unsupported or out-of-budget values."}}),
              file=sys.stderr)
        return 1
    finally:
        if args.prompt_password:
            if previous_password is None:
                os.environ.pop("NEO4J_PASSWORD", None)
            else:
                os.environ["NEO4J_PASSWORD"] = previous_password


if __name__ == "__main__":
    raise SystemExit(main())
