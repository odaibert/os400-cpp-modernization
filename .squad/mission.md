# Mission — discovery before reinvention

Requested by **odaibert**, approved **2026-10-19**. This is a persistent local Squad, not a transient set of agents.

## Objective

Understand the complete existing demo and produce an evidence-grounded, phased plan for using modernization knowledge as graph facts and retrieving that knowledge for agents. Preserve both the deliberately broken legacy demonstration and the portable C++ example. The repository is not an existing knowledge platform, production payment processor, or deployed cloud service.

## Phase-relative gates (no invented deadlines)

| Phase | Accountable owner | Required collaborators | Exit gate |
|-------|-------------------|------------------------|-----------|
| 0 — Ground truth | Morpheus | Trinity, Tank | Complete code/docs inventory; byte and call-flow contract; actual baseline and unavailable checks explicitly separated; no application edits |
| 1 — Knowledge contract | Neo | Trinity, Morpheus, Rai | Proposed typed schema and provenance, deterministic IDs, source spans/revisions, observed vs proposed claims, invalidation/deletion and trust boundaries; manually worked examples reviewed |
| 2 — Retrieval and evaluation design | Switch | Neo, Tank, Fact Checker | Same representative questions compared with direct source/lexical baseline, graph-only and hybrid options; citation, abstention, freshness, latency/cost criteria agreed before prototype |
| 3 — Reinvention decision | Morpheus | All specialists; Rai and Fact Checker reviews | Options/ADRs, preservation and rollback plan, scoped future backlog and explicit go/no-go; unresolved questions and resource implications disclosed |
| Future implementation | Not authorized | User approval required | Separate approval of scope, tooling, data handling, cost and acceptance criteria before any prototype, rewrite or provisioning |

The assessment in `docs/reinvention/repository-assessment.md` seeds Phase 0; bootstrap does not mean independent specialist reviews or later phases are complete.

## Non-goals

- No rewrite, extraction pipeline, graph database, embedding store, application API, agent runtime or UI implementation.
- No paid services, infrastructure provisioning, remote issues/PRs, commits/pushes, dependency installs/upgrades or active GitHub Actions workflows.
- No unattended loops, schedules, watchers or background monitors. Ralph is configured but not running.
- No external transmission of repository code, `.env` reads, credentials, user emails or private customer records.

## Operating references

- `.squad/policies/planning-only.md` — binding execution boundaries.
- `.squad/routing.md` — named ownership and handoffs.
- `.squad/rai/policy.md` and `.squad/fact-checker/policy.md` — retained rich installed governance with project-specific constraints.
