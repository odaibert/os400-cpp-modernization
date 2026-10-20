# Modernizing OS/400 C++ for x86 with GitHub Copilot

A teaching repository for big-endian C++ modernization, with original before/after
console examples and an optional local knowledge workbench. The workbench uses
Neo4j-backed structural analysis to prepare guarded conversion drafts and SQLite
to retain private job history. It is not a production IBM i application or a
general OS/400 migration platform.

![Original modernization scenario diagram](images/Code-refactor-diagram.jpg)

The diagram belongs to the original migration guidance; it is not a deployment
diagram for the local knowledge workbench.

## The Problem

The demonstration uses records captured in **big-endian** byte order. Copying
those bytes into native multibyte integer fields on a **little-endian** host
without decoding them can produce silently wrong numeric values. `memcpy`
itself copies the bytes correctly; the representation mismatch is the problem.
The two console examples demonstrate the failure and explicit endian decoding.

The optional workbench adds source-cited exploration and constrained conversion
without changing the original examples, CMake project or four original guides.

## Repository Structure

```
├── CMakeLists.txt                       # Build configuration (CMake 3.16+)
├── LICENSE
├── README.md
├── .github/                            # Copilot/Squad instructions and skills
├── .squad/                             # Team, policies and planning records
├── docs/
│   ├── modernizing-big-endian-cpp-for-azure.md  # Solution guide
│   ├── copilot-modernization-guide.md           # Step-by-step Copilot walkthrough
│   ├── copilot-prompts.md                       # Ready-to-use Copilot prompts
│   ├── replication-task-plan.md                 # Original demonstration task plan
│   ├── workbench-architecture.md                # As-built workbench design and diagram
│   └── reinvention/                            # Historical research and proposal
├── images/                                     # Original scenario and workbench diagrams
├── tooling/
│   └── knowledge-workbench/
│       ├── README.md                           # Setup, operation and safety limits
│       ├── compose.neo4j.yml                    # Explicit local development database
│       ├── src/knowledge_workbench/             # Python API, parser, graph and jobs
│       ├── tests/                              # Backend and opt-in integration tests
│       └── web/                                # React/TypeScript portal and tests
└── src/
    ├── pos_transaction.cpp                      # BEFORE — legacy OS/400 (buggy on x86)
    └── pos_transaction_x86.cpp                  # AFTER  — portable code (correct)
```

## Quick Start: original console examples

### Prerequisites

- A C++ compiler with C++20 support (GCC 10+, Clang 12+, or MSVC 2019+)
- CMake 3.16+ (optional — you can also compile directly with `g++`)

### Build with CMake

```bash
cmake -B build
cmake --build build
```

### Or build directly

```bash
g++ -std=c++17 -o pos_legacy  src/pos_transaction.cpp
g++ -std=c++20 -o pos_modern  src/pos_transaction_x86.cpp
```

### Run

**Legacy code (demonstrates the bug on x86):**

```bash
./pos_legacy    # or ./build/pos_legacy
```

```
Txn ID     : 16777216       ← WRONG (should be 1)
Amount ($) : 2.28295e+07    ← WRONG (should be 50)
Store      : 25600          ← WRONG (should be 100)
Pump       : 1792           ← WRONG (should be 7)
Card       : VISA
```

**Modernized code (expected output for the demonstration record):**

```bash
./pos_modern    # or ./build/pos_modern
```

```
Txn ID     : 1
Amount ($) : 50
Store      : 100
Pump       : 7
Card       : VISA
```

The original examples are independent of Neo4j, SQLite and the web portal.
Native macOS ARM64 execution is not Linux x86-64, IBM i, MSVC or big-endian
target validation.

## Local knowledge workbench

Follow the [workbench setup and operations guide](tooling/knowledge-workbench/README.md)
for Python 3.11+, Node 22.12+ (22.x) or Node 24+, a frontend build, and an
explicitly configured local Neo4j instance. The Python service serves the built
React portal; a separate frontend server is not required.

The [as-built architecture design](docs/workbench-architecture.md) explains the
components, storage ownership, graph/conversion flows and trust boundaries.

![Implemented local workbench architecture](images/knowledge-workbench-architecture.svg)

After completing that setup, register a trusted root and start the portal from
`tooling/knowledge-workbench/`:

```sh
.venv/bin/knowledge-workbench register ../.. --name endian-demo
.venv/bin/knowledge-workbench serve --port 8766
```

Open `http://127.0.0.1:8766/`. Stop the API before CLI registration, generation or
removal; these operations share an exclusive writer lock. Keep the API and
database loopback-only. The dedicated development database disables authentication
explicitly; it is not suitable for an untrusted shared machine.

| Implemented capability | Behavior and boundary |
|---|---|
| Neo4j and SQLite status lights | Independent live checks, with retry controls; connectivity does not prove a usable graph or safe conversion. |
| Explicit graph workflow | Select a repository, assess sources, then choose **Generate graph**. Page load, repository selection and reconnect do not load or generate graphs. **Load current graph** explicitly retrieves an existing generation. |
| Zoomable structural graph | Zoom 50–300%, drag to pan, or **Fit graph**. The SVG shows at most 36 matching nodes and 100 links; the full symbol table is paginated at 100 rows. |
| Guarded code conversion | **Convert code** opens the workflow. Explicitly refresh graph context, assess/select inputs and confirm record assumptions before starting. A complete, current Neo4j generation with matching settings is required. |
| Progress and comparison | Owned conversion jobs expose progress, blockers and source/converted views. Downloads are reviewable drafts, not target-certified builds. |
| SQLite persistence | Private job history and provenance survive restart for a valid owning browser session. SQLite is not a graph backend or an offline Neo4j replacement. |
| Cited document exports | Explicit as-built Markdown and human-review specification drafts; guides and Markdown are not graph ingestion inputs. |

Use **C++20** when analysing this repository: the modernized example uses
`std::endian`, which is unavailable in C++17. A graph generated using C++17 can be
partial; select C++20, reassess and explicitly generate a replacement.

Conversion handles a limited class of fixed-record endian reads, not arbitrary
IBM APIs, DB2 integrations, EBCDIC, packed decimals or recovered business rules.
Original sources are never overwritten. Current source hashes, graph provenance,
parser analysis and saved-recipe safety versions are checked before output is
presented. Generated output is reparsed locally, not built or executed on the
Linux x86-64 or IBM i target.

## Key Concepts

These are migration concerns, not capabilities implemented by the examples or
proof of a particular application's encoding or deployment model.

| Concept | Source concern | Target concern |
|---|---|---|
| Byte order | Big-endian records in this fixture | Decode explicitly for the host's byte order |
| Text encoding | IBM i applications may use EBCDIC; this fixture uses compatible text bytes | ASCII/UTF-8 conversion is separate and not implemented |
| Compiler and ABI | IBM dialects, APIs and record layout need their own assessment | Native parser success is not target compiler or ABI certification |

## Documentation

| Document | Description |
|---|---|
| [Solution Guide](docs/modernizing-big-endian-cpp-for-azure.md) | Endianness, architecture differences, C++ modernization workflow, Azure deployment options, Well-Architected considerations, and assessment checklist. |
| [Copilot Modernization Guide](docs/copilot-modernization-guide.md) | Problem statement, the Copilot prompt, before/after code walkthrough, and gotchas (COMP-3, EBCDIC, struct padding). |
| [Copilot Prompts](docs/copilot-prompts.md) | Copy-paste prompts for endianness refactoring, code explanation, and EBCDIC-to-UTF-8. |
| [Replication Task Plan](docs/replication-task-plan.md) | Step-by-step tasks with Copilot prompts to reproduce the original demonstration and migration guidance. |
| [Workbench setup and operations](tooling/knowledge-workbench/README.md) | Current local capabilities, Neo4j configuration, SQLite retention, conversion rules, troubleshooting and checks. |
| [Workbench architecture design](docs/workbench-architecture.md) | As-built system diagram, component responsibilities, data ownership, graph/conversion lifecycles and design tradeoffs. |
| [Browser workflow](tooling/knowledge-workbench/web/README.md) | Explicit graph actions, zoom/pan controls, connection lights, conversion and saved-job behavior. |

The four original guides describe the teaching example and illustrative migration
scenarios. They are preserved references, not evidence that Azure services,
EBCDIC adapters or production integrations have been deployed.

### Historical reinvention proposal and Squad

The [research and reinvention proposal](docs/reinvention/README.md) records the
initial discovery and phased design. It predates the implemented local workbench
and is not its current inventory or a record of completed future milestones.
Pinecone, embeddings, hosted retrieval, autonomous agents and cloud deployment
remain unimplemented; the proposal does not authorize trials, uploads or spending.

The [Squad roster](.squad/team.md), [mission](.squad/mission.md) and
[project policy](.squad/policies/planning-only.md) describe the configured team
and bounded authorization. Named specialists are not proof of completed reviews.
Ralph remains configured but dormant; no unattended agent loop is part of the app.

## References

- [C++ Language Documentation — Microsoft Learn](https://learn.microsoft.com/cpp/cpp/)
- [Porting and Upgrading C++ Code — Microsoft Learn](https://learn.microsoft.com/cpp/porting/visual-cpp-porting-and-upgrading-guide)
- [Azure Kubernetes Service (AKS)](https://learn.microsoft.com/azure/aks/)
- [Cloud Adoption Framework — Modernize](https://learn.microsoft.com/azure/cloud-adoption-framework/modernize/)
- [GitHub Copilot Documentation](https://docs.github.com/copilot)
- [`std::endian` (C++20)](https://en.cppreference.com/w/cpp/types/endian)
- [`std::byteswap` (C++23)](https://en.cppreference.com/w/cpp/numeric/byteswap)

## License

MIT — see [LICENSE](LICENSE) for details.
