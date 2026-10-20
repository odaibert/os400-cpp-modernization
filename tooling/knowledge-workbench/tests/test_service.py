import stat
from types import SimpleNamespace

import pytest

from knowledge_workbench.core import Profile, WorkbenchError
from knowledge_workbench.service import Registry, WorkbenchService


def test_registry_explicit_roots_are_durable_and_private(tmp_path):
    root = tmp_path / "application"
    root.mkdir()
    state = tmp_path / "state"
    repository = Registry(state).register(root, "Test application")
    loaded = Registry(state).get(repository.id)
    assert loaded.root == root
    assert loaded.name == "Test application"
    assert Registry(state).register(root).id == repository.id
    assert stat.S_IMODE((state / "repositories.json").stat().st_mode) == 0o600


def test_registry_rejects_symlink_root_and_corrupt_registry(tmp_path):
    root = tmp_path / "application"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root)
    registry = Registry(tmp_path / "state")
    with pytest.raises(WorkbenchError, match="symlinks"):
        registry.register(alias)
    registry.directory.mkdir()
    registry.path.write_text('{"unexpected":"not a registry"}')
    with pytest.raises(WorkbenchError, match="registry"):
        registry.list()


def test_missing_credentials_fail_without_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("NEO4J_AUTH_MODE", raising=False)
    monkeypatch.delenv("NEO4J_USERNAME", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    service = WorkbenchService(tmp_path / "state")
    root = tmp_path / "application"
    root.mkdir()
    repository = service.registry.register(root)
    with pytest.raises(WorkbenchError) as error:
        service.load_graph(repository.id)
    assert error.value.code == "credentials_required"


def test_no_auth_requires_explicit_mode_and_ignores_credentials(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    factory = MagicMock()
    monkeypatch.setattr("knowledge_workbench.service.Neo4jStore", factory)
    monkeypatch.setenv("NEO4J_AUTH_MODE", "none")
    monkeypatch.setenv("NEO4J_USERNAME", "unused-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "unused-test-value")
    monkeypatch.setenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    monkeypatch.setenv("NEO4J_DATABASE", "neo4j")
    service = WorkbenchService(tmp_path / "state")
    assert service.check_connection() == {"status": "ready", "neo4j": "connected"}
    factory.assert_called_once_with(
        uri="bolt://127.0.0.1:7687", database="neo4j", username=None, password=None,
    )
    factory.return_value.check_connection.assert_called_once()
    factory.return_value.close.assert_called_once()


def test_unknown_auth_mode_is_not_an_unauthenticated_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("NEO4J_AUTH_MODE", "disabled-by-typo")
    service = WorkbenchService(tmp_path / "state")
    with pytest.raises(WorkbenchError) as error:
        service.check_connection()
    assert error.value.code == "invalid_database_configuration"


def test_cancellation_between_extraction_and_publication(tmp_path, monkeypatch):
    root = tmp_path / "application"
    root.mkdir()
    published = []
    store = SimpleNamespace(publish=published.append, close=lambda: None)
    service = WorkbenchService(tmp_path / "state", store_factory=lambda: store)
    repository = service.registry.register(root)
    monkeypatch.setattr("knowledge_workbench.service.build_graph", lambda *args, **kwargs: object())
    monkeypatch.setattr("knowledge_workbench.service.verify_sources", lambda *args: None)
    with pytest.raises(WorkbenchError) as error:
        service.generate(repository.id, Profile(), cancelled=lambda: True)
    assert error.value.code == "cancelled"
    assert published == []


def test_stale_store_generation_is_not_returned(tmp_path, monkeypatch):
    root = tmp_path / "application"
    root.mkdir()
    closed = []
    store = SimpleNamespace(load=lambda repo_id: object(), close=lambda: closed.append(True))
    service = WorkbenchService(tmp_path / "state", store_factory=lambda: store)
    repository = service.registry.register(root)

    def stale(*args):
        raise WorkbenchError("stale_evidence", "Changed source.")

    monkeypatch.setattr("knowledge_workbench.service.verify_sources", stale)
    with pytest.raises(WorkbenchError, match="Changed"):
        service.load_graph(repository.id)
    assert closed == [True]
