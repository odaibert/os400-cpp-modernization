import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from knowledge_workbench.api import create_app
from knowledge_workbench.conversion import ConversionRequest, convert
from knowledge_workbench.core import WorkbenchError, build_graph
from knowledge_workbench.service import WorkbenchService

SOURCE = """#include <cstdint>
#include <cstring>
// café: byte offsets must survive a multibyte comment.
struct Sale {
    std::uint32_t order;
    std::int16_t delta;
    std::uint16_t store;
    char tag[4];
};
int main() {
    Sale value{};
    const unsigned char bytes[] = {0, 0, 0, 42, 255, 254, 0, 7, 'A', 'B', 'C', 'D'};
    std::memcpy(&value, bytes, sizeof(Sale));
    return value.order == 42 && value.delta == -2 && value.store == 7 ? 0 : 1;
}
"""


def request():
    return ConversionRequest(paths=["main.cpp"], confirmed_big_endian_layout=True)


def run_conversion(root, payload=None, cancelled=lambda: False):
    payload = payload or request()
    graph = build_graph(root, "fixture", payload.profile, cancelled=cancelled)
    return convert(root, "fixture", payload, cancelled, lambda *args: None, graph=graph)


def test_guarded_conversion_changes_real_record_values_without_overwriting_sources(tmp_path):
    source = tmp_path / "main.cpp"
    source.write_text(SOURCE, encoding="utf-8")
    progress = []
    result = convert(tmp_path, "fixture", request(), lambda: False,
                     lambda *stage: progress.append(stage),
                     graph=build_graph(tmp_path, "fixture", request().profile))
    assert not result.blocked and result.validated
    assert progress[0] == ("assessing", 0, 1)
    assert ("rewriting", 1, 1) in progress
    assert progress[-1] == ("validating", 1, 1)
    preview = result.preview(tmp_path, "main.cpp")
    assert preview["before"] == SOURCE
    assert preview["changes"] == 1
    assert "kw_migration_detail::from_big_endian(value.order)" in preview["after"]
    assert source.read_text() == SOURCE
    assert "café" not in json.dumps(result.public())
    build = tmp_path / "build"
    build.mkdir()
    generated = build / "converted.cpp"
    generated.write_text(preview["after"], encoding="utf-8")
    compiler = shutil.which("clang++")
    assert compiler
    compiled = subprocess.run(
        [compiler, "-std=c++20", str(generated), "-o", str(build / "converted")],
        capture_output=True, text=True, timeout=30,
    )
    assert compiled.returncode == 0, compiled.stderr
    assert subprocess.run([str(build / "converted")], timeout=5).returncode == 0
    assert source.read_text() == SOURCE


@pytest.mark.parametrize(("original", "replacement", "code"), [
    ("std::int16_t delta;", "float delta;", "unsupported_record"),
    ("struct Sale {", "#define PRIVATE_FEATURE 1\nstruct Sale {", "unsupported_preprocessing"),
    ("int main() {", "int IBM_api();\nint main() {\n    IBM_api();", "unsupported_call"),
    ("std::uint32_t order;", "std::uint8_t prefix;\n    std::uint32_t order;", "output_validation_failed"),
    ("    return value.order", "    value.order = value.order >> 8;\n    return value.order", "post_copy_mutation"),
])
def test_unsupported_features_and_padding_block_output(tmp_path, original, replacement, code):
    (tmp_path / "main.cpp").write_text(SOURCE.replace(original, replacement))
    result = run_conversion(tmp_path)
    assert result.blocked and not result.validated
    assert any(item.code == code for item in result.files[0].diagnostics)
    assert result.preview(tmp_path, "main.cpp")["after"] is None
    with pytest.raises(WorkbenchError) as failure:
        result.output_files(tmp_path)
    assert failure.value.code == "conversion_blocked"


def test_headers_are_preserved_and_source_changes_invalidate_previews_and_downloads(tmp_path):
    record = SOURCE[SOURCE.index("struct Sale"):SOURCE.index("int main")]
    header = tmp_path / "record.hpp"
    header.write_text("#pragma once\n#include <cstdint>\n" + record)
    (tmp_path / "main.cpp").write_text(SOURCE.replace(record, '#include "record.hpp"\n'))
    result = run_conversion(tmp_path)
    assert result.validated
    assert result.output_files(tmp_path)["converted/record.hpp"] == header.read_text()
    header.write_text(header.read_text() + "\n// changed\n")
    for operation in (lambda: result.preview(tmp_path, "main.cpp"),
                      lambda: result.output_files(tmp_path)):
        with pytest.raises(WorkbenchError) as failure:
            operation()
        assert failure.value.code == "source_changed"


def test_no_match_cancellation_and_explicit_confirmation(tmp_path):
    (tmp_path / "main.cpp").write_text("int main() { return 0; }\n")
    result = run_conversion(tmp_path)
    assert result.blocked
    assert result.files[0].diagnostics[0].code == "no_supported_conversion"
    with pytest.raises(WorkbenchError) as failure:
        run_conversion(tmp_path, cancelled=lambda: True)
    assert failure.value.code == "cancelled"
    with pytest.raises(ValueError):
        ConversionRequest(paths=["main.cpp"], confirmed_big_endian_layout=False)
    with pytest.raises(ValueError):
        ConversionRequest(paths=["README.md"], confirmed_big_endian_layout=True)


def modern_source():
    return (Path(__file__).resolve().parents[3] / "src/pos_transaction_x86.cpp").read_text()


def test_existing_portable_conversion_is_unchanged_even_with_other_helper_and_file_names(tmp_path):
    source = modern_source().replace("fromBigEndian", "decodeNetwork")
    (tmp_path / "main.cpp").write_text(source)
    result = run_conversion(tmp_path)
    assert not result.blocked and result.validated
    preview = result.preview(tmp_path, "main.cpp")
    assert preview["status"] == "unchanged"
    assert preview["changes"] == 0
    assert preview["before"] == preview["after"] == source
    assert result.output_files(tmp_path)["converted/main.cpp"] == source
    assert (tmp_path / "main.cpp").read_text() == source


@pytest.mark.parametrize(("original", "replacement"), [
    ("#include <iostream>", "#define UNREVIEWED 1\n#include <iostream>"),
    ("fromBigEndian16(txn.storeNumber)", "fromBigEndian32(txn.storeNumber)"),
    ("0x000000FF", "0x000000FE"),
    ("int main() {", "int IBM_api();\nint main() {\n    IBM_api();"),
    ("// Step 3: Process as normal", "txn.txnId = 42;\n    // Step 3: Process as normal"),
])
def test_existing_conversion_recognition_does_not_bypass_unknown_or_incorrect_code(tmp_path, original, replacement):
    source = modern_source()
    assert original in source
    (tmp_path / "main.cpp").write_text(source.replace(original, replacement))
    result = run_conversion(tmp_path)
    assert result.blocked and not result.validated
    assert result.preview(tmp_path, "main.cpp")["after"] is None
    with pytest.raises(WorkbenchError):
        result.output_files(tmp_path)


@pytest.mark.parametrize(("before_copy", "after_copy", "declaration", "code"), [
    ("", "decode(value);", """void decode(Sale& item) {
        item.order = (item.order >> 24) | ((item.order >> 8) & 0xff00u) |
            ((item.order << 8) & 0xff0000u) | (item.order << 24);
    }\n""", "record_escape"),
    ("Sale& alias = value;", "alias.order = 42;", "", "record_escape"),
    ("Sale* alias = &value;", "alias->order = 42;", "", "record_escape"),
    ("auto& alias = value.order;", "alias = 42;", "", "record_escape"),
    ("Alias alias{value.order};", "alias.order = 42;", "struct Alias { std::uint32_t& order; };\n", "record_escape"),
    ("Nested alias{{value.order}};", "alias.inner.order = 42;", "struct Alias { std::uint32_t& order; };\nstruct Nested { Alias inner; };\n", "record_escape"),
    ("", "decode(value.order);", "void decode(std::uint32_t& amount) { amount >>= 24; }\n", "record_escape"),
    ("", "auto decoder = &decode_order; decoder(value.order);", "void decode_order(std::uint32_t& x) { x = (x >> 24) | ((x >> 8) & 0xff00u) | ((x << 8) & 0xff0000u) | (x << 24); }\n", "record_escape"),
    ("", "void (&decoder)(std::uint32_t&) = decode_order; decoder(value.order);", "void decode_order(std::uint32_t& x) { x = (x >> 24) | ((x >> 8) & 0xff00u) | ((x << 8) & 0xff0000u) | (x << 24); }\n", "record_escape"),
    ("", "Decoder decoder{}; decoder(value.order);", "struct Decoder { void operator()(std::uint32_t& x) const { x >>= 24; } };\n", "record_escape"),
    ("", "++value.order;", "", "post_copy_mutation"),
    ("", "--value.order;", "", "post_copy_mutation"),
    ("", "(value.order) /* existing logic */ += 1;", "", "post_copy_mutation"),
])
def test_record_aliases_and_indirect_or_prefix_mutations_require_review(
    tmp_path, before_copy, after_copy, declaration, code,
):
    text = SOURCE.replace("int main() {", declaration + "int main() {")
    text = text.replace("    std::memcpy", f"    {before_copy}\n    std::memcpy")
    text = text.replace("    return value.order", f"    {after_copy}\n    return value.order")
    (tmp_path / "main.cpp").write_text(text)
    result = run_conversion(tmp_path)
    assert result.blocked and not result.validated
    assert any(item.code == code for item in result.files[0].diagnostics)
    assert result.preview(tmp_path, "main.cpp")["after"] is None


@pytest.mark.parametrize(("body", "expected_code"), [
    (
        """
    Sale value{};
    const unsigned char bytes[8] = {0, 0, 0, 42, 'A', 'B', 'C', 'D'};
    std::memcpy(&value, bytes, sizeof(Sale));
    std::uint32_t decoded = fromBigEndian32(value.order);
    return decoded == 42 ? 0 : 1;
""",
        "unsupported_call",
    ),
    (
        """
    Sale value{};
    const unsigned char bytes[8] = {0, 0, 0, 42, 'A', 'B', 'C', 'D'};
    std::memcpy(&value, bytes, sizeof(Sale));
    value.order = fromBigEndian32(value.order);
    return fromBigEndian32(value.order) == 42 ? 0 : 1;
""",
        "unsupported_call",
    ),
    (
        """
    Sale value{};
    const unsigned char bytes[8] = {0, 0, 0, 42, 'A', 'B', 'C', 'D'};
    std::memcpy(&value, bytes, sizeof(Sale));
    value.order = fromBigEndian32(value.order);
    Sale second{};
    std::memcpy(&second, bytes, sizeof(Sale));
    std::uint32_t decoded = fromBigEndian32(second.order);
    return (value.order + decoded) == 84 ? 0 : 1;
""",
        "unsupported_call",
    ),
    (
        """
    Sale value{};
    const unsigned char bytes[8] = {0, 0, 0, 42, 'A', 'B', 'C', 'D'};
    for (int step = 0; step < 2; ++step) {
        if (step == 1) {
            value.order = (value.order >> 24) | ((value.order >> 8) & 0xff00u)
                | ((value.order << 8) & 0xff0000u) | (value.order << 24);
            return value.order == 42 ? 0 : 1;
        }
        std::memcpy(&value, bytes, sizeof(Sale));
    }
    return 1;
""",
        "post_copy_mutation",
    ),
])
def test_unconsumed_endian_helpers_and_loop_carried_mutations_require_review(
    tmp_path, body, expected_code,
):
    helper_end = modern_source().index("struct TxnRecord")
    helper_header = modern_source()[:helper_end]
    record = "struct Sale {\n    std::uint32_t order;\n    char tag[4];\n};\n"
    source = f"{helper_header}\n{record}\nint main() {{{body}}}\n"
    (tmp_path / "main.cpp").write_text(source)
    result = run_conversion(tmp_path)
    assert result.blocked and not result.validated
    assert any(item.code == expected_code for item in result.files[0].diagnostics)
    assert result.preview(tmp_path, "main.cpp")["after"] is None


def test_multiple_copies_with_complete_decoded_prefixes_remain_supported(tmp_path):
    helper_end = modern_source().index("struct TxnRecord")
    helper_header = modern_source()[:helper_end]
    record = "struct Sale {\n    std::uint32_t order;\n    char tag[4];\n};\n"
    source = (
        f"{helper_header}\n{record}"
        "int main() {\n"
        "    Sale first{};\n"
        "    Sale second{};\n"
        "    const unsigned char bytes[8] = {0, 0, 0, 42, 'A', 'B', 'C', 'D'};\n"
        "    std::memcpy(&first, bytes, sizeof(Sale));\n"
        "    first.order = fromBigEndian32(first.order);\n"
        "    std::memcpy(&second, bytes, sizeof(Sale));\n"
        "    return (first.order + second.order) == 84 ? 0 : 1;\n"
        "}\n"
    )
    (tmp_path / "main.cpp").write_text(source)
    result = run_conversion(tmp_path)
    assert not result.blocked and result.validated
    preview = result.preview(tmp_path, "main.cpp")
    assert preview["status"] == "ready"
    assert preview["changes"] == 1
    converted = result.output_files(tmp_path)["converted/main.cpp"]
    assert converted.count("kw_migration_detail::from_big_endian(second.order)") == 1
    assert "first.order = fromBigEndian32(first.order);" in converted


def test_comment_wrapped_standalone_memcpy_with_utf8_comments_converts(tmp_path):
    source = SOURCE.replace(
        "    std::memcpy(&value, bytes, sizeof(Sale));",
        "    /* café — big-endian frame\n     */ std::memcpy(&value, bytes, sizeof(Sale)) /* résumé */;",
    )
    (tmp_path / "main.cpp").write_text(source, encoding="utf-8")
    result = run_conversion(tmp_path)
    assert not result.blocked and result.validated
    converted = result.output_files(tmp_path)["converted/main.cpp"]
    assert "/* café — big-endian frame\n     */" in converted
    assert "/* résumé */" in converted
    assert "kw_migration_detail::from_big_endian(value.order)" in converted
    non_standalone = SOURCE.replace(
        "    std::memcpy(&value, bytes, sizeof(Sale));",
        "    if (true) std::memcpy(&value, bytes, sizeof(Sale));",
    )
    (tmp_path / "main.cpp").write_text(non_standalone, encoding="utf-8")
    blocked_result = run_conversion(tmp_path)
    assert blocked_result.blocked
    assert any(item.code == "unsupported_copy" for item in blocked_result.files[0].diagnostics)


def test_platform_conditionals_in_translation_units_are_not_header_guards(tmp_path):
    (tmp_path / "main.cpp").write_text("#ifndef __linux__\n" + SOURCE + "\n#endif\n")
    result = run_conversion(tmp_path)
    assert result.blocked
    assert any(item.code == "unsupported_preprocessing" for item in result.files[0].diagnostics)


@pytest.mark.parametrize("guard", [
    "#ifndef RECORD_HPP\n{body}\n#endif\n",
    "#ifndef RECORD_HPP\n#define RECORD_HPP\n{body}\n#endif\nstruct OutsideGuard {{}};\n",
    "#ifndef __linux__\n#define __linux__\n{body}\n#endif\n",
])
def test_malformed_or_platform_header_guards_require_review(tmp_path, guard):
    record = SOURCE[SOURCE.index("struct Sale"):SOURCE.index("int main")]
    (tmp_path / "record.hpp").write_text(
        "#include <cstdint>\n" + guard.format(body=record),
    )
    (tmp_path / "main.cpp").write_text(SOURCE.replace(record, '#include "record.hpp"\n'))
    result = run_conversion(tmp_path)
    assert result.blocked
    assert any(item.code == "unsupported_preprocessing" for item in result.files[0].diagnostics)


def test_whole_header_guard_is_supported(tmp_path):
    record = SOURCE[SOURCE.index("struct Sale"):SOURCE.index("int main")]
    (tmp_path / "record.hpp").write_text(
        "#ifndef RECORD_HPP\n#define RECORD_HPP\n#include <cstdint>\n" + record + "\n#endif\n",
    )
    (tmp_path / "main.cpp").write_text(SOURCE.replace(record, '#include "record.hpp"\n'))
    result = run_conversion(tmp_path)
    assert result.validated and not result.blocked


def test_macro_only_headers_are_not_missed_by_preprocessing_checks(tmp_path):
    (tmp_path / "config.hpp").write_text("#define PRIVATE_FEATURE 1\n")
    (tmp_path / "main.cpp").write_text('#include "config.hpp"\n' + SOURCE)
    result = run_conversion(tmp_path)
    assert result.blocked
    assert any(item.code == "unsupported_preprocessing" for item in result.files[0].diagnostics)


@pytest.mark.parametrize("storage", ["static", "global"])
def test_shared_record_destinations_require_manual_review(tmp_path, storage):
    source = SOURCE.replace(
        "    Sale value{};",
        "    static Sale value{};" if storage == "static" else "",
    )
    if storage == "global":
        source = source.replace("int main() {", "Sale value{};\nint main() {")
    (tmp_path / "main.cpp").write_text(source)
    result = run_conversion(tmp_path)
    assert result.blocked
    assert any(item.code == "record_escape" for item in result.files[0].diagnostics)


def test_old_graph_analysis_and_saved_recipes_require_new_safety_checks(tmp_path):
    (tmp_path / "main.cpp").write_text(SOURCE)
    graph = build_graph(tmp_path, "fixture", request().profile)
    result = convert(tmp_path, "fixture", request(), lambda: False, lambda *args: None, graph=graph)
    assert result.validated
    for stale_recipe_version in (0, 1, 2):
        result.recipe_version = stale_recipe_version
        with pytest.raises(WorkbenchError) as error:
            result.output_files(tmp_path)
        assert error.value.code == "conversion_outdated"
    for stale_analysis in (None, 1):
        for node in graph.nodes:
            if stale_analysis is None:
                node.properties.pop("conversion_analysis", None)
            elif node.kind == "function":
                node.properties["conversion_analysis"] = stale_analysis
        result = convert(tmp_path, "fixture", request(), lambda: False, lambda *args: None, graph=graph)
        assert result.blocked
        assert any(item.code == "conversion_analysis_required" for item in result.files[0].diagnostics)


def test_unchanged_existing_conversion_still_requires_independent_layout_checks(tmp_path):
    source = modern_source().replace(
        "uint32_t txnId;", "uint16_t prefix;\n    uint32_t txnId;",
    ).replace(
        "txn.txnId       = fromBigEndian32(txn.txnId);",
        "txn.prefix = fromBigEndian16(txn.prefix);\n    txn.txnId = fromBigEndian32(txn.txnId);",
    )
    source = source.replace(
        'static_assert(sizeof(TxnRecord) == 16,\n'
        '    "TxnRecord size mismatch — check struct alignment/padding");', "",
    )
    assert "static_assert" not in source
    (tmp_path / "main.cpp").write_text(source)
    result = run_conversion(tmp_path)
    assert result.blocked and not result.validated
    assert any(item.code == "output_validation_failed" for item in result.files[0].diagnostics)


def test_mixed_real_demo_inputs_convert_legacy_and_preserve_existing_x86():
    root = Path(__file__).resolve().parents[3]
    payload = ConversionRequest(
        paths=["src/pos_transaction.cpp", "src/pos_transaction_x86.cpp"],
        confirmed_big_endian_layout=True,
    )
    result = run_conversion(root, payload)
    assert not result.blocked and result.validated
    assert [(item["status"], item["changes"]) for item in result.public()["files"]] == [
        ("ready", 1), ("unchanged", 0),
    ]
    outputs = result.output_files(root)
    assert outputs["converted/src/pos_transaction_x86.cpp"] == modern_source()
    assert "kw_migration_detail::from_big_endian" in outputs["converted/src/pos_transaction.cpp"]


def test_conversion_api_uses_stored_graph_and_enforces_ownership_and_freshness(tmp_path):
    application = tmp_path / "application"
    application.mkdir()
    source = application / "main.cpp"
    source.write_text(SOURCE)

    graphs = {}
    loads = []

    def load(repo_id):
        loads.append(repo_id)
        return graphs[repo_id]

    store = SimpleNamespace(load=load, close=lambda: None)
    service = WorkbenchService(tmp_path / "state", store_factory=lambda: store)
    repo = service.registry.register(application)
    graphs[repo.id] = build_graph(application, repo.id, request().profile)
    app = create_app(service)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        token = client.get("/api/session").json()["csrf_token"]
        route = f"/api/repos/{repo.id}/conversions"
        payload = request().model_dump()
        assert client.post(route, json=payload).status_code == 403
        response = client.post(route, json=payload, headers={"X-CSRF-Token": token})
        assert response.status_code == 202
        job = response.json()
        deadline = time.monotonic() + 20
        while job["status"] not in {"succeeded", "failed", "blocked"}:
            assert time.monotonic() < deadline
            time.sleep(0.02)
            job = client.get(f"/api/jobs/{job['id']}").json()
        assert job["status"] == "succeeded", job
        assert loads
        assert job["conversion"]["generation_id"] == graphs[repo.id].generation_id
        assert job["conversion"]["requires_review"] is True
        assert "café" not in json.dumps(job)
        endpoint = f"/api/conversions/{job['id']}"
        other = TestClient(app, base_url="http://127.0.0.1:8765")
        try:
            other.get("/api/session")
            assert other.get(f"/api/jobs/{job['id']}").status_code == 404
            assert other.get(f"{endpoint}/preview", params={"path": "main.cpp"}).status_code == 404
            assert other.get(f"{endpoint}/download").status_code == 404
        finally:
            other.close()
        preview = client.get(f"{endpoint}/preview", params={"path": "main.cpp"})
        assert preview.status_code == 200
        assert preview.json()["before"] == SOURCE
        assert client.get(f"{endpoint}/preview", params={"path": "../outside.cpp"}).status_code == 404
        downloaded = client.get(f"{endpoint}/download")
        assert downloaded.status_code == 200
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
            assert set(archive.namelist()) == {"converted/main.cpp", "manifest.json"}
            assert json.loads(archive.read("manifest.json"))["requires_review"] is True
        source.write_text(SOURCE + "\n// changed\n")
        assert client.get(f"{endpoint}/preview", params={"path": "main.cpp"}).status_code == 409
        assert client.get(f"{endpoint}/download").status_code == 409


@pytest.mark.parametrize("problem", ["missing", "partial", "profile", "stale", "repository", "unavailable"])
def test_conversion_requires_current_complete_matching_neo4j_graph(tmp_path, monkeypatch, problem):
    application = tmp_path / "application"
    application.mkdir()
    source = application / "main.cpp"
    source.write_text(SOURCE)
    graphs = {}

    def load(repo_id):
        if problem == "unavailable":
            raise WorkbenchError("database_unavailable", "Neo4j is offline.")
        if repo_id not in graphs:
            raise WorkbenchError("not_found", "Generate a graph first.")
        return graphs[repo_id]

    service = WorkbenchService(
        tmp_path / "state", store_factory=lambda: SimpleNamespace(load=load, close=lambda: None),
    )
    repo = service.registry.register(application)
    graph = build_graph(application, repo.id, request().profile)
    if problem != "missing":
        graphs[repo.id] = graph
    if problem == "partial":
        graph.status = "partial"
    if problem == "profile":
        graph.profile = graph.profile.model_copy(update={"standard": "c++17"})
    if problem == "stale":
        source.write_text(SOURCE + "\n// changed\n")
    if problem == "repository":
        graph.repo_id = "different-repository"

    def no_rebuild(*args, **kwargs):
        pytest.fail("Conversion must use Neo4j instead of rebuilding the input graph.")

    monkeypatch.setattr("knowledge_workbench.service.build_graph", no_rebuild)
    with pytest.raises(WorkbenchError) as error:
        service.convert(repo.id, request(), lambda: False, lambda *args: None)
    assert error.value.code == {
        "missing": "graph_required", "partial": "incomplete_graph",
        "profile": "graph_profile_mismatch", "stale": "source_changed",
        "repository": "graph_mismatch", "unavailable": "database_unavailable",
    }[problem]
    assert source.read_text().startswith(SOURCE)


def test_saved_conversion_recovers_after_restart_without_source_snapshots(tmp_path):
    application = tmp_path / "application"
    application.mkdir()
    source = application / "main.cpp"
    source.write_text(SOURCE)
    graphs = {}
    store = SimpleNamespace(load=lambda repo_id: graphs[repo_id], close=lambda: None)
    state = tmp_path / "state"
    service = WorkbenchService(state, store_factory=lambda: store)
    repo = service.registry.register(application)
    graph = build_graph(application, repo.id, request().profile)
    graphs[repo.id] = graph
    with TestClient(create_app(service), base_url="http://127.0.0.1:8765") as client:
        csrf = client.get("/api/session").json()["csrf_token"]
        cookie = client.cookies.get("workbench_session")
        job = client.post(f"/api/repos/{repo.id}/conversions", json=request().model_dump(),
                          headers={"X-CSRF-Token": csrf}).json()
        deadline = time.monotonic() + 20
        while job["status"] not in {"succeeded", "blocked", "failed"}:
            assert time.monotonic() < deadline
            time.sleep(0.02)
            job = client.get(f"/api/jobs/{job['id']}").json()
        assert job["status"] == "succeeded", job
    saved = (state / "conversions.sqlite3").read_bytes()
    assert cookie.encode() not in saved
    assert SOURCE.encode() not in saved
    assert "café".encode() not in saved
    restarted = WorkbenchService(state, store_factory=lambda: store)
    with TestClient(create_app(restarted), base_url="http://127.0.0.1:8765") as client:
        client.cookies.set("workbench_session", cookie, domain="127.0.0.1", path="/api")
        new_csrf = client.get("/api/session").json()["csrf_token"]
        assert client.cookies.get("workbench_session") == cookie
        assert new_csrf != csrf
        history = client.get(f"/api/repos/{repo.id}/conversions").json()["jobs"]
        assert [item["id"] for item in history] == [job["id"]]
        assert history[0]["conversion"]["generation_id"] == graph.generation_id
        assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "succeeded"
        endpoint = f"/api/conversions/{job['id']}"
        preview = client.get(f"{endpoint}/preview", params={"path": "main.cpp"})
        assert preview.status_code == 200, preview.text
        assert preview.json()["before"] == SOURCE
        assert "kw_migration_detail" in preview.json()["after"]
        response = client.get(f"{endpoint}/download")
        assert response.status_code == 200
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["generation_id"] == graph.generation_id
            assert manifest["request"]["confirmed_big_endian_layout"] is True
            assert manifest["profile"] == request().profile.model_dump()
        with pytest.raises(WorkbenchError):
            client.app.state.jobs.get(job["id"], "different-owner")
        graphs[repo.id] = graph.model_copy(update={"generation_id": "replacement"})
        assert client.get(f"{endpoint}/preview", params={"path": "main.cpp"}).status_code == 409
        assert client.get(f"{endpoint}/download").json()["error"]["code"] == "graph_changed"


@pytest.mark.skipif(os.environ.get("NEO4J_LIVE_TEST") != "1", reason="Explicit local Neo4j opt-in required")
def test_live_conversion_reads_published_neo4j_generation(tmp_path, monkeypatch):
    application = tmp_path / "application"
    application.mkdir()
    (application / "main.cpp").write_text(SOURCE)
    service = WorkbenchService(tmp_path / "state")
    repo = service.registry.register(application, "isolated-conversion-test")
    store = service._configured_store()
    try:
        store.check_connection()
        graph = service.generate(repo.id, request().profile)

        def no_rebuild(*args, **kwargs):
            pytest.fail("Conversion must read the published Neo4j graph.")

        monkeypatch.setattr("knowledge_workbench.service.build_graph", no_rebuild)
        result = service.convert(repo.id, request(), lambda: False, lambda *args: None)
        assert result.validated and not result.blocked
        assert result.generation_id == graph.generation_id
        assert result.preview(application, "main.cpp")["changes"] == 1
        service.verify_conversion(repo.id, result)
        store.delete(repo.id)
        with pytest.raises(WorkbenchError) as error:
            service.verify_conversion(repo.id, result)
        assert error.value.code == "not_found"
    finally:
        try:
            store.delete(repo.id)
        finally:
            store.close()
