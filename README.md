# Modernizing OS/400 C++ for x86 with GitHub Copilot

A practical guide and working code examples for migrating C++ applications from IBM Power Systems (Big-Endian) to x86/x64 Linux on Azure (Little-Endian), using GitHub Copilot to accelerate the refactoring.

![Code refactor architecture diagram](images/Code-refactor-diagram.jpg)

## The Problem

C++ code written for IBM Power (OS/400, IBM i) stores multi-byte integers in **Big-Endian** byte order. When that code is recompiled for **x86** (Little-Endian) — the architecture behind Azure Virtual Machines — every raw `memcpy` into a struct produces **silently wrong values**. This repository demonstrates the bug and its fix.

## Repository Structure

```
├── CMakeLists.txt                       # Build configuration (CMake 3.16+)
├── LICENSE
├── README.md
├── docs/
│   ├── modernizing-big-endian-cpp-for-azure.md  # Solution guide
│   ├── copilot-modernization-guide.md           # Step-by-step Copilot walkthrough
│   ├── copilot-prompts.md                       # Ready-to-use Copilot prompts
│   └── replication-task-plan.md                 # Tasks to replicate this solution
└── src/
    ├── pos_transaction.cpp                      # BEFORE — legacy OS/400 (buggy on x86)
    └── pos_transaction_x86.cpp                  # AFTER  — portable code (correct)
```

## Quick Start

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

**Modernized code (correct on all platforms):**

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

## Key Concepts

| Concept | IBM Power (Source) | Azure x86 (Target) |
|---|---|---|
| Byte Order | Big-Endian | Little-Endian |
| Text Encoding | EBCDIC | ASCII / UTF-8 |
| Scaling Model | Vertical | Horizontal |
| Compiler | IBM XL C/C++ | GCC / Clang / MSVC |

## Documentation

| Document | Description |
|---|---|
| [Solution Guide](docs/modernizing-big-endian-cpp-for-azure.md) | Endianness, architecture differences, C++ modernization workflow, Azure deployment options, Well-Architected considerations, and assessment checklist. |
| [Copilot Modernization Guide](docs/copilot-modernization-guide.md) | Problem statement, the Copilot prompt, before/after code walkthrough, and gotchas (COMP-3, EBCDIC, struct padding). |
| [Copilot Prompts](docs/copilot-prompts.md) | Copy-paste prompts for endianness refactoring, code explanation, and EBCDIC-to-UTF-8. |
| [Replication Task Plan](docs/replication-task-plan.md) | Step-by-step tasks with Copilot prompts to reproduce this entire solution from scratch. |

### Reinvention proposal — not shipped capabilities

[Research and reinvention plan](docs/reinvention/README.md): an optional, evidence-backed modernization knowledge workbench. This is planning only; no graph, retrieval service, or agent runtime is implemented or approved.

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
