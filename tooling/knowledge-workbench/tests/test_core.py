import pytest

from knowledge_workbench.core import (
    Graph, Profile, WorkbenchError, evidence_excerpt, inventory_sources, verify_sources,
)


def test_inventory_scope_and_utf8_budgets(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/main.cpp").write_text("// café\nint main() {}", encoding="utf-8")
    for directory in ["tooling", ".git", ".squad", "build", "exports", "node_modules",
                      "docs/reinvention", ".private"]:
        path = tmp_path / directory
        path.mkdir(parents=True, exist_ok=True)
        (path / "hidden.cpp").write_bytes(b"\xff")
    (tmp_path / ".env").write_bytes(b"\xff")
    sources = inventory_sources(tmp_path, Profile())
    assert [s.path for s in sources] == ["src/main.cpp"]
    assert sources[0].size == len("// café\nint main() {}".encode())
    with pytest.raises(WorkbenchError, match="byte limit|bounded regular"):
        inventory_sources(tmp_path, Profile(max_file_bytes=5))
    (tmp_path / "src/main.cpp").write_bytes(b"\xff")
    with pytest.raises(WorkbenchError) as failure:
        inventory_sources(tmp_path, Profile())
    assert failure.value.code == "encoding"


def test_symlinks_and_forbidden_reads(tmp_path):
    from knowledge_workbench.core import read_source

    (tmp_path / "real.cpp").write_text("int real;", encoding="utf-8")
    (tmp_path / "link.cpp").symlink_to(tmp_path / "real.cpp")
    with pytest.raises(WorkbenchError):
        inventory_sources(tmp_path, Profile())
    for path in [".env", "../outside.cpp", "/etc/passwd", ".git/file.cpp",
                 "tooling/secret.cpp", r"src\main.cpp"]:
        with pytest.raises(WorkbenchError):
            read_source(tmp_path, path, 100)
    (tmp_path / "link.cpp").unlink()
    (tmp_path / "linked").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(WorkbenchError):
        inventory_sources(tmp_path, Profile())


def test_only_cpp_sources_and_headers_are_read_and_tracked(tmp_path):
    from knowledge_workbench.core import read_source

    (tmp_path / "main.cpp").write_text('#include "record.hpp"\nint main() {}')
    (tmp_path / "record.hpp").write_text("struct Record {};")
    (tmp_path / "docs").mkdir()
    for relative in ("README.md", "docs/guide.md", "CMakeLists.txt"):
        (tmp_path / relative).write_bytes(b"\xff" * 1000)
        with pytest.raises(WorkbenchError):
            read_source(tmp_path, relative, 100)
    sources = inventory_sources(tmp_path, Profile(max_file_bytes=100, max_total_bytes=100))
    assert [source.path for source in sources] == ["main.cpp", "record.hpp"]
    graph = Graph(
        repo_id="code-only", generation_id="generation", profile=Profile(),
        sources=sources, nodes=[], edges=[], evidence=[], diagnostics=[], status="complete",
    )
    (tmp_path / "docs/guide.md").write_text("Documentation changed.")
    verify_sources(tmp_path, graph)


@pytest.mark.parametrize("change", ["modify", "delete", "add"])
def test_full_manifest_freshness(tmp_path, change):
    (tmp_path / "main.cpp").write_text("int main() {}", encoding="utf-8")
    sources = inventory_sources(tmp_path, Profile())
    graph = Graph(repo_id="r", generation_id="g", profile=Profile(), sources=sources,
                  nodes=[], edges=[], evidence=[], diagnostics=[], status="complete")
    verify_sources(tmp_path, graph)
    if change == "modify":
        (tmp_path / "main.cpp").write_text("int other() {}", encoding="utf-8")
    elif change == "delete":
        (tmp_path / "main.cpp").unlink()
    else:
        (tmp_path / "added.hpp").write_text("struct Added {};", encoding="utf-8")
    with pytest.raises(WorkbenchError) as failure:
        verify_sources(tmp_path, graph)
    assert failure.value.code == "source_changed"
    with pytest.raises(WorkbenchError) as failure:
        evidence_excerpt(tmp_path, graph, "anything")
    assert failure.value.code == "source_changed"


def test_include_profiles_reject_path_escapes():
    for path in ["../", "/etc", ".env", ".git", "build"]:
        with pytest.raises((WorkbenchError, ValueError)):
            Profile(include_paths=[path])
    assert Profile(include_paths=["."]).include_paths == ["."]
    for value in ["@secret", "FOO=a b", "FOO=../bad", "-include/etc/passwd"]:
        with pytest.raises(ValueError):
            Profile(defines=[value])


def test_cli_registry_assessment_and_explicit_nonoverwriting_zip(tmp_path, monkeypatch, capsys):
    import json
    import zipfile
    from unittest.mock import MagicMock

    from knowledge_workbench import cli, service as service_module
    from knowledge_workbench.core import build_graph
    from knowledge_workbench.service import WorkbenchService

    root = tmp_path / "application"
    root.mkdir()
    (root / "main.cpp").write_text("int main() { return 7; }", encoding="utf-8")
    store = MagicMock()
    service = WorkbenchService(tmp_path / "state", store_factory=lambda: store)
    monkeypatch.setattr(service_module, "WorkbenchService", lambda *args, **kwargs: service)
    assert cli.main(["register", str(root), "--name", "Sample"]) == 0
    repository_id = json.loads(capsys.readouterr().out)["id"]
    assert cli.main(["assess", repository_id]) == 0
    assessment = json.loads(capsys.readouterr().out)
    assert assessment["sources"][0]["path"] == "main.cpp"
    graph = build_graph(root, repository_id, Profile())
    store.load.return_value = graph
    target = tmp_path / "as-built.zip"
    assert cli.main(["export", repository_id, "--output", str(target)]) == 0
    capsys.readouterr()
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        document = archive.read("as-built.md").decode()
        assert manifest["generation_id"] == graph.generation_id
        assert graph.generation_id in document
        assert "return 7" not in document
    before = target.read_bytes()
    assert cli.main(["export", repository_id, "--output", str(target)]) == 1
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "exists"
    assert target.read_bytes() == before
    (root / "added.hpp").write_text("struct Added {};", encoding="utf-8")
    other = tmp_path / "stale.zip"
    assert cli.main(["export", repository_id, "--output", str(other)]) == 1
    assert not other.exists()
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "source_changed"
