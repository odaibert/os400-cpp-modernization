### 2026-10-19: Integrated reinvention architecture remains a proposal
**By:** Morpheus
**What:** Added `docs/reinvention/README.md` and `reinvention-plan.md`, with source-linked ontology, deterministic ingestion/citation contracts, local-first storage ladder, phase-owned backlog, proposed evaluation gates and rollback. Independent review and user scope approval remain pending. No vendor selection is accepted; JSON/direct search may suffice, SQLite is conditional, Neo4j-only requires a measured gap, and separate Pinecone requires incremental evidence and explicit data/spend approval.
**Why:** Integrate completed discovery and technology research without turning a two-file teaching demo into an unapproved platform or mistaking proposals for implemented capabilities.

**Local configuration correction:** Removed the machine-specific `teamRoot` key from `.squad/config.json`; preserved `version: 1` and `stateBackend: local`. The default local root is portable across checkouts. This supersedes the historical absolute-root bootstrap state documented in assessment §10, not its source/build findings. No database, process, remote operation or application change was made.
