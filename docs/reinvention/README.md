# Reinvention planning index

**Status: proposal; [Fact Checker approves as a proposal](review.md), pending user scope approval and remaining specialist reviews.** These documents do not add application capabilities, select a vendor, or authorize implementation or spending.

| Document | Purpose and evidence status |
|---|---|
| [Repository assessment](repository-assessment.md) | Inspected code/docs, binary contract, actual native ARM64 baseline and unverified platforms; bootstrap observations are historical. |
| [Technology research](technology-research.md) | Public documentation research, source-access limitations, storage/retrieval options and conditional experiments; not installed-product validation. |
| [Integrated reinvention plan](reinvention-plan.md) | Proposed architecture, typed evidence contract, deterministic ingestion, query examples, owned backlog, evaluation gates and rollback. |

Read the assessment for what exists, the research for technology claims, and the plan for what could come next. Both original C++ examples and all four original guides remain teaching artifacts. Direct search and local JSON/SQLite may be the final solution; a graph database is not required.

Binding boundaries: [mission](../../.squad/mission.md), [planning-only policy](../../.squad/policies/planning-only.md), [approved team](../../.squad/team.md). Local team state now omits the machine-specific `teamRoot` override; `stateBackend: local` remains explicit. This supersedes only the absolute-root bootstrap configuration described in assessment §10, not its discovery results.

**Review status:** Morpheus authored the synthesis; Fact Checker completed a [bounded independent factual/design-contract review](review.md) on 2026-10-19 and approved the proposal only, not implementation or phase completion. Independent Trinity, Neo, Switch, Tank and Rai reviews remain pending. Named future ownership is not evidence of work performed. Scribe acts only on assignment; Ralph remains configured and dormant.
