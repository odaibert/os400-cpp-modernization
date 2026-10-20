import io
import time
import zipfile

from fastapi.testclient import TestClient

from knowledge_workbench.api import create_app
from knowledge_workbench.core import WorkbenchError
from knowledge_workbench.service import WorkbenchService


class TestStore:
    __test__ = False

    def __init__(self):
        self.graphs = {}

    def publish(self, graph):
        self.graphs[graph.repo_id] = graph

    def load(self, repo_id):
        if repo_id not in self.graphs:
            raise WorkbenchError("not_found", "Generate the graph first.")
        return self.graphs[repo_id]

    def delete(self, repo_id):
        self.graphs.pop(repo_id, None)

    def close(self):
        return None


def test_local_cpp_to_evidence_docs_and_stale_rejection(tmp_path):
    application = tmp_path / "application"
    application.mkdir()
    source = application / "main.cpp"
    (application / "record.hpp").write_text("struct Record { unsigned amount; };\n")
    (application / "README.md").write_text("Do not index this documentation.\n")
    (application / "CMakeLists.txt").write_text("# Not a graph input\n")
    source.write_text(
        '#include "record.hpp"\n'
        'const char* banner = "do-not-retain-source-literal";\n'
        "unsigned convert(unsigned value) { return value; }\n"
        "int main() { return convert(7); }\n",
        encoding="utf-8",
    )
    store = TestStore()
    service = WorkbenchService(tmp_path / "state", store_factory=lambda: store)
    repository = service.registry.register(application)
    endpoint = f"/api/repos/{repository.id}"
    with TestClient(create_app(service), base_url="http://127.0.0.1:8765") as client:
        headers = {"X-CSRF-Token": client.get("/api/session").json()["csrf_token"]}
        assessment = client.post(f"{endpoint}/assessment", json={}, headers=headers)
        assert assessment.status_code == 200
        assert [source["path"] for source in assessment.json()["sources"]] == [
            "main.cpp", "record.hpp",
        ]
        start = client.post(f"{endpoint}/generations", json={}, headers=headers)
        assert start.status_code == 202
        deadline = time.monotonic() + 15
        job = start.json()
        while job["status"] not in {"succeeded", "partial", "failed", "cancelled"}:
            assert time.monotonic() < deadline, "Generation exceeded the test deadline"
            time.sleep(0.02)
            job = client.get(f"/api/jobs/{job['id']}").json()
        assert job["status"] in {"succeeded", "partial"}, job
        response = client.get(f"{endpoint}/graph")
        assert response.status_code == 200
        assert "do-not-retain-source-literal" not in response.text
        graph = response.json()
        assert {source["path"] for source in graph["sources"]} == {"main.cpp", "record.hpp"}
        assert any(node["name"] == "convert" for node in graph["nodes"])
        assert any(edge["kind"] == "CALLS" for edge in graph["edges"])
        evidence_id = graph["evidence"][0]["id"]
        evidence = client.get(f"{endpoint}/evidence/{evidence_id}")
        assert evidence.status_code == 200
        assert evidence.json()["path"] == "main.cpp"
        assert evidence.json()["text"]
        for kind in ("as-built", "spec-draft"):
            preview = client.post(
                f"{endpoint}/exports", json={"kind": kind}, headers=headers
            )
            assert preview.status_code == 200
            assert preview.json()["files"]
            exported = client.get(f"{endpoint}/export?kind={kind}")
            assert exported.status_code == 200
            with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
                assert "manifest.json" in archive.namelist()
        source.write_text("int main() { return 0; }\n", encoding="utf-8")
        assert client.get(f"{endpoint}/graph").status_code == 409
        assert client.get(f"{endpoint}/evidence/{evidence_id}").status_code == 409
        assert client.get(f"{endpoint}/export?kind=as-built").status_code == 409
        assert client.delete(endpoint, headers=headers).status_code == 204
        assert store.graphs == {}
        assert source.exists()
