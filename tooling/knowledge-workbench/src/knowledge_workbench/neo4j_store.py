"""Official-driver, loopback-only Neo4j persistence with transactional publication."""

from __future__ import annotations

import json
import threading
from urllib.parse import urlsplit

from neo4j import GraphDatabase, Query, unit_of_work

from .core import Graph, WorkbenchError

QUERY_SECONDS = 20
BATCH_SIZE = 200
_PUBLISH_LOCK = threading.Lock()


def _run(tx, text: str, **parameters):
    return tx.run(text, **parameters)


class Neo4jStore:
    def __init__(self, uri: str, database: str, username: str | None = None,
                 password: str | None = None):
        try:
            parsed = urlsplit(uri)
            host = parsed.hostname
            parsed.port
        except (ValueError, TypeError):
            raise WorkbenchError("unsafe_database", "Neo4j must use a loopback Bolt URI.") from None
        if (
            parsed.scheme not in {"bolt", "bolt+s", "bolt+ssc"}
            or host not in {"127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise WorkbenchError("unsafe_database", "Neo4j must use a loopback Bolt URI.")
        self.database = database
        try:
            self.driver = GraphDatabase.driver(
                uri, auth=(username, password) if username is not None else None,
                connection_timeout=5, connection_acquisition_timeout=8,
                max_transaction_retry_time=5, max_connection_pool_size=3,
                telemetry_disabled=True,
            )
        except Exception:
            raise WorkbenchError("database_unavailable", "Cannot configure the local Neo4j driver.") from None

    def check_connection(self) -> None:
        try:
            with self.driver.session(database=self.database) as session:
                record = session.run(Query("RETURN 1 AS ready", timeout=QUERY_SECONDS)).single()
            if record is None or record["ready"] != 1:
                raise WorkbenchError("database_unavailable", "Neo4j readiness check failed.")
        except WorkbenchError:
            raise
        except Exception:
            raise WorkbenchError(
                "database_unavailable",
                "Cannot connect to the local Neo4j database. Check Docker, the Bolt port and authentication.",
            ) from None

    def publish(self, graph: Graph) -> None:
        # The repo write lock serializes other processes; this lock also bounds this process.
        with _PUBLISH_LOCK:
            try:
                with self.driver.session(database=self.database) as session:
                    # Uniqueness also makes first publication safe across CLI processes.
                    # Schema transactions cannot be mixed with data transactions in Neo4j.
                    for statement in (
                        "CREATE CONSTRAINT kw_repository_id IF NOT EXISTS "
                        "FOR (r:KWRepository) REQUIRE r.repo_id IS UNIQUE",
                        "CREATE CONSTRAINT kw_generation_id IF NOT EXISTS "
                        "FOR (g:KWGeneration) REQUIRE (g.repo_id,g.generation_id) IS UNIQUE",
                        "CREATE CONSTRAINT kw_entity_id IF NOT EXISTS "
                        "FOR (n:KWEntity) REQUIRE (n.repo_id,n.generation_id,n.id) IS UNIQUE",
                    ):
                        session.run(Query(statement, timeout=QUERY_SECONDS)).consume()
                    session.execute_write(self._publish, graph)
            except WorkbenchError:
                raise
            except Exception:
                raise WorkbenchError("database_unavailable", "Neo4j publication failed; previous generation retained.") from None

    @staticmethod
    @unit_of_work(timeout=QUERY_SECONDS)
    def _publish(tx, graph: Graph) -> None:
        scope = {"repo": graph.repo_id, "generation": graph.generation_id}
        _run(tx, """
            MERGE (r:KWRepository {repo_id:$repo})
            SET r.publish_lock=coalesce(r.publish_lock,0)+1
        """, repo=graph.repo_id).consume()
        # All staging and pointer changes are one bounded transaction: failure rolls back
        # every staging entity, including on deterministic same-generation retries.
        _run(tx, """
            MATCH (n:KWEntity {repo_id:$repo,generation_id:$generation}) DETACH DELETE n
        """, **scope).consume()
        _run(tx, """
            MERGE (g:KWGeneration {repo_id:$repo,generation_id:$generation})
            SET g.payload=$payload, g.status=$status
        """, **scope, payload=graph.model_dump_json(), status=graph.status).consume()
        entities = (
            [{"id": n.id, "kind": n.kind, "name": n.name, "evidence_ids": n.evidence_ids,
              "properties": json.dumps(n.properties, sort_keys=True)} for n in graph.nodes]
            + [{"id": e.id, "kind": "evidence", "name": "", "evidence_ids": [],
                "properties": e.model_dump_json()} for e in graph.evidence]
        )
        for offset in range(0, len(entities), BATCH_SIZE):
            _run(tx, """
                UNWIND $rows AS row
                CREATE (n:KWEntity {repo_id:$repo,generation_id:$generation,id:row.id,
                  kind:row.kind,name:row.name,evidence_ids:row.evidence_ids,
                  metadata:row.properties})
            """, **scope, rows=entities[offset:offset + BATCH_SIZE]).consume()
        for offset in range(0, len(graph.edges), BATCH_SIZE):
            _run(tx, """
                UNWIND $rows AS row
                MATCH (a:KWEntity {repo_id:$repo,generation_id:$generation,id:row.source})
                MATCH (b:KWEntity {repo_id:$repo,generation_id:$generation,id:row.target})
                CREATE (a)-[:KW_REL {id:row.id,kind:row.kind,
                  evidence_ids:row.evidence_ids,repo_id:$repo,generation_id:$generation}]->(b)
            """, **scope, rows=[e.model_dump() for e in graph.edges[offset:offset + BATCH_SIZE]]).consume()
        _run(tx, """
            MATCH (r:KWRepository {repo_id:$repo})
            OPTIONAL MATCH (r)-[old:CURRENT]->() DELETE old
            WITH r
            MATCH (g:KWGeneration {repo_id:$repo,generation_id:$generation})
            CREATE (r)-[:CURRENT]->(g)
        """, **scope).consume()
        _run(tx, """
            MATCH (n {repo_id:$repo})
            WHERE (n:KWEntity OR n:KWGeneration) AND n.generation_id <> $generation
            DETACH DELETE n
        """, **scope).consume()

    def load(self, repo_id: str) -> Graph:
        @unit_of_work(timeout=QUERY_SECONDS)
        def read(tx):
            return _run(tx, """
                MATCH (:KWRepository {repo_id:$repo})-[:CURRENT]->(g:KWGeneration)
                RETURN g.payload AS payload
            """, repo=repo_id).single()

        try:
            with self.driver.session(database=self.database) as session:
                record = session.execute_read(read)
            if record is None:
                raise WorkbenchError("not_found", "No published graph exists for this repository.")
            return Graph.model_validate_json(record["payload"])
        except WorkbenchError:
            raise
        except Exception:
            raise WorkbenchError("database_unavailable", "Cannot load the local Neo4j graph.") from None

    def delete(self, repo_id: str) -> None:
        @unit_of_work(timeout=QUERY_SECONDS)
        def remove(tx):
            _run(tx, """
                MATCH (r:KWRepository {repo_id:$repo})
                SET r.publish_lock=coalesce(r.publish_lock,0)+1
                WITH r MATCH (n {repo_id:$repo})
                WHERE n:KWRepository OR n:KWEntity OR n:KWGeneration
                DETACH DELETE n
            """, repo=repo_id).consume()

        with _PUBLISH_LOCK:
            try:
                with self.driver.session(database=self.database) as session:
                    session.execute_write(remove)
            except Exception:
                raise WorkbenchError("database_unavailable", "Neo4j deletion failed.") from None

    def close(self) -> None:
        try:
            self.driver.close()
        except Exception:
            raise WorkbenchError("database_unavailable", "Cannot close the local Neo4j connection.") from None
