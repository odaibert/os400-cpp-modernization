# Historical research and reinvention proposal

**Initial planning snapshot: 2026-10-19. Current documentation refresh: 2026-10-20.**
These documents retain the original discovery, research and proposed milestones.
They are not a current inventory of the application.

## Current implementation versus proposal

The repository now also contains an additive
[local knowledge workbench](../../tooling/knowledge-workbench/README.md):
Neo4j-backed C++ analysis, guarded fixed-record conversion, SQLite job history,
explicit graph actions, database status lights and a zoomable browser graph.
See the [current browser workflow](../../tooling/knowledge-workbench/web/README.md)
and [as-built architecture](../workbench-architecture.md) for implemented behavior,
components and limitations; the [root overview](../../README.md) introduces both
the original examples and the additive workbench.
The original C++ examples and four original guides remain unchanged.

The earlier local JSON/SQLite graph baseline, alternative storage choices,
Pinecone/embedding experiments, hosted retrieval and autonomous agent designs
below remain proposals. In the implemented workbench, **Neo4j is the sole graph
backend and SQLite holds private conversion history/provenance**. Neither this
implementation nor the research establishes production IBM i compatibility,
target-platform execution, cloud deployment or approval for broader services.

**Proposal review status:** [Fact Checker approved the proposal](review.md),
not implementation, spending or completion of all design gates. Later bounded
implementation must not be represented as the independent specialist reviews
listed in the original plan.

## Historical documents

| Document | Purpose and evidence status |
|---|---|
| [Repository assessment](repository-assessment.md) | Inspected code/docs, binary contract, actual native ARM64 baseline and unverified platforms; bootstrap observations are historical. |
| [Technology research](technology-research.md) | Public documentation research, source-access limitations, storage/retrieval options and conditional experiments; not installed-product validation. |
| [Integrated reinvention plan](reinvention-plan.md) | Proposed architecture, typed evidence contract, deterministic ingestion, query examples, owned backlog, evaluation gates and rollback. |

Read the assessment for the **initial inspected snapshot**, the research for
dated technology claims and access limitations, and the plan for proposed future
work. Original source/README line references and observations about the absence
of a graph describe that snapshot; they must not be used as current implementation
evidence. Use the linked workbench documentation and source for the present app.

Binding boundaries: [mission](../../.squad/mission.md), [planning-only policy](../../.squad/policies/planning-only.md), [approved team](../../.squad/team.md). Local team state now omits the machine-specific `teamRoot` override; `stateBackend: local` remains explicit. This supersedes only the absolute-root bootstrap configuration described in assessment §10, not its discovery results.

**Review status:** Morpheus authored the synthesis; Fact Checker completed a [bounded independent factual/design-contract review](review.md) on 2026-10-19 and approved the proposal only, not implementation or phase completion. Independent Trinity, Neo, Switch, Tank and Rai reviews remain pending. Named future ownership is not evidence of work performed. Scribe acts only on assignment; Ralph remains configured and dormant.
