# Reinvention plan — evidence-backed modernization knowledge workbench

**Author:** Morpheus, Architecture Lead. **Planning date:** 2026-10-19. **Requested by:** odaibert.

> **Historical proposal:** the later local workbench is documented in the
> [current implementation summary](README.md#current-implementation-versus-proposal).
> Its existence does not complete this plan's evaluation gates, establish the
> proposed retrieval/agent platform or replace independent specialist reviews.
> The "exists now" inventory below refers to the original inspected revision.

**Status: optional proposal, not an approved product scope or implementation.** Fact Checker's [bounded independent review](review.md) approves the proposal only; remaining specialist reviews are pending. No database, embedding model, extraction service, retrieval API, agent runtime or cloud workload is claimed implemented by this plan. Approval of the persistent team is not approval of these components.

## 1. Executive proposal and evidence boundary

Keep the educational before/after endian demonstration intact. Optionally add a small, local, read-only **modernization knowledge workbench** that can answer “what does this code actually do, what supports that explanation, and what would become stale if it changed?” Its value would be traceable understanding, not automatic modernization or a graph-shaped visualization.

The seed is two independent executables and four guides, not a payment platform or real IBM i integration. A direct-source lookup plus a reviewed JSON manifest is the default experiment. SQLite is a conditional local convenience. A graph database must earn its complexity through measured questions; “graph engineering” first means typed evidence, reliable identity and bounded reasoning, not buying a graph service.

**Primary inputs:** [repository assessment](repository-assessment.md), especially §§3–7, and [technology research](technology-research.md), including its source register S1–S16. Original application reference revision: `d3d183bca292e365cf0eb8a78ebef7ba5ddea3a2`. Relative source links below describe that inspected content; a future citation resolver must also verify hashes, not assume a moving branch preserves line numbers.

Evidence precedence is scoped, not absolute: bytes/AST establish what is present; a recorded run establishes behavior only for its environment; guides establish what was written or recommended. An AST cannot prove all runtime behavior, and one run cannot certify portability. Conflicting claims remain separately visible. Neither embedding similarity nor a review turns a hypothesis into a measured result.

### Existing versus proposed

| Boundary | Exists now | Proposed only |
|---|---|---|
| Application | [CMake targets](../../CMakeLists.txt#L4-L12): C++17 `pos_legacy`, C++20 `pos_modern`, each with its own `main` | No new dependencies or knowledge calls inside either executable |
| Data flow | Local literal buffer → `memcpy` → native fields; modern adds four conversions → stdout ([legacy](../../src/pos_transaction.cpp#L42-L79), [modern](../../src/pos_transaction_x86.cpp#L92-L130)) | Offline source/document ingestion, not a real file/queue integration |
| Knowledge | Human-written guides, assessment and research | Versioned evidence manifest; optional relational/graph indexes; cited answers |
| Team/process | Local Squad files, approved named roles | Explicitly assigned bounded work, not a running multi-agent application |
| Deployment | Narrative cloud options and Pages metadata | No deployment in this scope |

```text
Existing, unchanged:
  fixture → pos_legacy → intentionally wrong little-endian numeric output
  fixture → pos_modern → endian conversion → corrected tested-host output

Optional workbench, outside the C++ runtime:
  allowlisted source bytes + docs
    → snapshot → AST/text extraction → validated/reviewed claim manifest
    → JSON/direct search [optional SQLite projection]
    → bounded query + evidence verification → cited answer OR abstention
    → optional draft patch artifact → human decision (never auto-apply)
```

This extraction/control-flow diagram is **not** the domain knowledge graph. Domain edges describe `Field → Transformation → Issue → Evidence`, for example. An agent workflow describes who may execute steps; an ANN index may use an internal graph for search. None substitutes for the others.

## 2. Minimal typed ontology and worked evidence

All types and predicates below are **proposed interfaces**, not installed schemas. Start with only concepts needed by the evaluation set. Do not import an enterprise payments ontology.

| Type | Identity/scope and intended meaning |
|---|---|
| `SourceRevision`, `File` | Logical repository ID chosen locally; revision or worktree snapshot digest; normalized repository-relative path and exact content hash |
| `BuildTarget`, `Symbol` | Target and translation-unit-qualified declaration/signature; separate `TxnRecord`, `processTxn`, `main` per target |
| `Transaction`, `Field`, `Fixture` | `Transaction` describes the demonstrated record concept, not a live business entity; each `TxnRecord` implementation remains distinct. Fields belong to a declaration; fixtures represent literal bytes with target/environment qualifications |
| `Encoding`, `Platform` | Separate byte order from character encoding; platform includes architecture, compiler/version, standard library, ABI and observed native order where known |
| `Issue`, `Transformation` | A bounded risk/contradiction or conversion rule; implemented operation versus suggested remediation explicitly distinguished |
| `TestCase`, `ValidationRun` | Planned case versus executed observation, command, inputs, environment, output and exit status; never equate them |
| `GuideSection`, `Claim`, `Evidence` | Document passages, reified assertions and exact support; every traversable domain edge has a claim/evidence record |

Allowed directed predicates initially include `File DECLARES Symbol`, `BuildTarget COMPILES File`, `Symbol HAS_FIELD Field`, `Symbol CALLS Symbol`, `Symbol READS_FIELD Field`, `Transformation APPLIES_TO Field`, `Fixture INSTANTIATES Transaction`, `Field USES_ENCODING Encoding`, `Issue QUALIFIES Claim`, `GuideSection DISCUSSES Issue`, `TestCase CHECKS Claim`, `ValidationRun EXECUTES TestCase`, and `Claim SUPPORTED_BY Evidence`. `CORRESPONDS_TO` connects the two record implementations only after review; identical names are not identity. A claim about encoding must say whether it concerns numeric byte order or character bytes.

Relationship validation specifies endpoint types and direction, required provenance and allowed scope. For example, `CALLS` needs a resolved call site, not a nearby guide mention; `DISCUSSES` cannot imply `IMPLEMENTS`. Multi-hop answers must return support for each edge, not just the endpoints. Absent edges mean unknown, not automatically false.

### Worked candidates anchored in actual source

These are manually worked **schema examples**, not extracted database records:

| Candidate fact | Source and evidence class | Qualification |
|---|---|---|
| `pos_modern COMPILES src/pos_transaction_x86.cpp`; standard C++20 | [CMake 4–5, 11–12](../../CMakeLists.txt#L4-L12), static observation | Does not prove every compiler builds it |
| Modern `TxnRecord HAS_FIELD amountCents:uint32_t` | [modern 72–78](../../src/pos_transaction_x86.cpp#L72-L78), static observation | Legacy declaration is a different entity ([24–30](../../src/pos_transaction.cpp#L24-L30)) |
| Modern `processTxn CALLS fromBigEndian32` for `amountCents` | [modern 99–102](../../src/pos_transaction_x86.cpp#L99-L102), static observation | Calls do not occur in legacy `processTxn` |
| Fixture amount bytes are `00 00 13 88`; intended wire offset 4–7, value 5000 | [modern 118–124](../../src/pos_transaction_x86.cpp#L118-L124), literal observation plus derived intended layout | Not an independently supplied IBM record specification; ABI offsets require separate evidence |
| Endian transformation leaves four card bytes unswapped | [modern 99–111](../../src/pos_transaction_x86.cpp#L99-L111), static observation | No evidence of EBCDIC conversion; ASCII bytes `56 49 53 41` concern the tested host |
| Native run printed `1 / 50 / 100 / 7 / VISA` | [assessment §4](repository-assessment.md#4-actual-baseline--executed-not-inferred), recorded runtime observation | Apple Clang 21/ARM64 little-endian only; no raw run log is newly produced here |
| Guide mentions an EBCDIC conversion prompt | [prompts 69–80](../copilot-prompts.md#L69-L80), documented claim | Not an implementation edge |
| Broad portability claim needs qualification | [README wording](../../README.md#L64-L76), [helpers](../../src/pos_transaction_x86.cpp#L31-L63), [assessment §5](repository-assessment.md#5-correctness-portability-and-documentation-qualifications) | Claim and its limits coexist; original teaching text is preserved |

Example path: exact lookup `amountCents` → choose modern target → `Field` ← `APPLIES_TO` endian transformation → supporting call at line 100 → helper body at lines 31–47 → numeric-order explanation in a guide. Another path is field → affected claim → test case → validation run/platform. A missing test case/run is reported as a gap, not synthesized from comments.

### Claim and citation contract

Proposed pseudocode only:

```text
SourceRef = {repo_id, snapshot_id, revision?, path, sha256,
             byte_start, byte_end_exclusive, line_start, line_end}
Claim = {id, subject, predicate, object, schema_version,
         evidence_refs[], extractor_version, extraction_run,
         basis: static_observation | runtime_observation | documented | inference | proposal,
         confidence: direct | derived | ambiguous | conflicted | unsupported,
         review: pending | accepted | rejected, reviewer?, rationale?,
         scope, status: current | invalidated | deleted | historical}
Answer = {snapshot_id, claims[], citations[], evidence_paths[],
          conflicts[], unknowns[], abstention_reason?}
```

`direct` describes extraction fidelity, not calibrated truth probability. Review is orthogonal to basis/confidence and must name an actual reviewer. IDs use canonical serialized components, never string concatenation without escaping: source identity `(repo_id,path)`; source version `(source_identity,sha256)`; symbol `(target,TU,qualified_name,signature,local_disambiguator)`; field `(symbol_id,field_name)`. Use a declaration span discriminator where names/signatures still collide; ambiguous resolution stays unresolved. Revisioned claim IDs include source versions, predicate, endpoints and extractor/schema version; line numbers are locator metadata, not permanent identity.

Every substantive answer clause must cite original source evidence with revision/hash and meaningful span; runtime claims also cite command/environment/run provenance. Display convenient relative links, but resolve against the pinned snapshot. Public-document citations need URL, access date, product/document version where known and section/excerpt hash. Derived answers show the inference and its input citations. A generated summary cannot be the sole source for a code fact. If only the assessment supplies historical execution evidence, label it as a reported run rather than pretending to possess an independent raw trace.

## 3. Deterministic ingestion and lifecycle

No ingestion is executed by this plan. Future implementation should follow this order:

1. **Approve and freeze the corpus.** Initially allowlist `src/*.cpp`, `CMakeLists.txt`, root README and the four original guides; keep planning reports in a separate evidence class so proposals cannot be reimported as shipped features. Exclude `.env`, credentials, private records, `.git`, tool state and other agent histories. Refuse symlink/path escapes, oversized inputs and unapproved binary types. No external upload, embedding API or telemetry containing source without opt-in.
2. **Snapshot exact bytes first.** Record manifest path, length, SHA-256, revision and worktree status. A dirty/untracked source uses content-addressed snapshot identity, never falsely the clean HEAD revision. Retain immutable local source bytes according to approved retention, and separately derive display text; do not normalize line endings or Unicode before hashing. Detect invalid text encoding explicitly and retain byte offsets. Source buffers are truth, not an LLM reconstruction.
3. **Extract code AST-first.** Use an approved installed compiler frontend and the target's C++17/C++20 settings; capture compiler version, include/define settings, diagnostics and active preprocessor branch. Distinguish lexical literals/comments from resolved declarations/calls. Inactive MSVC/manual-fallback text is not a tested call path. Missing parser/tool, unresolved include/type or unsupported construct yields an error/quarantined partial result; never silently promote regex extraction to AST facts. An exact-text/manual baseline can proceed with that limitation visible.
4. **Extract documentation deterministically.** Parse Markdown headings, paragraph/list/table/code spans and links while retaining exact byte/line maps. Parse the small CMake target declarations through a bounded recognizer or reviewed manifest; reject unsupported constructs rather than claiming arbitrary CMake evaluation. Code fences are examples, not compiled code. External URLs are references, not instructions to fetch/execute. A guide's Azure/Data Queue scenario remains documented narrative.
5. **Preserve fixture truth.** The existing simulated buffer is in source, not a checked-in binary fixture file. Future derived fixture artifact must preserve all 16 octets: `00 00 00 01 00 00 13 88 00 64 00 07 56 49 53 41` on the tested ASCII host. Store its own hash and derivation/source/environment; distinguish this from the source-file hash. Validate both literal arrays independently and never rewrite them from a natural-language summary. Host character literals do not establish universal encoding.
6. **Resolve and validate.** Validate schema, endpoint types/directions, required spans/hashes, provenance, duplicate handling and target-qualified symbols. Reject dangling edges and impossible ranges. Review every seed claim manually; quarantine ambiguous aliases, contradictory claims and parse errors. Inferences retain rules/input IDs; no model may invent a relationship to fill an empty path.
7. **Publish atomically.** Produce a validated generation of the canonical manifest, then rebuild optional projections. Deterministic reingestion of identical bytes/settings/schema should yield identical normalized facts (timestamps/run IDs kept separately). Publish a generation pointer only after validation; interrupted ingestion leaves the previous generation available but must mark it stale if source has changed.
8. **Invalidate before reuse.** At query time verify generation/source hashes. Any change invalidates affected claims, chunks, embeddings, cached paths/answers and transitive derivations before serving as current. Rename detection requires explicit content/identity evidence; do not merge by basename. Re-extract changed sources, resolve dependencies, then atomically promote a new generation. Tool/schema/model version changes also trigger the applicable rebuild.
9. **Delete and reconcile.** Removed source gets a tombstone in the next manifest; exclude all dependent evidence from current answers and delete associated search/vector entries. Historical retention is explicit and access-controlled, not a way to evade requested deletion. For sensitive deletion purge retained bytes/caches/exports according to policy; keep only permitted non-sensitive audit metadata. Reconcile IDs, counts and generations across stores before promotion; orphan/stale hits fail closed. Rebuild every projection from canonical evidence to test recoverability.

Errors are first-class: `source_changed`, `parse_failed`, `ambiguous_symbol`, `unsupported_encoding`, `missing_evidence`, `stale_projection`, `out_of_scope`, `forbidden_path`. Return them with bounded partial evidence where safe; do not silently answer using another revision. Extraction confidence and review metadata must survive exports and storage changes.

## 4. Questions, retrieval strategy and safety

| Representative question | Cheapest retrieval/path and expected behavior |
|---|---|
| Why does legacy ID 1 print 16,777,216? | Exact fixture/process lookup plus explicit big/little decoding; cite legacy 38–47 and fixture. Distinguish derived arithmetic from recorded run. |
| Which fields are converted and why not `cardType`? | Lexical `fromBigEndian` seed; bounded call/field edges to both helpers and output. State byte-order conversion is not character transcoding. |
| Where is a transaction's cents value decoded and printed as dollars? | Target-qualified field → transformation/call evidence → presentation line 107. Do not merge the two `processTxn` symbols. |
| What establishes the 16-byte layout? | Exact static assertion plus assessment's scoped native offset probe. Report ABI assumptions; do not infer all offsets from total size alone. |
| Is EBCDIC, COMP-3 or a Data Queue adapter implemented? | Inventory-bounded negative at the inspected snapshot; cite guide mentions separately from the complete two-source inspection. Graph-edge absence alone is insufficient. |
| Explain “network-order money fields” without exact identifiers | Try lexical synonyms/direct reading first; semantic passage seeds only in a separately approved experiment, followed by original evidence validation. |
| Is this certified on Linux x86 or IBM i? | Answer “not verified by available evidence”; ARM64 result is not x86 execution. No certification from filenames/comments. |
| Why do walkthrough output and actual output differ? | Compare [walkthrough 157–164](../copilot-modernization-guide.md#L157-L164) with fixture and assessment run; expose `2.28395e+07` versus `2.28295e+07`, do not rewrite sources. |
| If `amountCents` changes, what needs review? | Reverse-dependency traversal over supported claims/tests/guide references. Identify missing edges and proposed tests; never promise complete whole-program impact analysis. |
| Which Azure deployment is live? | Abstain from deployment claims; narrative architecture is not live-resource evidence. |

**Lexical** retrieval preserves exact raw identifiers/punctuation alongside optional FTS tokenization. **Graph traversal** follows typed known relations, initially at most three hops and 20 evidence records, restricted by snapshot/predicate/target; report truncation, not an apparently complete answer. **Semantic** retrieval proposes related passages, not verified edges or equivalence. If used, fuse ranks explicitly (for example reciprocal-rank fusion); do not add incomparable raw lexical/vector scores. Start with five retrieved seeds and let Tank predeclare any changed budget.

Proposed interfaces, not implemented APIs:

```text
snapshot(allowlist) -> Manifest | Errors
extract(manifest, parser_settings) -> CandidateClaims + Diagnostics
validate_and_review(candidates) -> ReviewedGeneration
search(query, snapshot, target?, mode=exact) -> EvidenceHits
traverse(seed_ids, predicates, depth<=3, max_evidence<=20) -> SupportedPaths
answer(question, generation) -> Answer | Abstention
draft_patch(answer, explicit_scope) -> ReviewArtifact   # no application write
```

Ambiguous `processTxn` queries return both targets or request target selection; unsupported questions return unknowns instead of plausible completion. Missing necessary evidence, conflicting unresolved inputs, failed hashes, or a relation outside the budget cause scoped abstention. Known conflicts may be answered as conflicts with both citations. Only source-current supported claims can be asserted as current.

**Read/write boundaries:** the retrieval worker can read only approved immutable snapshots and its indexes. It has no shell, network, credential access, source-write permission or authority to approve changes. Use parameterized SQL/Cypher and fixed query templates; retrieved prose cannot change tool permissions, invoke guide commands, add paths or authorize purchases. A separate explicitly invoked patch-drafting step may write an isolated review artifact only. Human approval of the exact diff, affected-source hashes, tests and rollback is required before any later apply step; a newer source revision cancels that approval. No generated patch is applied in this mission.

## 5. Storage/provider decision ladder

See research's [fit-for-scale comparison](technology-research.md#fit-for-scale-alternatives) and source register for underlying public references. This is a proposed decision ladder, **not an accepted vendor selection**.

| Option | Role and entry condition | Trade-offs / exit condition |
|---|---|---|
| Direct source + versioned JSON | Default canonical evidence and exact search; bounded in-memory traversal is sufficient to try domain relationships | Lowest service count; manual review/rebuild still costs effort. Stop here if scoped questions pass. A database is not a success criterion. |
| Local SQLite projection | Add only for demonstrated querying/update ergonomics; fact/edge/source tables and optional FTS5 | Recursive SQL can traverse relations; FTS5 availability must be checked in installed build [S13]. No server, no built-in embedding engine assumed. Keep JSON/export rebuildability. |
| Conditional local Neo4j **alone** | Trial only after a recorded relational/maintenance gap; graph + full-text + optional vectors in one store [S5–S8] | Installation/JVM, schema migration, backups, skills and resources; not embedded native C++. Pin release/edition. Numeric-list vector indexing differs from Enterprise/Aura native `VECTOR` storage. Embeddings still need a separately approved generator. |
| PostgreSQL + pgvector alternative | Revisit only if a broader relational workload/SQL ownership emerges [S14–S15] | Service/extension lifecycle and ANN tuning; credible alternative, not another mandatory stack layer. |
| Neo4j + separate Pinecone Database | Only after Neo4j-only measurements show incremental managed-search value and user authorizes data transfer/spend [S10–S11] | Duplicated IDs, generations, metadata and deletions, credentials, network failures, export and metering. Keep canonical relationship authority local or in Neo4j. Reject stale/missing join records; fall back to verified local retrieval. |

Neo4j already supports vector/full-text search: separate Pinecone is not required for “hybrid” retrieval. Pinecone dense/sparse/full-text/filter APIs and feature availability must be checked against the selected API/account; managed operations or better measured answers are hypotheses, not established benefits here. If ever used, idempotent upserts, tombstones, reconciliation and remote-failure tests are mandatory.

Provider/cost/license review precedes any trial. Neo4j Community GPLv3 and Enterprise commercial components require packaging/use-specific review [S9]; do not assume this MIT repository makes dependencies MIT or that all network clients become GPL. SQLite packaging and any local embedding model have their own distribution/version/license checks. Neo4j's GenAI plugin may call external providers [S7]; a local database is not a guarantee of local-only processing. Local embeddings require approval of model download, license, compute and retention. Hosted Pinecone adds service/model charges, egress/data handling and account obligations; no price quotation, free-tier promise or trial signup is authorized. Record actual setup/rebuild/review effort and resource use as well as any later authorized charges.

Nexus is **separate** from Pinecone Database and an agent framework. Its curated-context/KnowQL documentation exists [S12]; the trial landing page is application-reviewed [S2]. Account access, GA designation, commercial conditions and advertised speed/token/task gains were not verified. Public marketing is neither proof of immediate access nor proof of unavailability. Its “graph of contexts” does not establish a property-graph engine or C++ extractor.

## 6. Phase-owned execution backlog and gates

These are **future assignments to propose**, not dispatched work or accepted specialist outputs. Planning phases P0–P3 align with the [mission](../../.squad/mission.md#phase-relative-gates-no-invented-deadlines). Implementation experiments E1–E3 are separately gated after planning. No dates or automatic schedules are assigned.

| ID / stage | Accountable owner; scoped collaborators | Depends on | Deliverable and objective exit gate |
|---|---|---|---|
| P0 — Ground-truth review | Morpheus; Trinity, Tank | Existing assessment | Trinity verifies fixture/layout/encoding qualifications; Tank checks reproducibility matrix. Resolve source conflicts and distinguish passed/unavailable checks. Reports exist; independent review remains pending. |
| P1 — Knowledge contract | Neo; Trinity, Morpheus, Rai | P0 review accepted | Versioned minimal schema, ID rules, at least 20 hand-worked claims across both targets/docs, two duplicate-symbol cases, one conflict, one bounded negative, invalidation/deletion examples. Every claim traceable; Rai reviews path/privacy boundaries. |
| P2a — Evaluation contract | Tank; Trinity, Fact Checker | P0 review accepted | Gold questions, exact evidence/expected answers, ambiguity/staleness scenarios and metrics below; Fact Checker challenges negative claims and gold validity. Freeze before implementations. |
| P2b — Retrieval design | Switch; Neo, Tank | P1 and P2a | Read-only query/answer contract, direct/lexical and relation traversal comparison design, citation/abstention rules, error/attack cases. Same snapshot/budgets/rubric for alternatives; no framework requirement. |
| P3 — Reinvention decision | Morpheus; Rai, Fact Checker, specialists | P1, P2a, P2b | Architecture/complexity ADR, preservation/rollback, unresolved scope and reviews. This synthesis is a draft input, not evidence those dependencies passed. User chooses stop/go and scope. |
| E0 — Explicit implementation authorization | Morpheus prepares; user decides | P3 reviews and open decisions resolved | Written allowlist of scope/tooling/dependencies/data policy/resource budget/thresholds; no implementation before this gate. |
| E1a — Preservation harness | Trinity; Tank | E0 | Additive fixture/output checks without editing either example; approved platform matrix and documented skips. Both original outputs/bytes preserved on supported tested hosts; CMake tested only when available/approved. |
| E1b — Local evidence baseline | Neo; Trinity, Rai | E0, P1 | Deterministic reviewed JSON extractor/manifest and rebuild/export/delete instructions; optional SQLite only with documented need. All seed claims manually verified; change/delete recovery checks pass. |
| E1c — Baseline retrieval/evaluation | Switch; Tank, Fact Checker | E1a, E1b, P2b | Exact/lexical plus bounded local edge traversal, cited answers and per-case evaluation report; zero uncontrolled writes/network. If quality meets need, keep baseline and stop escalation. |
| E2 — One local improvement | Neo for graph; Switch for retrieval; Tank measures; Morpheus owns decision | E1c failing class documented; new user approval of tools/resources | Compare Neo4j-only or a separately approved local semantic experiment, not both changes at once. Same extraction/queries; predeclared promotion thresholds and operational recovery tests. Reject if gains do not justify costs. |
| E3 — Optional managed-search inquiry/trial | Switch; Morpheus, Rai, Tank, Fact Checker | Local gap persists after E2; separate user access/data/spend approval | Validate contracts/features/deletion/export before trial; compare Neo4j-only with added Pinecone under matched settings. Nexus would need its own evaluation, not index substitution. No approval means no signup/upload. |
| H — Decision/history handoff | Scribe, on explicit assignment | Actual phase evidence | Append actual decisions, links, review outcomes and unresolved work; no auto-commit or invented participation. |
| R — Work visibility | Ralph | Explicit future manual request only | Remain configured/dormant. A manual status snapshot may summarize accepted backlog; no heartbeat, issue polling, background process or unattended agents. |

Roles do not confer user approval authority: Neo owns graph contracts, Switch retrieval, Trinity C++ semantics, Tank evaluation, Morpheus architecture trade-offs. Research's suggested Neo “approve” task is interpreted as preparing/recommending scope/schema; the user alone authorizes implementation or spending. Rai and Fact Checker are independent review gates, not rubber stamps. If their rejection protocol applies, a different author revises the rejected artifact.

### Proposed evaluation policy, not measured results

Before E1, Tank should label **24 question/scenario cases**: four exact-identifier/build cases; four paraphrase cases; four supported relationship/comparison cases; four absent/unsupported-capability cases; four ambiguity/contradiction cases; four freshness/deletion cases. Add at least six ingestion/safety checks (path escape, invalid text, unresolved parse, same-name symbol collision, instruction-bearing document, partial index publish). Keep synthetic mutations in an isolated approved test corpus, never the original examples; label all synthetic facts separately. Include renamed files, one changed field type/offset, deleted guide/supporting evidence and mixed-generation vector hits.

The seed corpus is the two source files, CMake and existing guides/README. Gold evidence comes from original sources plus explicitly scoped reported execution; planned or synthetic tests are never represented as original test infrastructure. Two files are too small for performance generalization, statistical superiority or broad migration reliability. Expand only with user-approved, non-sensitive, legally usable samples and independent record specifications if real IBM integration becomes a goal. Keep development and held-out paraphrases distinct; retain failures rather than tuning them out.

**Default acceptance thresholds below are proposed policy for approval, not benchmarks achieved here:**

| Dimension | Proposed seed acceptance gate |
|---|---|
| Provenance/typing | 100% of current accepted claims/edges have valid required provenance, types and source hashes; zero wrong symbol merges or dangling endpoints. Hand-review every seed claim; rejected candidates may remain quarantined. |
| Extraction | 100% precision and coverage on the agreed small hand-labeled seed facts; report unresolved/unsupported constructs explicitly rather than omitting them from denominators. No claim of universal parser correctness. |
| Retrieval | Required gold evidence appears in top five seeds for at least 90% of answerable cases; report exact counts and each question class. For multi-hop cases, also require all necessary supported edges within the declared traversal budget. |
| Answer grounding | Zero unsupported asserted clauses; every asserted clause cited; at least 90% fully correct answerable cases. Unsupported certainty fails even if aggregate accuracy passes. Abstaining on answerable cases counts as a miss. |
| Negatives/ambiguity | 100% of designated unsupported/ambiguous cases return bounded negatives, conflicts, target disambiguation or appropriate abstention; zero invented integrations/platform certifications. |
| Freshness/deletion | 100% of changed/deleted/stale-generation scenarios suppress affected current answers; zero tombstoned/orphan evidence served. Rebuild and interrupted-publish recovery pass every designed case. |
| Safety/preservation | All six safety checks pass, zero unapproved network/source writes, and unchanged original source/build/guide hashes (except the authorized root index link). Regression fixture/output checks pass in their stated environment. |
| Improvement promotion | Predeclare comparison before E2/E3: default require at least two previously failed answerable cases newly pass, no previously passing case regresses, all hard gates remain satisfied, and user accepts recorded incremental setup/maintenance/resources. For an operations-only benefit, require a separately approved effort/recovery criterion before the experiment instead. |

Record per-case correctness, evidence/path precision, retrieval recall, abstention and stale-answer rejection; distinguish extraction misses from retrieval misses. Measure cold/warm query and rebuild times, resource use, model calls/tokens if any and human review effort with fixed hardware/settings. No latency SLA or vendor speedup is assumed: E0 must approve a resource/time ceiling appropriate to intended use, or defer performance-based promotion. Repeated identical runs test reproducibility, not sample diversity. Larger-corpus confidence requires new evidence, not extrapolation from 24 seed scenarios.

## 7. Preservation, rollback and failure policy

- Preserve both original programs, their separate build targets, literal fixture bytes, intentionally wrong legacy little-endian output, corrected modern tested-host output, four-byte non-NUL card output and four original guides. Never “fix” the legacy teaching artifact as a knowledge-workbench side effect.
- Place any future tooling/tests/indexes outside the example runtime and behind explicit commands. Original C++ builds must not require a database, model, network, provider key or agent tool.
- Before any later implementation, capture a path/hash manifest and baseline commands/results. Work in additive, reviewable increments. Root README linking is the only original documentation edit authorized by this synthesis.
- Canonical snapshots/JSON are the export/rebuild contract. SQLite/Neo4j/vector projections and answer caches are disposable; restore a validated generation or rebuild from approved sources. A previous generation cannot be presented as current after its source changed; use historical mode or fail closed until reingestion.
- On preservation mismatch, privacy violation, unsupported claim, unresolved serious reviewer objection or loss of provenance, stop promotion and disable workbench querying. Remove additive integration hooks/indexes using the recorded change manifest, not destructive repository resets; do not touch unrelated user changes. Separately revoke later-approved remote access/purge remote copies if applicable.
- Local `.squad/config.json` now retains version 1 and explicit local backend but omits `teamRoot`, allowing the default repository-local root in another checkout. This is a portability correction to assessment §10's historical absolute-root state, not a change to application behavior. No bridge process or moved-checkout runtime test is claimed.

## 8. Risks, unresolved decisions and stop/go

| Risk / open decision | Required resolution before affected work |
|---|---|
| Scope inflation from educational demo to modernization platform | User chooses teaching-only documentation, local workbench experiment, or a later broader corpus. Stopping at improved documentation/direct search is valid. |
| Unclear compatibility/record authority | User identifies actual target compilers/OS/ABIs and authoritative wire/CCSID specs. Do not infer IBM production requirements, compliance or payment SLAs from scenario prose. |
| Extraction looks precise but is wrong/incomplete | Neo/Trinity review source-supported claims; Tank reports parser coverage and branch limits. Unknown constructs remain explicit. |
| Stale or conflicting prose dominates answers | Scope claims by basis/revision; show conflicts and enforce invalidation before current answers. |
| Prompt injection or private-data retention | Rai reviews allowlists, tool isolation, opt-in transfers and deletion/retention before E1/E3. No source-directed commands. |
| Vendor/license/provider lock-in | Morpheus documents alternatives, version/license review, export/rebuild and cost/resource ceilings; user approves any installation/provider. |
| Gold set overfits tiny demo | Tank reports case-level results; no performance/general migration claim without approved expanded corpus. |
| Independent reviews incomplete | Fact Checker [approved the proposal after a bounded factual/design-contract review](review.md); Trinity/Neo/Switch/Tank/Rai reviews remain pending through explicit authorized coordination. Do not claim consensus or completed phase gates. |

**Go/no-go questions for the user:** Is the optional workbench wanted at all? Which questions/corpus are in scope? Are deterministic tools sufficient, or is a local model experiment desired? What retention/deletion and resource limits apply? Are the proposed acceptance thresholds acceptable? Which platforms need real validation? Who will perform independent reviews? Any external provider consideration needs a later separate decision on exact data, access, license, budget and export/deletion terms.

**Default stop:** planning artifacts only. No implementation until P3 review/E0 approval; no graph service unless the local baseline has a recorded gap; no separate Pinecone unless incremental value can be measured and explicit remote-service approval exists. Fundamental unresolved decisions are approval gates, not implied commitments.

## 9. Verification limitations and current review status

The assessment reports successful direct C++17/C++20 Apple Clang 21 builds and native little-endian ARM64 outputs, including layout probe. CMake was unavailable; x86 Linux, IBM i/big-endian, MSVC/fallback branches, mixed-endian behavior and performance were not validated. “x86” in filenames and broad README claims are not execution evidence. This synthesis does not rerun those builds because sources/build behavior are unchanged; preservation checks establish unchanged inputs, not new platform coverage.

Technology claims are documentation research, not installed-product tests, pricing/legal advice or reproduced benchmarks. Research S3 provided only a Medium summary; full text and detailed examples/quantitative claims remain unverified. S4 practitioner advice and S1/S2 marketing do not prove advantage here. Nexus docs/trial marketing establish neither user access nor verified gains. Current vendor documentation is version-sensitive and must be rechecked before implementation. No sources beyond the two inputs and local evidence were independently web-verified by this synthesis.

No new factual error requiring an assessment edit was found in synthesis. The absolute-root configuration described there is explicitly superseded above; neither input report is edited. The original guides' known qualifications remain visible rather than silently corrected.

**Independent reviewer status: limited proposal approval.** Fact Checker completed a [bounded factual/design-contract review](review.md) on 2026-10-19, including native ARM64 reproduction and public-source checks; this is not implementation approval or completion of P0–P3/E0. Trinity, Neo, Switch, Tank and Rai have not reviewed this integrated plan. Morpheus's author consistency checks are not independent approval. Scribe has not been assigned a handoff and Ralph is dormant. All future owner assignments, API sketches, thresholds and storage choices above remain proposals.

**Author checks performed for this synthesis:** nine SHA-256 comparisons preserved both C++ files, CMake, four original guides and both input reports; the root README matched HEAD after removing only the authorized proposal-link insertion. Parsed config matched exactly `{"version":1,"stateBackend":"local"}`. Checked all 32 relative links in the root entry point/new documents, source line ranges, heading anchors and balanced code fences. `git diff --check` and the scoped original-source/build/guide diff passed. These are structural/preservation checks, not a compiler run, database test or independent review.
