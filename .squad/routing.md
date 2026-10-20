# Work Routing

## Routing Table

| Work Type | Route To | Deliverable / handoff |
|-----------|----------|-----------------------|
| Repository discovery, architecture, boundaries, phased reinvention | Morpheus | Evidence-linked assessment and architecture trade-offs |
| Binary contracts, endian portability, legacy preservation | Trinity | Field/encoding inventory, compatibility and C++ risk review |
| Graph schema, provenance, extraction and change invalidation | Neo | Candidate facts, typed relations, source identity and schema options |
| Retrieval, agent context, tool boundaries and grounded answers | Switch | Baseline comparison and retrieval/agent interface proposal |
| Build baseline, fixtures, evaluation and acceptance gates | Tank | Reproducible validation plan and quality scorecard |
| Session memory, decision inbox consolidation | Scribe | Append-only, redacted local records during explicitly assigned work |
| Work queue status | Ralph | Manual report only; dormant until user requests activation |
| Privacy, prompt injection, external data movement, safety | Rai | Review using `.squad/rai/policy.md` |
| Source verification, counter-hypotheses, contradictory claims | Fact Checker | Review using `.squad/fact-checker/policy.md` |

## Rules

1. Read `.squad/mission.md` and `.squad/policies/planning-only.md` first.
2. Default to bounded direct work. Do not fan out, spawn anticipatory agents, or start background watchers automatically.
3. Morpheus is an architecture specialist, not the coordinator. Squad routes explicitly requested work.
4. No issue creation, labels, PRs, commits, pushes, cloud provisioning, paid services, package installations or upgrades.
5. Scribe records actual activity, never fictional agent participation. Local filesystem operations are valid for the local state backend.
6. Before publishing a future plan, route factual claims to Fact Checker and data/privacy boundaries to Rai when explicitly assigned. Bootstrap does not imply those reviews happened.
7. Preserve approved names and resolve charter paths from repository root, including the scaffold's case-sensitive `agents/Rai` directory.

## Issue Routing

Disabled for this planning mission. Do not poll, create, assign, label or auto-pick-up issues. Record proposed work as phase-relative acceptance gates in planning documents, not remote issues.
