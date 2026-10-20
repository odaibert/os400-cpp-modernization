from pathlib import Path

import pytest

from knowledge_workbench.core import Profile, WorkbenchError, build_graph, evidence_excerpt


def test_native_duplicate_symbols_calls_fields_and_exact_utf8_evidence(tmp_path):
    text = (
        "// café — offsets are bytes\n"
        "struct TxnRecord { int amount; };\n"
        "int processTxn(TxnRecord t) { return t.amount; }\n"
        "int main() { TxnRecord x{}; return processTxn(x); }\n"
    )
    for name in ["legacy.cpp", "modern.cpp"]:
        (tmp_path / name).write_text(text, encoding="utf-8")
    graph = build_graph(tmp_path, "fixture", Profile())
    assert graph.status == "complete"
    for name, kind in [("main", "function"), ("processTxn", "function"),
                       ("TxnRecord", "record"), ("amount", "field")]:
        matches = [n for n in graph.nodes if n.name == name and n.kind == kind]
        assert len(matches) == 2
        assert len({n.id for n in matches}) == 2
    nodes = {node.id: node for node in graph.nodes}
    calls = [e for e in graph.edges if e.kind == "CALLS"
             and nodes[e.target].name == "processTxn"]
    assert len(calls) == 2
    for edge in calls:
        assert nodes[edge.source].name == "main"
        assert nodes[edge.source].properties["translation_unit"] == nodes[
            edge.target
        ].properties["translation_unit"]
        excerpt = evidence_excerpt(tmp_path, graph, edge.evidence_ids[0])
        assert excerpt["text"] == "processTxn(x)"
        assert excerpt["line_start"] == 4
    references = [e for e in graph.edges if e.kind == "REFERENCES"
                  and nodes[e.target].name == "amount"]
    assert len(references) == 2
    assert "café" not in graph.model_dump_json()
    assert build_graph(tmp_path, "fixture", Profile()).generation_id == graph.generation_id


@pytest.mark.parametrize("directive", [
    '#include "/etc/passwd"', '#include "../outside.hpp"', '#include ".env"',
    '#define HEADER "/etc/passwd"\n#include HEADER',
    '#include_next <iostream>', '#import <iostream>',
    '#pragma clang __debug crash', '#include \\\n"/etc/passwd"',
    'const char *trick="/*";\n#include "/etc/passwd"\nconst char *end="*/";',
    '\ufeff#include "/etc/passwd"', '\x00#include "/etc/passwd"',
    '#inc\\ \nlude "/etc/passwd"', '#inc\\\rlude "/etc/passwd"',
])
def test_hostile_preprocessor_rejected_before_ast(tmp_path, directive):
    (tmp_path / "main.cpp").write_text(directive + "\nint main() {}", encoding="utf-8")
    with pytest.raises(WorkbenchError) as failure:
        build_graph(tmp_path, "hostile", Profile())
    assert failure.value.code in {"unsafe_path", "unsafe_include", "unsupported_input"}
    assert "/etc/passwd" not in str(failure.value)


def test_transitive_header_preflight_and_missing_header_diagnostics(tmp_path):
    (tmp_path / "main.cpp").write_text('#include "nested.hpp"\nint main() {}', encoding="utf-8")
    (tmp_path / "nested.hpp").write_text('#include ".env"', encoding="utf-8")
    with pytest.raises(WorkbenchError):
        build_graph(tmp_path, "r", Profile())
    (tmp_path / "nested.hpp").write_text('#include "does-not-exist.hpp"', encoding="utf-8")
    graph = build_graph(tmp_path, "r", Profile())
    assert graph.status == "partial"
    assert any(d.code == "compiler_error" for d in graph.diagnostics)
    assert "does-not-exist" not in graph.model_dump_json()


def test_warning_is_partial_without_source_leak(tmp_path):
    (tmp_path / "main.cpp").write_text("#warning VERY_PRIVATE_DIAGNOSTIC\nint main() {}", encoding="utf-8")
    graph = build_graph(tmp_path, "r", Profile())
    assert graph.status == "partial"
    assert any(d.code == "compiler_warning" for d in graph.diagnostics)
    assert "VERY_PRIVATE_DIAGNOSTIC" not in graph.model_dump_json()


def test_cancellation_and_hard_parser_deadline(tmp_path, monkeypatch):
    from knowledge_workbench import parser

    (tmp_path / "main.cpp").write_text("int main() {}", encoding="utf-8")
    with pytest.raises(WorkbenchError) as failure:
        build_graph(tmp_path, "r", Profile(), cancelled=lambda: True)
    assert failure.value.code == "cancelled"
    monkeypatch.setattr(parser, "PARSER_SECONDS", 0)
    with pytest.raises(WorkbenchError) as failure:
        build_graph(tmp_path, "r", Profile())
    assert failure.value.code == "parser_timeout"


def test_native_repository_samples_without_modification():
    root = Path(__file__).resolve().parents[3]
    graph = build_graph(root, "repository-smoke", Profile())
    assert {"src/pos_transaction.cpp", "src/pos_transaction_x86.cpp"} <= {
        s.path for s in graph.sources
    }
    assert len([n for n in graph.nodes if n.kind == "record" and n.name == "TxnRecord"]) == 2
    assert len([n for n in graph.nodes if n.kind == "function" and n.name == "processTxn"]) == 2
    names = {n.id: n.name for n in graph.nodes}
    assert any(e.kind == "CALLS" and names[e.source] == "processTxn"
               and names[e.target] == "fromBigEndian32" for e in graph.edges)
    assert len([n for n in graph.nodes if n.kind == "field"]) == 10


def test_explicit_include_profile_and_header_symbol_tu_isolation(tmp_path):
    (tmp_path / "include").mkdir()
    (tmp_path / "include/record.hpp").write_text(
        "struct Record { unsigned amount; };\n"
        "inline unsigned convert(Record r) { return r.amount; }\n", encoding="utf-8",
    )
    for name in ["one.cpp", "two.cpp"]:
        (tmp_path / name).write_text(
            '#include <record.hpp>\nint main(){ Record r{}; return convert(r); }',
            encoding="utf-8",
        )
    missing = build_graph(tmp_path, "r", Profile())
    configured = build_graph(tmp_path, "r", Profile(include_paths=["include"]))
    assert missing.status == "partial"
    assert configured.status == "complete"
    assert missing.generation_id != configured.generation_id
    records = [n for n in configured.nodes if n.name == "Record" and n.kind == "record"]
    assert len(records) == 2 and len({n.id for n in records}) == 2
    for record in records:
        assert evidence_excerpt(tmp_path, configured, record.evidence_ids[0])["path"] == "include/record.hpp"


def test_initializer_and_decltype_literal_not_retained(tmp_path):
    (tmp_path / "main.cpp").write_text(
        'struct Record { const char* label = "PRIVATE_INITIALIZER"; };\n'
        'auto typed() -> decltype("PRIVATE_TYPE_LITERAL") { return "PRIVATE_TYPE_LITERAL"; }\n',
        encoding="utf-8",
    )
    graph = build_graph(tmp_path, "r", Profile())
    assert graph.status == "complete"
    assert any(n.name == "label" for n in graph.nodes)
    assert "PRIVATE_INITIALIZER" not in graph.model_dump_json()
    assert "PRIVATE_TYPE_LITERAL" not in graph.model_dump_json()
    assert str(tmp_path) not in graph.model_dump_json()


def test_graph_entity_budget_fails_explicitly(tmp_path, monkeypatch):
    from knowledge_workbench import parser

    (tmp_path / "main.cpp").write_text("int main() {}", encoding="utf-8")
    monkeypatch.setattr(parser, "MAX_NODES", 1)
    with pytest.raises(WorkbenchError) as failure:
        parser._extract(tmp_path, "r", Profile())
    assert failure.value.code == "graph_limit"
