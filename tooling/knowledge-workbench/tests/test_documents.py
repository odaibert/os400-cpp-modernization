import pytest

from knowledge_workbench.core import (
    Edge, Evidence, Graph, Node, Profile, Source, WorkbenchError,
)
from knowledge_workbench.documents import render_documents


@pytest.fixture
def graph():
    return Graph(
        repo_id="repo", generation_id="generation", profile=Profile(),
        sources=[Source(id="s", path="src/demo.cpp", sha256="a" * 64, size=100)],
        nodes=[Node(id="f", kind="function", name="process", evidence_ids=["e"],
                    properties={"translation_unit": "src/demo.cpp"}),
               Node(id="x", kind="external", name="external")],
        edges=[Edge(id="edge", source="f", target="x", kind="CALLS", evidence_ids=["e"])],
        evidence=[Evidence(id="e", source_id="s", start_byte=0, end_byte=30,
                           line_start=3, line_end=5)],
        diagnostics=[], status="complete",
    )


def test_deterministic_cited_observations_and_proposal_separation(graph):
    as_built = render_documents(graph, "as-built")
    draft = render_documents(graph, "spec-draft")
    assert as_built == render_documents(graph, "as-built")
    assert set(as_built) == {"as-built.md"}
    assert set(draft) == {"spec-draft.md"}
    for rendered in [as_built["as-built.md"], draft["spec-draft.md"]]:
        assert "src/demo.cpp:3-5" in rendered
        assert "a" * 64 in rendered
        assert "generation" in rendered
        assert "unverified" in rendered
    assert "**CALLS**" in as_built["as-built.md"]
    assert "**PROPOSAL, not recovered requirements.**" in draft["spec-draft.md"]
    assert "not an executed plan" in draft["spec-draft.md"]
    assert "human review required" in draft["spec-draft.md"]
    assert "Proposed review questions" not in as_built["as-built.md"]


def test_document_kind_and_unsafe_markdown(graph):
    graph.nodes[0].name = "<script>[link](url)|`bad`"
    document = render_documents(graph, "as-built")["as-built.md"]
    assert "<script>" not in document
    assert "&lt;script&gt;" in document
    assert "\\[link\\]" in document
    with pytest.raises(WorkbenchError):
        render_documents(graph, "../guide")
