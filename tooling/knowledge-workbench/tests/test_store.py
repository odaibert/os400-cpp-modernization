import os
from copy import deepcopy
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from knowledge_workbench.core import Edge, Graph, Node, Profile, WorkbenchError
from knowledge_workbench.neo4j_store import Neo4jStore


@pytest.fixture
def graph():
    return Graph(
        repo_id="r' MATCH (n) DELETE n //", generation_id="generation",
        profile=Profile(), sources=[],
        nodes=[Node(id="a", kind="function", name="main"),
               Node(id="b", kind="function", name="callee")],
        edges=[Edge(id="call", source="a", target="b", kind="CALLS")],
        evidence=[], diagnostics=[], status="complete",
    )


class Transaction:
    def __init__(self, state, fail_at=None):
        self.state = state
        self.fail_at = fail_at
        self.calls = []

    def run(self, query, **params):
        assert isinstance(query, str), "ManagedTransaction.run only accepts string Cypher"
        text = query
        self.calls.append((text, params))
        if self.fail_at and self.fail_at in text:
            raise RuntimeError("sensitive driver message password=do-not-display")
        if "CREATE (r)-[:CURRENT]->(g)" in text:
            self.state["current"] = params["generation"]
        if "RETURN g.payload AS payload" in text:
            result = MagicMock()
            result.single.return_value = self.state.get("record")
            return result
        return MagicMock()


@pytest.fixture
def store(monkeypatch):
    driver = MagicMock()
    monkeypatch.setattr(
        "knowledge_workbench.neo4j_store.GraphDatabase.driver", lambda *a, **kw: driver
    )
    instance = Neo4jStore("bolt://127.0.0.1:7687", "neo4j", "user", "not-printed")
    session = driver.session.return_value.__enter__.return_value
    state = {"current": "old"}
    transactions = []

    def write(function, *args):
        assert 0 < function.timeout <= 20
        staged = deepcopy(state)
        transaction = Transaction(staged, state.get("fail_at"))
        transactions.append(transaction)
        function(transaction, *args)
        state.update(staged)

    session.execute_write.side_effect = write
    def read(callback):
        assert 0 < callback.timeout <= 20
        return callback(Transaction(state))

    session.execute_read.side_effect = read
    return instance, session, state, transactions


def test_atomic_parameterized_publication_with_real_entities_and_edges(store, graph):
    instance, session, state, transactions = store
    instance.publish(graph)
    assert session.execute_write.call_count == 1
    assert session.run.call_count == 3
    assert all(call.args[0].timeout > 0 for call in session.run.call_args_list)
    assert state["current"] == graph.generation_id
    calls = transactions[0].calls
    assert all(graph.repo_id not in text for text, _ in calls)
    assert all(params["repo"] == graph.repo_id for _, params in calls)
    assert any("CREATE (n:KWEntity" in text for text, _ in calls)
    assert any("CREATE (a)-[:KW_REL" in text for text, _ in calls)
    edge_index = next(i for i, (text, _) in enumerate(calls) if "CREATE (a)-[:KW_REL" in text)
    promote_index = next(i for i, (text, _) in enumerate(calls)
                         if "CREATE (r)-[:CURRENT]->(g)" in text)
    assert edge_index < promote_index
    rows = next(params["rows"] for text, params in calls if "CREATE (a)-[:KW_REL" in text)
    assert rows == [graph.edges[0].model_dump()]
    assert "generation_id <> $generation" in calls[-1][0]


@pytest.mark.parametrize("failure", ["CREATE (n:KWEntity", "CREATE (a)-[:KW_REL",
                                     "CREATE (r)-[:CURRENT]->(g)", "generation_id <>"])
def test_failed_staging_or_promotion_keeps_previous_pointer_and_redacts_errors(store, graph, failure):
    instance, _, state, _ = store
    state["fail_at"] = failure
    with pytest.raises(WorkbenchError) as error:
        instance.publish(graph)
    assert error.value.code == "database_unavailable"
    assert "sensitive" not in str(error.value)
    assert "password" not in str(error.value)
    assert state["current"] == "old"


def test_load_and_delete_namespace_and_missing_graph(store, graph):
    instance, _, state, transactions = store
    with pytest.raises(WorkbenchError) as failure:
        instance.load(graph.repo_id)
    assert failure.value.code == "not_found"
    state["record"] = {"payload": graph.model_dump_json()}
    assert instance.load(graph.repo_id) == graph
    instance.delete(graph.repo_id)
    query, params = transactions[-1].calls[-1]
    assert "DETACH DELETE n" in query
    assert "WHERE n:KWRepository OR n:KWEntity OR n:KWGeneration" in query
    assert params == {"repo": graph.repo_id}
    assert graph.repo_id not in query
    instance.close()
    instance.driver.close.assert_called_once()


@pytest.mark.parametrize("uri", [
    "bolt://example.com:7687", "neo4j://127.0.0.1:7687",
    "bolt://user:secret@127.0.0.1:7687", "bolt://127.0.0.1:7687/?password=secret",
    "bolt://[invalid", "bolt://127.0.0.1:not-a-port",
])
def test_nonloopback_routing_and_embedded_credentials_rejected(uri):
    with pytest.raises(WorkbenchError) as failure:
        Neo4jStore(uri, "neo4j")
    assert failure.value.code == "unsafe_database"
    assert "secret" not in str(failure.value)


def test_driver_privacy_and_timeouts(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr("knowledge_workbench.neo4j_store.GraphDatabase.driver", factory)
    Neo4jStore("bolt://127.0.0.1:7687", "neo4j")
    options = factory.call_args.kwargs
    assert options["telemetry_disabled"] is True
    assert options["connection_timeout"] <= 10
    assert options["connection_acquisition_timeout"] <= 10


def test_schema_failure_does_not_start_publication(store, graph):
    instance, session, state, _ = store
    session.run.side_effect = RuntimeError("sensitive authorization detail")
    with pytest.raises(WorkbenchError) as error:
        instance.publish(graph)
    assert error.value.code == "database_unavailable"
    assert "sensitive" not in str(error.value)
    session.execute_write.assert_not_called()
    assert state["current"] == "old"


def test_readiness_verifies_the_configured_database_and_redacts_errors(store):
    instance, session, _, _ = store
    session.run.return_value.single.return_value = {"ready": 1}
    instance.check_connection()
    statement = session.run.call_args.args[0]
    assert statement.text == "RETURN 1 AS ready"
    assert statement.timeout == 20
    session.run.side_effect = RuntimeError("private connection detail")
    with pytest.raises(WorkbenchError) as failure:
        instance.check_connection()
    assert failure.value.code == "database_unavailable"
    assert "private" not in str(failure.value)


@pytest.mark.skipif(os.environ.get("NEO4J_LIVE_TEST") != "1",
                    reason="Explicit live opt-in and local authentication configuration required")
def test_live_neo4j_roundtrip_and_cleanup(graph):
    from knowledge_workbench.service import WorkbenchService

    graph.repo_id = "workbench-live-test-" + uuid4().hex
    store = WorkbenchService._configured_store()
    try:
        store.check_connection()
        store.publish(graph)
        assert store.load(graph.repo_id) == graph
        store.delete(graph.repo_id)
        with pytest.raises(WorkbenchError) as failure:
            store.load(graph.repo_id)
        assert failure.value.code == "not_found"
    finally:
        try:
            store.delete(graph.repo_id)
        finally:
            store.close()
