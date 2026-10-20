# Technology research: an evidence-first C++ migration companion

**Planning context and access date: 2026-10-19.** Research by Switch, Retrieval & Agent Engineer. This is a proposal, not authorization to implement, buy services, upload source code, or deploy infrastructure.

> **Historical research:** the alternatives and experiments below are proposals,
> not a current storage inventory. The implemented workbench uses Neo4j for graphs
> and SQLite for private conversion history. See the
> [current implementation summary](README.md#current-implementation-versus-proposal)
> before applying these recommendations.

## Recommendation and boundaries

Start with a small, local, source-cited migration-understanding experiment, not a graph-platform rewrite. README.md and CMakeLists.txt describe two C++ executables (`pos_legacy`, C++17; `pos_modern`, C++20) and migration guides. They do not establish an existing retrieval platform, graph service, ingestion pipeline, or benchmark suite. The source files were not inspected for this research; the schema and sample questions below are hypotheses to validate, not extracted code facts.

Use structured JSON and exact text lookup first; consider SQLite for indexed text and explicit relationships. If measured multi-hop questions justify a graph database, evaluate **local Neo4j alone before Neo4j plus Pinecone**. Neo4j has graph traversal, full-text indexes, and vector indexes; a separate vector database is not technically necessary for the proposed retrieval MVP [S5–S8]. This does not mean Neo4j implements extraction, embeddings, answer validation, or agent governance automatically.

Keep the working migration examples intact. No external database, multi-agent framework, paid model, cloud provisioning, or new runtime is approved by this document. No repository content or credentials were sent to external services during research: only public documentation URLs were fetched.

## Source status and evidence register

All URLs below were attempted through public web fetching in this session, with access recorded against the supplied planning date **2026-10-19**. These are live responses, not an archived historical snapshot. If a live site's actual revision or access date differs from the planning context, that live version must not be represented as proof of availability on an earlier date; recheck versioned documentation before implementation. URL tracking parameters and the supplied browser-reader wrapper are omitted.

| ID | Canonical source | Access status on 2026-10-19 and evidentiary limits |
|---|---|---|
| S1 | [Neo4j knowledge graphs](https://neo4j.com/use-cases/knowledge-graph/) | Accessible vendor use-case page. Supports the vendor's property-graph positioning, not comparative performance or suitability for this repository. |
| S2 | [Pinecone Nexus trial](https://www.pinecone.io/lp/nexus-trial/) | Accessible trial-request landing page. Says requests are reviewed and the team follows up. No trial requested. Marketing task-completion, speed, and token claims were not independently verified. |
| S3 | [Adnan Masood, Graph Engineering for AI Agents](https://medium.com/@adnanmasood/graph-engineering-for-ai-agents-the-practitioners-guide-to-designing-multi-agent-systems-as-f9a4559aa693) | Partial: fetch returned only a `tl:dr;` summary, not the complete article. Full-body availability/paywall status could not be established. No access-control workaround attempted; detailed examples, numerical claims, and full argument remain unverified. |
| S4 | [OpenClaw Academy, Graph Engineering for Agentic Systems](https://openclaw.academy/blog/graph-engineering-agentic-systems/) | Accessible article, read across two fetch ranges. Practitioner advice, not product documentation or an independently reproduced study. Its referenced small Apollo study was not separately verified. |
| S5 | [Neo4j vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/vector-indexes/) | Accessible official manual; older `semantic-indexes` URL redirected here. Edition/storage distinctions explicitly documented. Current documentation is version-sensitive. |
| S6 | [Neo4j full-text indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/full-text-indexes/) | Accessible official manual; older URL redirected here. Tokenization, string-property indexing, and relevance scores documented. |
| S7 | [Neo4j embedding generation and storage](https://neo4j.com/docs/genai/plugin/current/embeddings/) | Accessible official plugin documentation. Provider API calls and native-vector storage requirements documented; not evidence of an offline model bundled into the database. |
| S8 | [Neo4j embedded Java reference](https://neo4j.com/docs/java-reference/current/java-embedded/) | Accessible official reference with traversal and embedded JVM topics. Not evidence of a native embedded C++ database. |
| S9 | [Neo4j legal terms](https://neo4j.com/legal-terms/) and [Neo4j upstream repository](https://github.com/neo4j/neo4j) | Accessible. Licensing URL redirected to legal terms. Upstream explicitly identifies Community as GPLv3 and Enterprise as containing commercial closed-source components. |
| S10 | [Pinecone Database overview](https://docs.pinecone.io/guides/get-started/overview) | Accessible official documentation. Separates Database, Assistant, and Nexus; documents dense, sparse, full-text, metadata-filtered, and hybrid retrieval. Not proof that every API or account tier exposes every capability. |
| S11 | [Pinecone hybrid search](https://docs.pinecone.io/guides/search/hybrid-search) | Accessible official documentation. Distinguishes Documents API text-match/dense and rank fusion from Vectors API dense/sparse combinations. Recheck API/version availability before choosing. |
| S12 | [Pinecone Nexus overview](https://docs.pinecone.io/guides/nexus/overview) | Accessible official documentation. Describes curated contexts and grounded, cited answers through KnowQL. Explicitly distinguishes Nexus from a vector database and an agent framework. Does not establish this user's access, commercial terms, or general-availability status. |
| S13 | [SQLite FTS5](https://www.sqlite.org/fts5.html) and [SQLite WITH](https://www.sqlite.org/lang_with.html) | Accessible official documentation. Full-text module and recursive graph/tree queries documented. Verify FTS5 support in the actual installed SQLite build. |
| S14 | [pgvector upstream documentation](https://github.com/pgvector/pgvector) | Accessible official project README. Exact/approximate similarity and index tradeoffs documented. No installation performed. |
| S15 | [PostgreSQL recursive queries](https://www.postgresql.org/docs/current/queries-with.html) and [full-text introduction](https://www.postgresql.org/docs/current/textsearch-intro.html) | Accessible official documentation. Relationship traversal via recursive SQL and built-in lexical search documented. |
| S16 | [Anthropic, Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Accessible first-party engineering guidance; research URL redirected here. Recommends simplicity and distinguishes fixed workflows from autonomous agents. Page itself warns that tooling has evolved since the original publication. Advice, not a benchmark for this repository. |

None of the supplied URLs was wholly unreachable in this session. S3 is nevertheless **not fully verified**: a returned summary is not the full Medium article. No pricing, product trial, authentication, library installation, or provisioning was attempted.

## Four different capabilities—not one “graph” feature

| Capability | What it answers | Migration-understanding example | Important limitation |
|---|---|---|---|
| Relation traversal | Which explicitly modeled entities are connected, with what direction and path? | “Which source field, decoding operation, guide section, and test evidence support this migration rule?” | Missing or incorrect edges produce incomplete or incorrect paths. A path is evidence only if its constituent claims are supported. |
| Similarity retrieval | Which passages or entities are close in an embedding space? | Find explanations of byte-order conversion when the question uses different wording. | Semantic proximity is not proof of a call dependency, representation guarantee, or correctness. |
| Lexical retrieval | Which exact identifiers, tokens, phrases, or error strings occur? | Find `memcpy`, `std::endian`, a field identifier, or a compiler diagnostic. | Tokenization may split C++ punctuation and qualified names; preserve a raw exact-match path alongside full-text ranking. |
| Agent orchestration | Who or what performs a step, under which policy, budget, and approval gate? | Extract → validate → retrieve → draft → reviewer approval. | A workflow graph is not the same thing as a stored knowledge graph or an ANN index's internal graph. No database supplies all execution controls by itself. |

Use exact identifiers or lexical search to obtain seeds, optionally semantic retrieval for paraphrases, then bounded traversal for evidence expansion. Fuse ranked results explicitly rather than adding incomparable raw similarity and lexical scores. A deterministic pipeline can implement this without autonomous delegation.

**Article advice:** The returned Medium summary discusses typed handoffs, deterministic policy routing, and separating judgment from computation [S3]; this is the extent of verified access. OpenClaw Academy describes extraction → entity resolution → provenance-aware assembly → grounded query, singleton fallback, schema versioning, and evaluation [S4]. Its own text cautions that graphs are not needed for most simple retrieval tasks and that its referenced small study is illustrative. Neither article establishes an advantage for this two-file demo.

**Verified product features:** Treat the official manuals in the register as the capability basis.

**Repository hypotheses:** Better explanations, safer change-impact analysis, and shared evidence across roles are proposed benefits, not measured outcomes.

## Can Neo4j alone support the proposed MVP?

**Yes, as the sole retrieval database, conditionally.** Store file/symbol/concept/evidence entities and typed relations; use traversal for bounded paths, full-text for guide passages, and optional vector properties/indexes for semantic seeds [S5–S8]. Source citations and extraction metadata would be an application-designed schema. Candidate results still require evidence checking and an answer renderer; an LLM is optional.

Important distinctions:

- **Vector embeddings are not generated just because an index exists.** S5 documents indexing vectors from external proprietary or open-source generators. For a future offline experiment, locally computed embeddings could be written as numeric lists. Model selection, license, download policy, compute, and quality need separate approval and evaluation. No model was downloaded.
- **Neo4j's GenAI plugin is not inherently offline.** The documented embedding function sends requests to the selected provider [S7]. Do not enable it against private source material by default.
- **Edition and version matter.** S5 documents vector indexes in Community and Enterprise. Community can index numeric-list properties; native `VECTOR` storage requires the documented Enterprise/Aura storage format. Pin a compatible version and test the selected representation rather than copying the latest syntax blindly.
- **“Embedded” is ambiguous.** Embedded Neo4j in S8 means a Java application sharing a JVM, not linking a lightweight native C++ library into either executable. Prefer a separate optional local research service if Neo4j earns a trial; do not alter the C++ demo's runtime dependencies.
- **Licensing is not MIT throughout the stack.** The repository README identifies its license as MIT; Neo4j Community is GPLv3, Enterprise includes commercially licensed components, and Desktop/service terms are separate [S9]. Internal use, redistribution, modifications, and embedded packaging need case-specific review; this is not legal advice or a claim that every network client must become GPL. Do not bundle a database into the demo without a licensing decision.
- **Operational costs remain without a subscription:** JVM/process resources, installation, data rebuilds, backups, upgrades, schema migrations, and Cypher expertise. Search quality must be measured locally; vendor speed claims do not settle the decision.

## Fit-for-scale alternatives

“Cost” below identifies cost drivers, not a price quotation or measured total cost.

| Option | Value for a tiny corpus | Missing pieces / costs | Operational complexity and decision condition |
|---|---|---|---|
| **A. No external DB: JSON + exact lookup; optionally SQLite FTS5 and edge tables** | Reviewable facts and provenance; no network service; exact search; SQLite adds full-text and recursive relationship queries [S13]. Plain JSON can support bounded in-memory traversal. | Manual/schema upkeep; extraction still needed; neither JSON nor core SQLite FTS5 is a built-in semantic vector engine. Optional embeddings would be a separate experiment. | **Lowest starting complexity.** Local files, rebuild script, and installed-module verification. Preferred baseline; retaining it is a successful outcome if it answers the workload. |
| **B. Local Neo4j graph + full-text + optional vectors** | One retrieval store with explicit paths and semantic/lexical seeds [S5–S8]. Better fit when recurring relationship queries become central. | Database runtime, learning, licenses/edition review, resource use, and extraction/embedding work. No automatic proof of correctness or orchestration. | **Moderate.** Evaluate only if A has demonstrated relational or maintenance limitations. |
| **C. Local PostgreSQL + pgvector** | Facts, provenance, SQL joins/recursive traversal, full-text, and exact or approximate vector search in one system [S14–S15]. Useful if relational data and team SQL familiarity dominate. | Postgres service and extension lifecycle; graph paths can be less ergonomic than Cypher. ANN recall/filter interactions and index tuning require validation. | **Moderate.** More machinery than this corpus currently needs; credible alternative if a broader relational workload emerges. |
| **D. Neo4j + separate managed Pinecone Database** | Separates graph traversal from managed vector/lexical retrieval; may help with independently scaled retrieval, an existing Pinecone investment, or a measured relevance/operations benefit [S10–S11]. | Additional service boundary, credentials, data transfer approval, metered service/model costs, duplicated IDs/metadata, synchronization, deletion, failure recovery, and observability. No native relationship traversal established by cited Pinecone docs. | **Highest here.** Not justified for the present demo. Future vendor experiment requires explicit permission and a gap B/C cannot reasonably close. |
| **E. JSON/SQLite relationship authority + managed Pinecone retrieval** | Another possible split: retain simple local relations while outsourcing search. Shows that a managed vector DB does not require Neo4j. | Same remote-service approval and index-staleness concerns as D; local traversal and provenance logic remain necessary. | **Higher than A.** Consider only if managed search itself proves valuable, not as a prerequisite for “agents.” |

### Explicit incremental case for Pinecone

Pinecone Database supports dense, sparse, full-text, filtered, and hybrid retrieval, including integrated embedding options [S10–S11]. Those capabilities can provide value, but “hybrid” is not a single interchangeable API: the docs distinguish text filtering plus dense ranking, client-side reciprocal-rank fusion, and Vectors API dense/sparse weighting. Validate the actual account/API combination; do not promise a particular feature tier.

Adding it to Neo4j does **not** add graph traversal to a graph database, and Neo4j already offers vector and full-text indexes. The incremental hypothesis is managed search operations or better measured retrieval under a future workload—not merely “vector support.”

If ever approved, Neo4j or the canonical local manifest should remain the relationship/provenance authority. Pinecone records should carry stable entity/chunk IDs, source revision, embedding version, and ingestion generation. Query-time joins must reject missing/deleted/stale records. Define idempotent upserts, reconciliation, tombstones, and a baseline fallback for remote failure. This consistency work can dominate a tiny corpus's operating effort.

**Nexus is separate.** S2 is an application-reviewed trial entry point, while S12 describes an answer-serving knowledge engine over curated contexts, using Pinecone Database underneath. The documentation explicitly says Nexus is not a vector database and not an agent framework. Its “graph of contexts” is not evidence of a general-purpose property-graph query language or a C++ dependency extractor. Public docs exist, but account access, general-availability designation, contractual limits, and reproducibility of advertised gains were not verified. Do not assert Nexus is unavailable; equally, do not assume immediate access or transfer its marketing gains to Pinecone Database or this repo. No trial is needed for the current plan.

## Transferable graph-engineering patterns for migration knowledge

The useful reinvention is an **auditable migration evidence model**, independent of storage vendor:

1. **Small typed vocabulary.** Candidate entities: `SourceFile`, `Symbol`, `WireField`, `Representation`, `MigrationRule`, `GuideSection`, `Evidence`, and `ValidationRun`. Candidate relations: `DECLARES`, `READS_FIELD`, `USES_REPRESENTATION`, `MITIGATES`, `DOCUMENTED_BY`, `SUPPORTED_BY`, and `SUPERSEDES`. These are proposals; create only predicates supported by inspected source or documentation.
2. **Separate claims from observations.** A guide's recommendation is not an implementation fact; a successful example output is not comprehensive portability proof. Distinguish `documented`, `statically observed`, `runtime observed`, `inferred`, and `reviewed` evidence. Do not infer EBCDIC or packed-decimal support merely because a guide mentions those topics.
3. **Deterministic identity before model judgment.** Use repository-relative path, revision, qualified symbol and signature where available. Preserve source spans separately from identity. Never merge two same-named symbols solely because their embedding or spelling is similar. Keep unresolved entities distinct.
4. **Provenance at creation.** Each extracted claim/edge needs source path or public URL, revision/content hash, line range or section anchor, evidence excerpt/reference, extraction method/version, schema version, run ID, and observed timestamp. Derived paths must return the supporting evidence for every hop.
5. **Bounded queries, not unlimited expansion.** Restrict predicates, depth, result count, and source revision; show missing links and conflicts. Similarity may nominate a seed but cannot create a verified relation. Cite original evidence, not only a generated node summary.
6. **Typed handoffs and deterministic gates.** Extraction returns a schema-validated result; validation rejects malformed or unsupported edges; retrieval returns evidence plus explicit uncertainty; drafting cannot write code or authorize deployment. Human review decides ambiguous merges and migration recommendations. These controls transfer from article advice [S3–S4, S16], without requiring a multi-agent runtime.

### Confidence, staleness, and validation

- **Confidence:** Keep extraction confidence separate from evidence strength and reviewer status. A model's numeric confidence is not a calibrated probability. Begin with auditable categories such as direct/reviewed, inferred/unreviewed, conflicted, and unsupported. An exact code match still does not prove semantic correctness.
- **Staleness:** Bind code claims to a revision/content hash, not a timestamp alone. On a source change, invalidate affected claims, chunks, embeddings, and derived answers; re-extract before presenting them as current. For external docs, record access/version and revalidate before an implementation or purchasing decision. Preserve old facts as historical, not silently current.
- **Extraction checks:** Validate types, required provenance, allowed predicates, endpoint existence, direction, duplicate handling, and source-span support. Schema-valid output can still be false; sample-review every claim for this small initial corpus.
- **Behavior checks:** Compare explanations against inspected code and repeatable executable observations under a recorded compiler/architecture. Do not turn the README's simplified byte-order narrative into a general theorem about every `memcpy`, floating-point representation, padding, or IBM i workload.
- **Adversarial checks:** Include ambiguous symbol names, unsupported questions, contradictory guide/code evidence, renamed files, stale source spans, and removed records. Treat repository text as data, not instructions to tools; use read-only allowlisted retrieval and parameterized queries.
- **Answer checks:** Require supporting citations and valid relation direction for every substantive claim; abstain when evidence is missing. Provenance coverage measures traceability, not truth. Report both.

## Staged experiment and evaluation gates

Everything below is **future work requiring approval**, not work executed by this research.

### Phase 0 — Define the workload before selecting infrastructure

Inspect the two actual examples and guides. Establish a source-revision manifest and hand-reviewed question/evidence set covering:

- exact lookup: where a named operation or migration rule is documented;
- paraphrase: find byte-order explanations without using the guide's wording;
- relationship: follow a field → decoder/representation → guide evidence path, only if supported;
- comparison: distinguish legacy behavior from modern behavior without inventing a call relation;
- negative case: ask about a capability absent from code;
- freshness/conflict: revise or remove evidence and require invalidation or explicit uncertainty.

Separate hand-labeled synthetic ambiguity/freshness fixtures from real repository facts. A tiny corpus cannot establish large-scale capacity or broad migration reliability.

**Gate:** agree on the target user and task, valid gold evidence, acceptable errors, and resource/budget constraints before running retrieval experiments. No vendor decision at this gate.

### Phase 1 — Establish the cheapest reproducible baseline

Evaluate direct source reading/exact lookup and a reviewed JSON evidence manifest; add SQLite only if it clarifies a real need. Use the same corpus snapshot, questions, answer format, and evaluation rubric for all later candidates. Keep setup/rebuild instructions and results separate from the existing C++ demonstration.

**Gate:** if the baseline answers the scoped workload with acceptable evidence quality and upkeep, stop. More infrastructure is not a success criterion.

### Phase 2 — Test one justified local improvement

If relationship retrieval is a measured weakness, compare baseline traversal with local Neo4j. If paraphrase retrieval is a measured weakness, compare lexical retrieval against an approved local embedding experiment. Do not change extraction quality, model, chunking, and storage vendor simultaneously; otherwise improvements cannot be attributed. PostgreSQL + pgvector is a credible comparator if SQL/relational requirements emerge, not another mandatory service.

**Gate:** retain a more complex option only when repeatable task gains or maintainability benefits outweigh recorded setup, compute, licensing, and lifecycle work. Pin versions and verify edition-specific features.

### Phase 3 — Optional managed-search or Nexus inquiry

Only after a local gap and explicit user authorization: investigate actual access, applicable contracts, data handling, deletion/export, current costs, and feature availability. Any later remote evaluation must use approved data and a stated spending ceiling. Compare Neo4j-only against Neo4j + Pinecone with identical corpus and embedding settings where comparable; evaluate Nexus as a separate answer-serving system, not an interchangeable index.

**Gate:** no source upload, trial signup, paid service, or deployment without separate approval. If managed search does not show incremental value, retain the simpler local option.

### Measurements to record

| Dimension | Evidence to collect |
|---|---|
| Retrieval | Recall/precision at a fixed result budget, ranking usefulness, exact-identifier success, and performance by question class; do not hide failed multi-hop/negative cases in one average. |
| Extraction/resolution | Hand-reviewed relation precision/recall, wrong merges, missed aliases, orphan endpoints, and coverage of required facts. |
| Grounding | Correct answers, citation support, unsupported-claim rate, path validity, provenance completeness, and appropriate abstention. |
| Freshness | Detection of changed/deleted evidence, propagation to indexes, stale-answer rejection, rebuild/reconciliation success. |
| Efficiency | Measured query and end-to-end latency, model calls/tokens if any, local resource consumption, setup/rebuild/review effort. Distinguish cold and warm runs. |
| Operations/cost | Number of services and failure modes, version/license obligations, recoverability/export, actual resource or service charges only if later authorized. |

Set acceptance thresholds **before** comparisons; no unsupported target percentage, promised speedup, vendor pricing, or scale claim is asserted here. For a tiny corpus, report per-question results and repeatability rather than statistically sweeping conclusions.

## Limitations and open decisions

This is documentation research, not a code audit, installed-product test, license opinion, pricing quote, or reproduction of vendor/article claims. Medium's full article could not be verified. Nexus access/GA status and commercial conditions remain unresolved. Current documentation can change; pin releases before implementation. Whether a migration companion is the desired product, whether the corpus will grow, and whether semantic retrieval is necessary are still product decisions. Nothing here justifies converting two C++ examples into a graph platform by default.

## Concrete next actions and phase-relative owners

| Owner | Next action | Gate / sequencing |
|---|---|---|
| **Neo** | Define the companion's target questions and non-goals; approve a minimal evidence schema and decide whether any application beyond the existing demo is wanted. | Phase 0, before an implementation request or database choice. Obtain explicit user approval to proceed beyond planning. |
| **Tank** | Prepare the hand-reviewed question/evidence rubric and negative, ambiguity, and freshness cases; define acceptance thresholds and verify the existing executable behavior when an experiment is authorized. | Phase 0 gold-set review precedes Phase 1; evaluation results must pass before any Phase 2 promotion. |
| **Morpheus** | Own the architecture decision record and complexity budget; review Neo4j packaging/license implications and compare baseline, Neo4j-only, and SQL alternatives against Tank's evidence. | After Phase 1 results; authorize a local Phase 2 spike only for a documented gap. Escalate any managed service, source transfer, trial, or spend as a separate Phase 3 approval—not a default commitment. |
