import stat
import time

import pytest
from fastapi.testclient import TestClient

from knowledge_workbench.api import create_app
from knowledge_workbench.conversion import ConversionRequest
from knowledge_workbench.core import WorkbenchError
from knowledge_workbench.job_store import ConversionRecord, JobStore, owner_hash
from knowledge_workbench.service import WorkbenchService


def record(repo_id, owner):
    return ConversionRecord(
        id="interrupted-job", repo_id=repo_id, owner_hash=owner_hash(owner),
        status="running", stage="rewriting", completed_files=1, total_files=2,
        request=ConversionRequest(paths=["one.cpp", "two.cpp"], confirmed_big_endian_layout=True),
        result=None, error=None, created_at=time.time(), updated_at=time.time(),
    )


def test_restart_marks_unfinished_jobs_interrupted_and_preserves_ownership(tmp_path):
    state = tmp_path / "state"
    root = tmp_path / "app"
    root.mkdir()
    service = WorkbenchService(state)
    repo = service.registry.register(root)
    store = JobStore(state)
    cookie = store.session("")
    store.save(record(repo.id, cookie))
    app = create_app(service)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        client.cookies.set("workbench_session", cookie, domain="127.0.0.1", path="/api")
        csrf = client.get("/api/session").json()["csrf_token"]
        result = client.get("/api/jobs/interrupted-job").json()
        assert result["status"] == "interrupted"
        assert result["completed_files"] == 1 and result["total_files"] == 2
        assert result["error"]["code"] == "job_interrupted"
        assert result["request"]["paths"] == ["one.cpp", "two.cpp"]
        assert client.post(
            "/api/jobs/interrupted-job/cancel", headers={"X-CSRF-Token": csrf},
        ).json()["status"] == "interrupted"
        assert client.get("/api/conversions/interrupted-job/download").status_code == 409
        with pytest.raises(WorkbenchError):
            app.state.jobs.get("interrupted-job", "someone-else")
        assert app.state.jobs.history(repo.id, "someone-else") == []
        app.state.jobs.forget(repo.id)
        assert client.get("/api/jobs/interrupted-job").status_code == 404
        assert store.list(repo.id, owner_hash(cookie)) == []
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_only_one_runtime_can_recover_a_state_directory(tmp_path):
    first = JobStore(tmp_path / "state")
    second = JobStore(tmp_path / "state")
    first.acquire_runtime()
    try:
        with pytest.raises(WorkbenchError) as error:
            second.acquire_runtime()
        assert error.value.code == "job_store_busy"
    finally:
        first.release_runtime()
    second.acquire_runtime()
    second.release_runtime()


def test_corrupt_or_symlink_history_is_not_replaced_with_empty_success(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    database = state / "conversions.sqlite3"
    database.write_bytes(b"not-a-database")
    with pytest.raises(WorkbenchError) as error:
        JobStore(state)
    assert error.value.code == "job_store_unavailable"
    database.unlink()
    target = tmp_path / "other"
    target.write_text("untouched")
    database.symlink_to(target)
    with pytest.raises(WorkbenchError) as error:
        JobStore(state)
    assert error.value.code == "forbidden_path"
    assert target.read_text() == "untouched"


def test_expired_session_cannot_recover_private_jobs(tmp_path):
    store = JobStore(tmp_path / "state")
    token = store.session("")
    assert store.valid_session(token)
    with store.connection() as database:
        database.execute("UPDATE sessions SET expires_at=0")
    assert not store.valid_session(token)
    replacement = store.session(token)
    assert replacement != token
    assert token.encode() not in store.path.read_bytes()


def test_health_rejects_an_incompatible_history_schema(tmp_path):
    store = JobStore(tmp_path / "state")
    assert store.check_connection() == {"status": "ready", "sqlite": "connected"}
    with store.connection() as database:
        database.execute("PRAGMA user_version = 2")
    with pytest.raises(WorkbenchError) as error:
        store.check_connection()
    assert error.value.code == "job_store_invalid"


def test_cli_removal_deletes_only_its_private_history(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace

    from knowledge_workbench.cli import main

    state = tmp_path / "state"
    removed = []
    service = WorkbenchService(state, store_factory=lambda: SimpleNamespace(
        delete=removed.append, close=lambda: None,
    ))
    first_root, second_root = tmp_path / "first", tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = service.registry.register(first_root)
    second = service.registry.register(second_root)
    store = JobStore(state)
    store.save(record(first.id, "owner"))
    store.save(record(second.id, "owner").model_copy(update={"id": "unrelated-job"}))
    monkeypatch.setattr("knowledge_workbench.service.WorkbenchService", lambda *args: service)
    assert main(["--state-dir", str(state), "remove", first.id, "--yes"]) == 0
    assert removed == [first.id]
    assert store.list(first.id, owner_hash("owner")) == []
    assert store.get("unrelated-job", owner_hash("owner")).repo_id == second.id
    with pytest.raises(WorkbenchError):
        service.registry.get(first.id)
    assert service.registry.get(second.id).id == second.id
    assert first_root.exists() and second_root.exists()
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("command", ["remove", "generate", "register"])
def test_mutating_cli_commands_cannot_race_an_active_server(tmp_path, monkeypatch, capsys, command):
    from knowledge_workbench.cli import main

    service = WorkbenchService(tmp_path / "state")
    root = tmp_path / "app"
    root.mkdir()
    repo = service.registry.register(root)
    monkeypatch.setattr("knowledge_workbench.service.WorkbenchService", lambda *args: service)
    with TestClient(create_app(service), base_url="http://127.0.0.1:8765"):
        arguments = [command, str(root)] if command == "register" else [command, repo.id]
        if command == "remove":
            arguments.append("--yes")
        assert main(arguments) == 1
        assert "job_store_busy" in capsys.readouterr().err
        assert service.registry.get(repo.id).id == repo.id
