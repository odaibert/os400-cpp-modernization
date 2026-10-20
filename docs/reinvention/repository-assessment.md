# Repository assessment — ground truth before reinvention

**Assessor:** Morpheus, Architecture Lead. **Requested by:** odaibert. **Date:** 2026-10-19.

**Scope:** repository discovery and a phased reinvention plan, not implementation. All observations below concern the original application at revision `d3d183bca292e365cf0eb8a78ebef7ba5ddea3a2` unless explicitly labeled **proposal** or **bootstrap**. Source line references are relative to this document and remain valid because original application files and guides were not edited.

## 1. Executive finding and preservation contract

This is a tiny educational OS/400-to-little-endian C++ demonstration: **two independent console executables, one synthetic record each, four explanatory guides**. There is no production transaction system, actual IBM i integration, knowledge graph, retrieval service or deployed Azure workload. The enterprise workload in the solution guide is a scenario, not an implemented or measured requirement ([scenario, lines 9–18](../modernizing-big-endian-cpp-for-azure.md#L9-L18)).

Preserve both teaching artifacts:

- `pos_legacy` intentionally interprets big-endian record bytes as host-native integers. Its wrong numeric output on an ordinary little-endian machine is the demonstration, not a regression to “fix” ([legacy, lines 33–55](../../src/pos_transaction.cpp#L33-L55)).
- `pos_modern` reads the same bytes and converts four integer fields to native order while leaving four text bytes alone ([modern, lines 92–112](../../src/pos_transaction_x86.cpp#L92-L112)).
- Future knowledge tooling should be an additive, separately approved design around these artifacts, not an excuse to remove the before/after comparison, change wire bytes, or require hosted infrastructure to run a C++ example.

The approved enduring team is recorded in [`.squad/team.md`](../../.squad/team.md); the binding planning mission and gates are [`.squad/mission.md`](../../.squad/mission.md). Bootstrap does not mean all nine members executed work or reviewed this assessment.

## 2. Complete original repository inventory

All original text files listed below were read. Repository inspection found no pre-existing `AGENTS.md`, `CONTRIBUTING.md` or `.github/copilot-instructions.md`; new Squad guidance is bootstrap material, not an original contributor convention.

| Exact repository path | Evidence / purpose | Boundary |
|---|---|---|
| `src/pos_transaction.cpp` | [1–79](../../src/pos_transaction.cpp#L1-L79): legacy commentary, five-field `TxnRecord`, `processTxn`, `main` | Synthetic in-memory fixture; not an IBM-source import or executable IBM i test record |
| `src/pos_transaction_x86.cpp` | [1–130](../../src/pos_transaction_x86.cpp#L1-L130): C++20 endian helpers, same fields, size guard, converted processing, fixture | Independent executable; no reusable library/exported application API |
| `CMakeLists.txt` | [1–12](../../CMakeLists.txt#L1-L12): CMake 3.16, project `simple-cpp-x86`, default C++20, C++17 legacy override, two executable targets | No dependencies, install/package rules, tests, warning flags or platform matrix |
| `README.md` | [1–76](../../README.md#L1-L76): explanation and quick start; [78–108](../../README.md#L78-L108): concept table, guide links and references | Friendly entry point; universal claims need qualifications below |
| `docs/modernizing-big-endian-cpp-for-azure.md` | [1–115](../modernizing-big-endian-cpp-for-azure.md#L1-L115): scenario/endian/platform background; [119–202](../modernizing-big-endian-cpp-for-azure.md#L119-L202): modernization/deployment proposals; [206–307](../modernizing-big-endian-cpp-for-azure.md#L206-L307): prompts/code/output; [310–370](../modernizing-big-endian-cpp-for-azure.md#L310-L370): discovery/checklists/references | Azure components, sub-millisecond latency, scale and datacenter exit are narrative aspirations, not repository capabilities |
| `docs/copilot-modernization-guide.md` | [3–82](../copilot-modernization-guide.md#L3-L82): rationale/prompt; [86–279](../copilot-modernization-guide.md#L86-L279): duplicated before/after snippets; [283–343](../copilot-modernization-guide.md#L283-L343): explanation/gotchas/manual validation; [348–383](../copilot-modernization-guide.md#L348-L383): references | Not a generated-code provenance log, real migration benchmark or exact source mirror |
| `docs/copilot-prompts.md` | [9–65](../copilot-prompts.md#L9-L65): explain/refactor prompts; [69–97](../copilot-prompts.md#L69-L97): EBCDIC-generation prompt and usage tips | Prompt text is not an implemented EBCDIC utility or automated agent pipeline |
| `docs/replication-task-plan.md` | [7–158](../replication-task-plan.md#L7-L158): prerequisites and code/build reproduction; [161–337](../replication-task-plan.md#L161-L337): explain/stretch utility/docs prompts; [340–480](../replication-task-plan.md#L340-L480): repository/commit/Pages instructions; [484–509](../replication-task-plan.md#L484-L509): checklist and estimates | Reproduction instructions are not task-completion evidence; do not execute commit, push or provisioning examples during this mission |
| `_config.yml` | [1–3](../../_config.yml#L1-L3): Cayman Jekyll theme/title/description | Pages metadata, not proof of a configured/live Pages deployment |
| `images/Code-refactor-diagram.jpg` | [Referenced by README line 5](../../README.md#L5) and [solution guide line 127](../modernizing-big-endian-cpp-for-azure.md#L127); inspected file metadata: JPEG, 1024×299 | Static illustration, not runtime architecture evidence; no OCR or image-content validation claimed |
| `.gitignore` | [Original lines 1–27](../../.gitignore#L1-L27): build/binary/editor/CMake ignores | Squad init subsequently appended runtime ignores; original exclusions retained |
| `LICENSE` | [1–21](../../LICENSE#L1-L21): MIT grant, notice and warranty disclaimer | License text does not establish correctness, safety or production fitness |

There were no original dependency manifests, headers, tests, fixtures on disk, Dockerfiles, deployment manifests, GitHub Actions workflows, databases or application configuration files. The directory tree is fully accounted for by these original tracked paths. No `.env` files were read.

## 3. Binary data contract and call/data flow

### Fixture bytes and field interpretation

Both `main` functions construct the same **16-byte** simulated big-endian input ([legacy 58–73](../../src/pos_transaction.cpp#L58-L73), [modern 115–124](../../src/pos_transaction_x86.cpp#L115-L124)). Offsets below are intended wire positions and were also confirmed for the modern struct on the native host; they are not an independently supplied IBM file specification.

| Byte offset | Field / width | Fixture bytes | Intended value | Legacy native little-endian value |
|---|---|---|---|---|
| 0–3 | `txnId`, `uint32_t` | `00 00 00 01` | 1 | `0x01000000` = 16,777,216 |
| 4–7 | `amountCents`, `uint32_t` | `00 00 13 88` | 5,000 cents | `0x88130000` = 2,282,946,560 cents |
| 8–9 | `storeNumber`, `uint16_t` | `00 64` | 100 | `0x6400` = 25,600 |
| 10–11 | `pumpNumber`, `uint16_t` | `00 07` | 7 | `0x0700` = 1,792 |
| 12–15 | `cardType`, `char[4]` | ASCII-host literal bytes `56 49 53 41` | `VISA`, no trailing NUL | `VISA` on the tested host |

`amountCents / 100.0` is a presentation calculation, not a mutation of the record. The wrong little-endian amount is 22,829,465.60 dollars before default stream formatting; it prints `2.28295e+07`. The modern fixture prints `50`, not a fixed-format `50.00` ([legacy 49–54](../../src/pos_transaction.cpp#L49-L54), [modern 105–111](../../src/pos_transaction_x86.cpp#L105-L111)).

### Legacy path

1. The legacy translation unit includes only standard stream, memory-copy and integer headers ([11–13](../../src/pos_transaction.cpp#L11-L13)).
2. `main()` constructs the local `const char buffer[]`, prints a heading, calls `processTxn(buffer)`, returns 0 ([58–79](../../src/pos_transaction.cpp#L58-L79)).
3. `processTxn(const char*)` allocates a local `TxnRecord` and copies `sizeof(TxnRecord)` bytes with `std::memcpy` ([42–47](../../src/pos_transaction.cpp#L42-L47)).
4. It reads host-native unsigned integer fields without conversion, prints the divided amount, and writes exactly four card bytes using `std::cout.write` ([49–55](../../src/pos_transaction.cpp#L49-L55)).

No actual file is opened and no Data Queue is called: those are fixture comments. There is no pointer overlay/reinterpret-cast in the executable; `memcpy` into a properly aligned local object avoids the unaligned-dereference problem that a cast could introduce. The defect shown is the numeric interpretation of the copied bytes.

### Modern path

1. `<bit>` provides C++20 `std::endian` ([10–13](../../src/pos_transaction_x86.cpp#L10-L13)).
2. `main()` follows the same fixture → heading → `processTxn` → success path ([115–130](../../src/pos_transaction_x86.cpp#L115-L130)).
3. The same struct fields are declared at [72–78](../../src/pos_transaction_x86.cpp#L72-L78), with `static_assert(sizeof(TxnRecord) == 16)` at [80–82](../../src/pos_transaction_x86.cpp#L80-L82).
4. After `memcpy`, two 32-bit fields call `fromBigEndian32` and two 16-bit fields call `fromBigEndian16` ([92–103](../../src/pos_transaction_x86.cpp#L92-L103)).
5. Each helper returns unchanged on native big-endian; otherwise it selects GCC/Clang builtins, MSVC intrinsics, or manual shift/mask operations through preprocessor branches ([31–63](../../src/pos_transaction_x86.cpp#L31-L63)).
6. The identical presentation code emits corrected integers and unchanged card bytes ([105–112](../../src/pos_transaction_x86.cpp#L105-L112)).

The two global `TxnRecord` / `processTxn` names are in separate targets, not shared declarations or a common library. Any future symbol graph must identify them by translation unit/target rather than collapse them into one symbol. Combining both sources into one executable would also duplicate `main`; the current build correctly keeps them separate.

### Build and runtime dependencies

`CMakeLists.txt` creates `pos_legacy` from one source with C++17 and `pos_modern` from the other with C++20 ([1–12](../../CMakeLists.txt#L1-L12)). Runtime dependencies visible in application source are the C++ runtime/standard library and stdout. There is no CLI parsing, network, persistence, external library, environment-based behavior, configuration loader, stateful business logic, concurrency or service lifecycle.

## 4. Actual baseline — executed, not inferred

**Environment observed:** macOS, `arm64`, `/usr/bin/c++`, Apple Clang **21.0.0** (`clang-2100.3.34.2`), target `arm64-apple-darwin27.0.0`. A compiled `<bit>` probe confirmed native little-endian. This is **not** an x86 Linux/Azure or IBM i execution.

The available direct-build route was used (as permitted by [README 41–46](../../README.md#L41-L46)), with additional warning flags. Final assertion run used the unique repository-local build directory `.squad/.scratch/baseline-20261019T124429-40967`, removed in a `finally` cleanup. No build artifacts remain.

```sh
c++ -std=c++17 -Wall -Wextra -Wpedantic src/pos_transaction.cpp -o "$BUILD/pos_legacy"
c++ -std=c++20 -Wall -Wextra -Wpedantic src/pos_transaction_x86.cpp -o "$BUILD/pos_modern"
"$BUILD/pos_legacy"
"$BUILD/pos_modern"
```

Here `$BUILD` denotes that unique directory, not an existing configuration requirement. Both compiles exited 0 without emitted diagnostics; both programs exited 0. A Python assertion driver checked every field-output line exactly:

| Output | Legacy observed | Modern observed |
|---|---|---|
| `Txn ID` | `16777216` | `1` |
| `Amount ($)` | `2.28295e+07` | `50` |
| `Store` | `25600` | `100` |
| `Pump` | `1792` | `7` |
| `Card` | `VISA` | `VISA` |

A separate C++20 probe included the modern source with its `main` renamed only in the probe translation unit. It checked actual `std::endian`, `sizeof` and `offsetof`; asserted output was `native_little=1 sizeof=16 offsets=0,4,8,10,12`. No application file was modified.

**Unavailable / not performed:** `cmake` is absent from `PATH` (`shutil.which('cmake')` returned `None`), so CMake configure/build/CTest were **not** run and no tool was installed. No existing test runner exists. GCC, MSVC, Linux x86, IBM i/big-endian, mixed-endian, C++23 snippets, malformed inputs, sanitizers, fuzzing, generated assembly, performance/load tests, external URLs or live Pages/cloud deployment were not validated. No claims of cross-platform certification or independent Tank/Rai/Fact Checker review are made.

## 5. Correctness, portability and documentation qualifications

These are **observations/risks**, not changes implemented in this mission.

| Finding and evidence | Accurate interpretation / future requirement |
|---|---|
| **Unsized input precondition:** both `processTxn(const char*)` functions copy `sizeof(TxnRecord)` without a length/null check ([legacy 42–47](../../src/pos_transaction.cpp#L42-L47), [modern 92–96](../../src/pos_transaction_x86.cpp#L92-L96)) | Supplied 16-byte arrays are valid on this tested ABI. A future external-input parser must reject truncated/null data before copy; current API is not safe for arbitrary caller buffers. No external attack surface exists in the current hardcoded demo. |
| **ABI, not a wire schema:** native struct layout is copied directly; only the modern file has a 16-byte size guard ([legacy 24–30](../../src/pos_transaction.cpp#L24-L30), [modern 72–82](../../src/pos_transaction_x86.cpp#L72-L82)) | Current native offsets were verified. Size alone is not a complete portable format contract: field offsets, integer/byte widths, encoding and ABI must be explicit. An unsupported legacy layout could copy beyond the fixture. A future parser could decode explicit offsets or strengthen assertions without silently changing the teaching example. |
| **“Correct on all platforms” is too broad:** [README 64–76](../../README.md#L64-L76), [CMake comment 11–12](../../CMakeLists.txt#L11-L12), helper logic [31–63](../../src/pos_transaction_x86.cpp#L31-L63) | Evidence supports the fixed fixture on tested ordinary little-endian ARM64. Helpers assume every non-big native order is little-endian; C++ permits `std::endian::native` to be neither. Exact-width types, ABI, standard library and compiler support also constrain portability. No big-endian run occurred. |
| **`memcpy` is not intrinsically broken:** [README line 9](../../README.md#L9) says “every raw `memcpy` into a struct” produces wrong values | Failure requires a mismatched multi-byte representation and subsequent numeric interpretation. Matching-order data, byte arrays and explicit decoding are counterexamples. Copying bytes alone does not alter/corrupt the source bytes. |
| **Platform generalizations:** [README 78–85](../../README.md#L78-L85), [solution guide 75–95](../modernizing-big-endian-cpp-for-azure.md#L75-L95) | Treat endian order as a property of the actual source format and target ABI, not a universal statement about all Power configurations, all Azure compute, or all C++ data. Vertical/horizontal scaling are architectural choices, not properties proved by this code. |
| **Text encoding is separate:** fixture literals at [modern 118–123](../../src/pos_transaction_x86.cpp#L118-L123); EBCDIC discussion at [walkthrough 317–322](../copilot-modernization-guide.md#L317-L322) | `VISA` uses host character literals, ASCII bytes on the tested host. No EBCDIC input/conversion, CCSID selection or UTF-8 error handling exists. Leaving text unswapped is correct for endianness, not an EBCDIC conversion. |
| **Intrinsic/header coverage:** MSVC branches at [modern 38–39, 58–59](../../src/pos_transaction_x86.cpp#L31-L63), headers at [10–13](../../src/pos_transaction_x86.cpp#L10-L13) | MSVC intrinsic declarations/header requirements and library support need explicit compile validation. No dedicated MSVC declaration header is included. Clang success does not validate those preprocessor branches or the manual fallback. |
| **Branch elimination is not zero computation:** [walkthrough 285–296](../copilot-modernization-guide.md#L283-L296), [solution guide 276](../modernizing-big-endian-cpp-for-azure.md#L276) | `if constexpr` resolves the condition at compile time; little-endian conversions still perform swaps/shifts. “Zero runtime cost” overstates “no runtime endian-dispatch branch.” No instruction-count or latency measurement was performed. |
| **Formatting/semantics:** [modern 106–111](../../src/pos_transaction_x86.cpp#L106-L111) prints unsigned fields and floating-point dollars | Fixed-width `cout.write` is appropriate for a non-NUL-terminated array; don't replace it with C-string output. There is no card validation, signed amount/refund model, domain-range check, fixed currency formatting or production accounting contract. Those require actual requirements, not assumptions. |
| **Documentation drift:** walkthrough [157–164](../copilot-modernization-guide.md#L157-L164) prints `2.28395e+07`; [source 69](../../src/pos_transaction.cpp#L69) produces `2.28295e+07` on this host | That walkthrough amount is a typo relative to the fixture, observed baseline, README and replication plan. Document copies are supporting material, not authoritative generated facts. |
| **C++ version drift:** [solution guide 251–276](../modernizing-big-endian-cpp-for-azure.md#L251-L276) uses `std::byteswap` with a “C++20/23” include comment | `std::byteswap` is C++23, unlike C++20 `std::endian`. The real executable uses intrinsics/fallbacks, not `std::byteswap`; a C++20 build promise should not be inferred for that standalone snippet. |
| **Packed decimal illustration:** [walkthrough 302–312](../copilot-modernization-guide.md#L302-L312) labels `01 23 45 0C` as 12345 | BCD nibbles before sign `C` read `0,1,2,3,4,5,0` (123450), not 12345 under the stated convention. The example should be reverified before reuse; no COMP-3 parser is present. This assessment leaves the original guide unchanged. |
| **Replication plan is not an exact implementation manifest:** [133–147](../replication-task-plan.md#L133-L147) requests warnings and project `BigEndianMigrationDemo`; [407](../replication-task-plan.md#L407) says three docs | Actual CMake uses `simple-cpp-x86` and adds no warning flags; there are four original guides. The stretch EBCDIC task [187–205](../replication-task-plan.md#L187-L205), commit and Pages steps [411–480](../replication-task-plan.md#L411-L480) do not prove a utility, commit operation or live deployment here. |

Original README/source/guide language was not edited as part of this bounded assignment. These qualifications prevent a future graph from converting broad prose into false repository facts. General industry claims and the guide's external references were read but not independently web-verified.

## 6. Existing versus absent capabilities; demo versus production

| Area | Existing evidence | Absent / proposed only |
|---|---|---|
| Binary handling | One hardcoded fixture, native copy, four endian conversions, stdout ([modern 92–129](../../src/pos_transaction_x86.cpp#L92-L129)) | Real file/queue/network ingress, size/error handling, serialization/writeback, schema versions |
| IBM i migration | Simulated big-endian bytes and explanatory comments ([legacy 58–73](../../src/pos_transaction.cpp#L58-L73)) | OS/400 APIs, IBM XL build artifacts, customer code, actual Data Queue exports |
| Encoding/data types | Unsigned 16/32-bit integers and four native text bytes ([modern 72–78](../../src/pos_transaction_x86.cpp#L72-L78)) | EBCDIC conversion, packed decimal, floating-point wire formats, signed/refund records |
| Quality | Manual compile/run instructions ([README 27–76](../../README.md#L27-L76)); this assessment's native checks | Automated regression fixtures, malformed-input tests, CTest/CI, cross-platform assurance |
| Deployment | Pages theme metadata and architecture prose ([solution guide 129–201](../modernizing-big-endian-cpp-for-azure.md#L129-L201)) | Containers, cloud resources, IaC, workflows, monitoring, scale/latency evidence |
| Knowledge/agents | Human-written prompts ([prompts 9–97](../copilot-prompts.md#L9-L97)); new local Squad process files | Graph schema/database, extraction/index, embeddings, retrieval API, agent runtime, model access, evaluation corpus |

**Production requirements are not established by the demo.** The guide's high-volume/sub-millisecond scenario is not a measured SLA. Payment compliance, idempotency, refunds, transactional durability, queue ordering, backpressure, authentication, observability, capacity and failure recovery would need discovery from a real owner before implementation. None should be imposed as invented requirements on this teaching repository.

## 7. Modernization knowledge suitable for graph representation — proposal

**No graph has been built.** Start with a small, manually reviewed evidence model and compare it to plain structured records and direct source search. Candidate entity types: `SourceRevision`, `File`, `BuildTarget`, `Symbol`, `RecordField`, `WireFormat`, `Fixture`, `ConversionRule`, `Risk`, `DocumentationClaim`, `Observation`, `Decision`, `Owner`, `AcceptanceGate`.

Examples of grounded candidate facts (not deployed schema):

| Candidate subject → relation → object | Evidence / status |
|---|---|
| `CMakeLists.txt::pos_legacy` → `compiles` → `src/pos_transaction.cpp`; → `requires_standard` → C++17 | [CMake 7–9](../../CMakeLists.txt#L7-L9), observed |
| `CMakeLists.txt::pos_modern` → `compiles` → `src/pos_transaction_x86.cpp`; → `requires_standard` → C++20 | [CMake 4–5, 11–12](../../CMakeLists.txt#L4-L12), observed |
| `modern::processTxn` → `calls` → `fromBigEndian32` / `fromBigEndian16` | [modern 99–102](../../src/pos_transaction_x86.cpp#L99-L102), observed |
| `modern::TxnRecord.amountCents` → `wire_order` → big-endian; → `wire_width` → 4; → `presented_as` → cents divided by 100.0 | [fixture 119–120](../../src/pos_transaction_x86.cpp#L119-L120), [output 107](../../src/pos_transaction_x86.cpp#L107), derived intended contract, not externally verified IBM specification |
| `fixture VISA` → `expected_output_on` → tested native platform values | Section 4 command observation; attach compiler/architecture/run metadata, never infer all-platform success |
| `README all-platform claim` → `qualified_by` → mixed-endian/ABI/untested-toolchain risks | [README 64](../../README.md#L64), [helpers 31–63](../../src/pos_transaction_x86.cpp#L31-L63), assessed |
| `EBCDIC conversion` → `mentioned_in` → prompt 4; → `implementation_status` → absent in original tracked source inventory | [prompts 69–80](../copilot-prompts.md#L69-L80); absence is bounded to the inspected revision |
| `Phase 1 graph contract` → `owned_by` → Neo; → `depends_on` → accepted Phase 0 inventory | [mission](../../.squad/mission.md), proposed future work |

Each future fact needs a deterministic ID, repository/revision, path, meaningful span, extractor/version or named human derivation, observed/derived/proposed status, confidence and evidence links. Duplicate symbol names must include target/file identity. A line span alone is unstable after edits; retain revision/content identity and invalidate dependent claims on changes. Attach environmental scope to runtime observations. Model contradictions explicitly instead of overwriting an old assertion.

**Trust boundary proposal:** original guides and future retrieved text are untrusted evidence, not executable instructions. Exclude `.env`, secrets and user emails; do not ingest private records or send code externally. Define source allowlists, deletion/retention, path normalization and access constraints before storage. Squad's local memory scaffolding is not an application graph or an embedding index.

**Retrieval questions worth testing:**

1. Why does transaction 1 become 16,777,216 in the legacy executable?
2. Which exact fields are swapped, which functions do it, and why is `cardType` not swapped?
3. What supports the assertion that this fixture is 16 bytes, and what remains ABI-dependent?
4. Is EBCDIC or COMP-3 conversion actually implemented? Return an evidence-bounded negative answer.
5. Is the code proven on x86 Linux or IBM i? Abstain from unsupported certification.
6. Which statements in the guides conflict with source/build or measured output?
7. If `amountCents` changes type or offset, which proposed facts, assertions and explanations become stale?

These questions exercise cross-file provenance and negative answers; for this tiny corpus, direct reading or lexical search may remain better than GraphRAG. A useful graph must demonstrate added value, not merely draw the existing call chain.

## 8. Concrete phased action and acceptance gates — proposal, no deadlines

| Phase | Named accountable owner | Concrete next action | Acceptance gate before advancing |
|---|---|---|---|
| 0 — Ground truth | **Morpheus** | Deliver this inventory/flow and preservation contract; **Trinity** reviews binary/layout assumptions; **Tank** reviews reproducibility and missing-platform matrix | Every original source/doc accounted for; observed behavior separated from narrative; review corrections captured; unavailable CMake/target runs explicitly left open |
| 1 — Knowledge contract | **Neo** | Work a minimal schema and a handful of manually cited facts, including duplicated symbols, contradictions and absent capabilities; **Trinity** checks semantics; **Rai** reviews data boundaries | Deterministic source IDs/revision spans, typed relations, observed/proposed flags, refresh/deletion story; reviewers can trace every sample fact to evidence; no database/service selection assumed |
| 2 — Retrieval/evaluation design | **Switch** | Specify direct-source/lexical, graph-only and hybrid alternatives on the same questions; **Tank** defines judged answers, citation accuracy, completeness, abstention/freshness and latency/cost measurement method | Agreed evaluation set and acceptance thresholds before any prototype; fair simple baseline; prompt-injection and no-external-code constraints; **Fact Checker** challenges claims and unsupported superiority assertions |
| 3 — Reinvention plan / decision | **Morpheus** | Integrate evidence, technology options and preservation/rollback strategy into explicit architecture decisions; name a scoped future backlog | Comparative rationale, phase dependencies and unresolved risks visible; **Rai** / **Fact Checker** reviews recorded if performed; user chooses go/no-go before implementation, dependencies, services or provisioning |
| Session handoff | **Scribe** | On explicit assignment, append real decisions/lessons and maintain local memory | No invented participation, no overwritten histories, no automatic commit |
| Work visibility | **Ralph** | Remain configured and dormant; manual status only on explicit request | No watcher, heartbeat, schedule, issue polling or active loop |

The concurrently researched technology document is outside this assignment; this assessment neither edits nor depends on its content. No later-phase outcome is claimed complete.

## 9. Open design questions and blockers

- **Purpose:** teach this demo better, assist larger future codebase modernization, or both? Which user questions justify graph relationships over direct source retrieval?
- **Corpus:** only checked-in code/docs, or future IBM record specifications and additional repositories? What licensing/privacy constraints apply?
- **Authority:** should source, executable observations and guide prose have explicit precedence? How are disputed or stale claims exposed to an agent?
- **Storage:** would versioned JSON/SQLite suffice before a graph database? Is RDF/property graph traversal needed at all at this scale?
- **Retrieval/runtime:** deterministic tools only or optional local models later? What is the approved cost/token budget and external-data policy? No provider is selected.
- **Compatibility:** which concrete Linux/compiler/IBM i targets matter? Which actual record layouts, code pages and error semantics are authoritative?
- **Evaluation:** which expected answers, citation/freshness thresholds and useful latency targets will the owner accept? No performance numbers are invented.
- **Immediate validation blocker:** CMake is not installed; alternative direct builds succeeded. Target-platform, fallback/MSVC and independent specialist reviews remain open, not failed checks.

## 10. Bootstrap persistence and all observed scaffolder side effects

The installed **Squad CLI 0.11.0** was used once:

```sh
squad init --no-workflows --state-backend local
```

It created `.squad/` with empty team/routing/casting state, local memory scaffolding/configuration, built-in charters/histories, RAI and Fact Checker rich policies/audit trails, identity files, ceremonies, decisions, `.first-run` and a copied template library. It installed `.github/agents/squad.agent.md` and **19** `.github/skills/*/SKILL.md` files, created `.gitattributes`, appended `.gitignore`, created `.mcp.json` and `.copilot/mcp-config.json`. Its output reported removing a stale generated `squad_state` entry from the project Copilot config after placing it at repository root.

**Important inspected defaults and corrections:**

- Personal-Squad discovery initially wrote `teamRoot` pointing outside this repo. It was corrected to `<repo-root>/.squad`; `stateBackend` remains explicitly `local`. No personal team files were modified.
- Generated `.mcp.json` used `npx -y @bradygaster/squad-cli@insider state-mcp`, which could download on later startup. It now uses installed **`squad state-mcp`**. The generated unused `EXAMPLE-github` MCP server was removed, leaving `.copilot/mcp-config.json` with no servers. `squad state-mcp --help` confirmed the installed command exists; no server was started or connectivity claimed.
- Approved roster/charters/starter histories, Matrix registry/snapshot, mission, project policy, routing and manual ceremonies were filled in. Full installed Rai/Fact Checker methodology was retained with project-specific planning/privacy constraints and a corrected Fact Checker “different reviser” rule.
- `.github/copilot-instructions.md` and an explicit project override in the generated Squad agent prevent generic eager spawning, issue enforcement, upgrades and commit recipes from overriding this mission. Ralph's charter explicitly says dormant.
- `.gitattributes` contains `merge=union` for decisions, histories, logs and both audit trails. It does not require a custom merge driver. The binding project policy requires append-only records.
- No `.github/workflows/` or active heartbeat was installed. The scaffolder copied inert workflow examples under `.squad/templates/workflows/`; these are reference templates, not enabled GitHub Actions.
- **`.git/config` unchanged:** before/after local settings were identical (`core.*`, existing origin URL/fetch and `branch.main.*` only). No custom merge config or `core.hooksPath` appeared. Post-init inspection found no non-sample hook files in `.git/hooks/`; no hook installation was reported. A separate pre-init hook-directory snapshot was not taken.
- No install/upgrade command, application edit, issue, commit, push, paid service, provisioning, scheduler or unattended process was performed. The initializer's generic “Workflows & CI” completion banner did not mean workflows were enabled.

Durable files persist locally without a commit; committing/pushing is intentionally outside authorization. The initialized `.squad/decisions.md` remains Scribe-owned; Morpheus's decision is in the ignored local `.squad/decisions/inbox/` drop-box, with durable mission/policy files carrying the approved boundaries.

### Bootstrap validation results

- Parsed every initialized `.squad/**/*.json` file plus both MCP configuration files.
- Confirmed exact `## Members` header, nine entries, all charter/history paths, all approved names, and registry/snapshot key/name agreement.
- Confirmed local backend/root, installed-command MCP configuration and no project GitHub Actions workflow directory.
- Checked assessment relative links and source line ranges against actual file lengths.
- Verified `merge=union` attributes for decisions, a representative history and both audit trails.
- `git diff --check` passed for tracked changes; explicit original-source/build/docs diff was empty. No application behavior changed.
- Confirmed no scratch build artifacts or non-sample hooks remain. These are structural checks, not separate agent reviews.
