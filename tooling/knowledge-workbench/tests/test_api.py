import io
import threading
import zipfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from knowledge_workbench.api import JobManager, create_app
from knowledge_workbench.core import Profile, WorkbenchError


class FakeService:
    def __init__(self, directory):
        self.registry = SimpleNamespace(
            get=lambda repo_id: SimpleNamespace(id=repo_id), directory=directory,
        )
        self.entered = threading.Event()
        self.release = threading.Event()

    def list_repos(self):
        return [{"id": "repo", "name": "Demo", "status": "registered"}]

    def check_connection(self):
        return {"status": "ready", "neo4j": "connected"}

    def assess(self, repo_id, profile):
        return {"sources": [], "profile": profile.model_dump(), "diagnostics": []}

    def load_graph(self, repo_id):
        raise WorkbenchError("stale_evidence", "Sources changed. Generate the graph again.")

    def verify_graph(self, repo_id, graph):
        return None

    def generate(self, repo_id, profile, cancelled, on_stage):
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise WorkbenchError("budget_exceeded", "Test generation deadline exceeded.")
        if cancelled():
            raise WorkbenchError("cancelled", "Graph generation was cancelled.")
        on_stage("publishing")
        return SimpleNamespace(status="complete")


@pytest.fixture
def service(tmp_path):
    return FakeService(tmp_path / "state")


@pytest.fixture
def client(service):
    with TestClient(create_app(service), base_url="http://127.0.0.1:8765") as client:
        yield client
        service.release.set()


def establish(client):
    response = client.get("/api/session")
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_local_authentication_and_mutation_boundary(client):
    assert client.get("/api/repos").status_code == 401
    headers = establish(client)
    assert client.get("/api/repos").json()["repos"][0]["name"] == "Demo"
    assert client.post("/api/repos/repo/assessment", json={}).status_code == 403
    assert client.post("/api/repos/repo/assessment", json={}, headers=headers).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "evil.example"},
        {"Origin": "https://evil.example"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_cross_site_localhost_requests_rejected(client, headers):
    assert client.get("/api/session", headers=headers).status_code == 403


def test_validation_errors_do_not_echo_source_or_input(client):
    headers = establish(client)
    response = client.post(
        "/api/repos/repo/assessment",
        headers=headers,
        json={"standard": "private-source-should-not-appear", "max_files": -1},
    )
    assert response.status_code == 422
    assert "private-source" not in response.text


def test_stale_graph_is_an_explicit_error(client):
    establish(client)
    response = client.get("/api/repos/repo/graph")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_evidence"
    assert response.headers["cache-control"] == "no-store"


def test_health_reports_database_failure_instead_of_configured_success(client, service):
    establish(client)
    assert client.get("/api/health").json()["neo4j"] == "connected"

    def unavailable():
        raise WorkbenchError("database_unavailable", "Start the local Neo4j container.")

    service.check_connection = unavailable
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "ready" not in response.json()
    assert client.get("/api/health/sqlite").json() == {"status": "ready", "sqlite": "connected"}


def test_sqlite_health_requires_a_session_and_queries_the_actual_store(client):
    assert client.get("/api/health/sqlite").status_code == 401
    establish(client)
    assert client.get("/api/health/sqlite").json() == {"status": "ready", "sqlite": "connected"}
    with client.app.state.jobs.store.connection() as database:
        database.execute("DROP TABLE conversions")
    response = client.get("/api/health/sqlite")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "job_store_unavailable"
    assert "ready" not in response.json()
    assert client.get("/api/health").json() == {"status": "ready", "neo4j": "connected"}


def test_large_chunked_request_is_bounded(client):
    headers = establish(client)
    response = client.post(
        "/api/repos/repo/assessment",
        headers={**headers, "Content-Type": "application/json"},
        content=iter([b'{"standard":"', b"a" * 20_000, b'"}']),
    )
    assert response.status_code == 413


def test_jobs_are_owned_and_cancellation_does_not_publish(service):
    manager = JobManager(service)
    try:
        job = manager.submit("repo", Profile(), "owner")
        assert service.entered.wait(timeout=5)
        with pytest.raises(WorkbenchError, match="session"):
            manager.get(job["id"], "other")
        with pytest.raises(WorkbenchError, match="active"):
            manager.submit("repo", Profile(), "owner")
        manager.cancel(job["id"], "owner")
        service.release.set()
    finally:
        manager.close()
    assert manager.get(job["id"], "owner")["status"] == "cancelled"


def test_conversion_cancellation_and_shared_worker_limit(service):
    from knowledge_workbench.conversion import ConversionRequest

    def convert(repo_id, payload, cancelled, on_progress):
        service.entered.set()
        assert service.release.wait(timeout=5)
        on_progress("validating", 1, 1)
        raise AssertionError("Cancelled conversion must not finish")

    service.convert = convert
    manager = JobManager(service)
    payload = ConversionRequest(paths=["main.cpp"], confirmed_big_endian_layout=True)
    try:
        job = manager.submit("repo", Profile(), "owner", conversion=payload)
        assert service.entered.wait(timeout=5)
        with pytest.raises(WorkbenchError, match="active"):
            manager.submit("repo", Profile(), "owner")
        manager.cancel(job["id"], "owner")
        service.release.set()
    finally:
        manager.close()
    assert manager.get(job["id"], "owner")["status"] == "cancelled"
    with pytest.raises(WorkbenchError):
        manager.conversion(job["id"], "owner")


def test_download_rechecks_graph_and_builds_explicit_manifest(client, service, monkeypatch):
    headers = establish(client)
    graph = SimpleNamespace(generation_id="generation", sources=[])
    service.load_graph = lambda repo_id: graph
    monkeypatch.setattr(
        "knowledge_workbench.documents.render_documents",
        lambda current, kind: {"application.md": "# Verified facts"},
    )
    response = client.get("/api/repos/repo/export?kind=as-built", headers=headers)
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"application.md", "manifest.json"}
        assert '"generation_id": "generation"' in archive.read("manifest.json").decode()
    service.load_graph = lambda repo_id: (_ for _ in ()).throw(
        WorkbenchError("stale_evidence", "Source changed.")
    )
    assert client.get("/api/repos/repo/export?kind=as-built").status_code == 409


def test_submission_waits_for_repository_removal_and_revalidates_registration(tmp_path):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError

    from knowledge_workbench.service import WorkbenchService

    entered, release, submitting = threading.Event(), threading.Event(), threading.Event()

    def delete_graph(_repo_id):
        entered.set()
        assert release.wait(timeout=5)

    store = SimpleNamespace(delete=delete_graph, close=lambda: None)
    service = WorkbenchService(tmp_path / "state", store_factory=lambda: store)
    root = tmp_path / "app"
    root.mkdir()
    repo = service.registry.register(root)
    app = create_app(service)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        headers = establish(client)
        manager = app.state.jobs

        def submit():
            submitting.set()
            return manager.submit(repo.id, Profile(), "owner")

        with ThreadPoolExecutor(max_workers=2) as threads:
            removal = threads.submit(client.delete, f"/api/repos/{repo.id}", headers=headers)
            try:
                assert entered.wait(timeout=5)
                submission = threads.submit(submit)
                assert submitting.wait(timeout=5)
                with pytest.raises(TimeoutError):
                    submission.result(timeout=0.1)
            finally:
                release.set()
            assert removal.result(timeout=5).status_code == 204
            with pytest.raises(WorkbenchError) as error:
                submission.result(timeout=5)
            assert error.value.code == "not_found"
        assert not manager.jobs
