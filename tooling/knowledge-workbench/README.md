# OS/400 C++ knowledge workbench

An additive local tool for exploring C++ declarations, fields, calls and
references in Neo4j, with source evidence, guarded conversion drafts, private
SQLite history and optional Markdown exports. Includes are checked as parser
inputs; the graph is not a complete build or include-dependency model.
The original endian demonstration, CMake project and four original guides are
independent of this tool.

For the repository overview, see the [root README](../../README.md). The
[browser guide](web/README.md) covers interaction details. The
[architecture design](../../docs/workbench-architecture.md) documents the
implemented components, flows, storage and trust boundaries. The
[reinvention documents](../../docs/reinvention/README.md) are historical research
and proposals, not a current feature inventory or completed milestone report.

## Boundaries

- **Application language:** C++ only. Local UTF-8 `.cpp`, `.cc`, `.cxx`, `.h` and
  `.hpp` files. Markdown, README files and build documents are not read or indexed.
  No native IBM i connectivity, EBCDIC conversion,
  arbitrary compile-command execution, or compiler compatibility certification.
  Initial profiles are C++17 and C++20; legacy IBM dialects require representative
  inputs and a separate parser-capability assessment.
- **Storage:** local Neo4j, using the official Python driver. Use the dedicated
  Docker development instance below or an existing authenticated local instance.
  SQLite stores private conversion-job history, progress and provenance only;
  it is not a second graph backend or an offline fallback for Neo4j.
  No automatic database installation.
- **Processing:** local, deterministic extraction. No hosted AI, embeddings,
  telemetry, source uploads, or OpenClaw-related code, assets or dependencies.
- **Retention:** registered root paths, structural metadata, hashes and evidence
  spans, not full source snapshots. Source excerpts are reread only for display.
  Graph metadata, symbol names and downloaded documentation may still be sensitive.

The initial corpus is the two existing C++ examples. Unsupported IBM extensions,
missing declarations and ambiguous calls must remain diagnostics or unresolved
references rather than invented relationships. Success on macOS ARM64 does not
establish IBM XL/ILE C++, IBM i/big-endian or Linux x86 compatibility.

## Setup

Use Python 3.11+ and Node 22.12+ (22.x) or Node 24+. Install dependencies
in this tool's own environment, not in the original C++ project:

```sh
cd tooling/knowledge-workbench
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
cd web
npm ci
npm run build
cd ..
```

The frontend build is served by the local Python API; a second web server is
unnecessary. No external fonts, assets or scripts are required at runtime.

## Neo4j configuration

### Dedicated Docker development instance

With Docker Desktop running, use the pinned Neo4j Community image and dedicated
persistent volume in `compose.neo4j.yml`. From this tool's directory:

```sh
docker compose -p os400-knowledge-workbench -f compose.neo4j.yml up -d --wait
export NEO4J_AUTH_MODE=none
export NEO4J_URI=bolt://127.0.0.1:7687
export NEO4J_DATABASE=neo4j
.venv/bin/knowledge-workbench check
```

The container is `os400-knowledge-workbench-neo4j`; Bolt port 7687 and browser
port 7474 bind to `127.0.0.1` only. Usage reporting is disabled. **Authentication
is deliberately disabled for this local development database:** any local
process can access it. Do not expose the ports, use it on an untrusted shared
machine, or store credentials for it. The workbench requires the explicit
`NEO4J_AUTH_MODE=none`; missing credentials never silently disable authentication.
Ensure these ports are free instead of stopping another project's database.

Stop just this database with:

```sh
docker compose -p os400-knowledge-workbench -f compose.neo4j.yml stop
```

Start it again with the `up` command above. Data remains in the dedicated
`os400-knowledge-workbench-neo4j-data` volume; stopping or removing the container
does not erase the graph. Do not remove that volume unless you intend to delete
all workbench database data.

### Existing authenticated instance

Use a dedicated local database or account where practical. This tool creates
its own repository/generation-scoped graph entities; do not give it a database
administrator account unnecessarily. Review the server's own usage reporting,
authentication, backup and deletion policy separately.
The current adapter creates its workbench schema constraints, so the configured
account needs schema-create privileges as well as access to workbench data.

The default non-secret connection settings are:

```sh
export NEO4J_URI=bolt://127.0.0.1:7687
export NEO4J_DATABASE=neo4j
export NEO4J_AUTH_MODE=required
export NEO4J_USERNAME=neo4j
```

Supply `NEO4J_PASSWORD` through your local shell's hidden input or an approved
secret manager. Do not put a password in a command argument, source file, browser
storage, screenshot or chat. `.env` files are never loaded. Missing credentials
and connection failures are explicit errors, never a successful empty graph.

Authentication defaults to `required`; only `required` and `none` are accepted.
Use `.venv/bin/knowledge-workbench --prompt-password check` to verify an
authenticated connection. The session-protected `/api/health` endpoint also
checks the actual database and returns HTTP 503 when unavailable.

## Workflow

Use the CLI to explicitly register each application root; the browser cannot
browse or register arbitrary filesystem paths. Start with `knowledge-workbench
--help` for commands and profile options.

From `tooling/knowledge-workbench/`, register this repository and start the
foreground application. For the Docker development database, retain the
`NEO4J_AUTH_MODE=none` setting from above:

```sh
.venv/bin/knowledge-workbench register ../.. --name endian-demo
.venv/bin/knowledge-workbench serve --port 8766
```

Open `http://127.0.0.1:8766/`, select `endian-demo`, then assess and generate.
Expand **Assessed sources** to review the C++-only inventory before generation.
Use **C++20** for this repository: `src/pos_transaction_x86.cpp` uses
`std::endian`, which is not available in C++17. The C++17 profile remains useful
for compatible inputs; it is not appropriate for analysing both demo files.
Existing graphs containing Markdown/build inputs must be regenerated after this
scope change. For an authenticated database, add `--prompt-password` before
`serve` or other database commands; it reads a hidden password for that process
only. Set `NEO4J_USERNAME` first. Omit the prompt when credentials are already
provided through the process environment.

For CLI-only operation, copy the opaque repository ID returned by registration
or `list`:

```sh
.venv/bin/knowledge-workbench list
.venv/bin/knowledge-workbench assess REPO_ID --standard c++20
.venv/bin/knowledge-workbench generate REPO_ID --standard c++20
.venv/bin/knowledge-workbench query REPO_ID
.venv/bin/knowledge-workbench docs REPO_ID --kind as-built
.venv/bin/knowledge-workbench docs REPO_ID --kind spec-draft
```

Stop the API before CLI `register`, `generate` or `remove` commands. These
mutations share its exclusive state-directory lock and fail explicitly if a
server or another CLI writer is active. Read-only CLI queries can run while
the API is serving. Browser removal is serialized with job submission, and
active jobs must finish or be cancelled before their repository can be removed.

1. Register a specific local C++ application directory and assess the allowed
   input files. The state directory stores its private absolute path locally;
   browser repository lists show only its name and opaque ID.
2. Select a C++ standard and approved repository-relative include directories.
   No application build, CMake configuration or IBM API call runs during indexing.
3. Explicitly choose **Generate graph**. The browser does not load or generate
   graphs on page load, repository selection or session refresh. To inspect an
   existing generation, choose **Load current graph** instead.
   Review diagnostics and the completeness status before
   using relationships. Native parser support is not an IBM compiler guarantee.
4. Explore symbols and relationships using the CLI or local web interface.
   The **Structural graph** displays a bounded SVG index (first 36 matching
   nodes and up to 100 recorded links) alongside the full paginated symbol table
   (100 rows per page). Use **Zoom in**, **Zoom out** and **Fit graph** (50%–300%
   scale, pointer drag-pan, or `+`/`-`/`0` and arrow keys when the SVG canvas is
   focused) to inspect node labels and connected links without expanding the DOM
   cap; the view resets automatically when filters or generations change.
   Evidence reads recheck source hashes. Changed, added or removed inputs require
   regeneration; stale graphs are not silently presented as current.
5. Optionally preview and download as-built documentation or human-review
   specification drafts. Graph generation does not require documentation export.

The browser uses loopback-only, same-origin requests with a local session and
CSRF protection. Do not expose it through a tunnel, reverse proxy, public bind
address or shared network. A single generation job runs at a time. Cancellation
is available before publication; once publication starts it cannot be cancelled.
Errors and partial extraction are visible in the interface.

## Connection indicators

The header shows separate three-light **Neo4j** and **SQLite** indicators with text labels: amber while
checking, green only after a live database query succeeds, and red when the
database, credentials or local API are unavailable. Checks run after session
establishment and every 15 seconds thereafter, without overlapping requests.
Use **Check Neo4j connection** or **Check SQLite connection** to retry independently.
A check times out after 12 seconds. `/api/health` checks Neo4j;
`/api/health/sqlite` queries the conversion-history tables and checks the SQLite
schema version. Both endpoints require a local session. These checks do not
scan repository sources, load or generate graphs, start Docker or bypass authentication.
A green connection light confirms database access only. Graph completeness,
source freshness, compiler settings and conversion safety are separate checks.

## Troubleshooting

| Symptom | Action |
|---|---|
| No graph shown after opening the page or selecting a repository | Expected: choose **Assess repository** and **Generate graph**, or explicitly **Load current graph**. Connection checks do not generate graphs. |
| Four `compiler_error` diagnostics for `src/pos_transaction_x86.cpp` under C++17 | Select **C++20**, reassess and explicitly generate a replacement. `std::endian` requires C++20; changing the dropdown does not repair an existing generation. Other compiler diagnostics can have different causes. |
| Neo4j indicator is red | Check the dedicated local database, URI and explicit authentication mode. Do not embed passwords in URLs or disable authentication to bypass an authenticated instance. |
| SQLite indicator is red | Check access to the configured private state directory and recover its database/schema as appropriate. Do not delete history or substitute an empty success response to hide an error. |
| Conversion cannot start despite green connection lights | Explicitly **Refresh graph context** and check completeness, source freshness and matching profile settings. Regenerate older graphs and start a fresh conversion when safety rules changed. |
| A saved job is interrupted or its output is outdated | Interrupted jobs never resume automatically. Recheck the graph and start a new conversion; older recipe versions are not revalidated by reopening history. |
| A CLI writer reports `job_store_busy` | Stop the API or other writer using the same state directory before `register`, `generate` or `remove`. |

## Guarded OS/400 C++ conversion

Choose **Convert code** on the initial page or open **Code conversion**
(`/#/conversion`), select and assess a registered repository,
select C++ translation units and explicitly confirm the record assumptions
before choosing **Start conversion**. First generate a complete knowledge graph
on the **Knowledge graph** page with the same C++ profile. Conversion loads that
published Neo4j generation instead of rebuilding its input analysis. Source
hashes, repository identity, completeness and all profile settings must match.
On the conversion page, choose **Refresh graph context** to explicitly load and
verify the current generation; it is not fetched on page load.
**Use graph settings** adopts its profile. Missing, stale, partial,
unavailable or mismatched graphs are explicit errors, not automatic rebuilds.
The separate conversion page shows actual job stages and analysed-file counts,
blockers, and on-demand **Before / after conversion** panels. The job link in
the address bar or **Saved conversions** can reopen a saved job after a server
restart in its still-valid browser session. Navigating away does not cancel a job.
Use **Cancel conversion** to request cancellation.

The initial automatic transformation is deliberately narrow:

- Resolve standalone `memcpy(&record, buffer, sizeof(Record))` statements through
  the native C++ AST; custom `memcpy` functions and ambiguous records are rejected.
  Leading or trailing comments on a standalone `memcpy` statement are preserved
  using comment-masked UTF-8 byte boundaries.
- Support plain structs containing explicitly fixed-width signed/unsigned
  integers and byte fields/arrays. Preserve byte fields, and insert C++20
  big-endian-to-native conversion for multibyte integer fields.
- Require local value-record destinations. Global/static records, reference or
  pointer escapes (including aggregate/brace-initialized reference fields and
  indirect callable or function-pointer/reference bindings), aliased numeric
  fields and unreviewed record-taking calls require manual review, including
  aliases created before the copy. The AST identifies assignments and
  prefix/postfix mutations across the whole function (including loop-carried or
  backward-branch writes that appear lexically before `memcpy`) rather than
  relying on source order or matching field names in source text.
- Add compile-time record-size and field-offset assertions. Padding, unsupported
  layouts, numeric field mutations outside a recognized in-place decode prefix
  and already-generated inputs require manual review rather than speculative
  rewrites.
- Validate generated sources in the existing in-memory Clang input tree without
  writing or executing them. Checks use the installed host compiler/headers,
  **not a Linux x86-64 cross-toolchain or IBM compiler**. The preview and manifest
  explicitly state that target-platform build and execution remain unperformed.

Existing conversions using the reviewed portable 16/32-bit helper pattern
(endian check, compiler-selected byte-swap intrinsics and matching fallback)
are recognized as **Already modernized — unchanged** when every multibyte field
already calls the matching AST-resolved helper in an immediate in-place decode
prefix after `memcpy`. Reviewed endian-helper calls outside a complete immediate
in-place decode prefix (such as out-of-place decodes into another variable or
stream, or extra helper calls after a decoded prefix) block conversion for manual
review so values are never double-swapped. Such unchanged files remain byte-for-byte
identical in comparisons and downloads; an extra byte swap is never inserted.
Recognition is based on the complete helper implementation and call bindings,
not the filename or helper name. Recognized unchanged records receive the same
independent size/offset assertions in a temporary validation view; the assertions
are not added to their downloaded source. Custom compiler defines, unknown conditional
code/intrinsics, incomplete or incorrect field conversions, and numeric
field mutations outside the recognized decode prefix still require manual review.
Selecting both demonstration files therefore converts the legacy example while
preserving the existing x86 example.

This is a migration-draft workspace, not a general OS/400 translator. No broader
IBM application samples have been supplied. Missing headers, incomplete parsing,
conditional/macro-controlled code, nontrivial records and unreviewed external or
declaration-only calls block automatic conversion. Only whole-header guards
with a matching `#ifndef` / `#define` / final `#endif`, no code outside the guard,
and a non-reserved guard name are accepted; `#pragma once` is also supported in
headers. Platform conditionals in translation units are not header guards.
Inventoried headers are audited even when they contain only macros and produce
no declaration nodes. IBM i APIs, DB2 integration, EBCDIC conversion,
packed/zoned decimals and recovered business requirements are **not implemented**.
Source files must already be UTF-8; text fields must already have a
target-compatible encoding. Original comments, buffer-length assumptions,
business logic, unselected translation units and platform integration still need
human review.

Comparisons reread the original inputs and generate the draft in memory.
Changing, adding or removing a supported input invalidates previews/downloads.
The server also verifies the current Neo4j generation and graph-content digest
before and after conversion, comparison and download. A changed generation or
unavailable database requires recovery/regeneration and a new conversion where
applicable. Output validation independently reparses generated C++ in memory;
the stored graph is not proof that a rewrite compiles or behaves correctly.
Graphs generated before the current record-access and callable analysis
(`generation-v4`, `conversion_analysis = 2`) must be regenerated. Saved
recipes carry a safety version (`CONVERSION_VERSION = 3`); older recipes remain
visible as history but cannot be previewed or downloaded under newer safety
rules. Start a fresh conversion after regeneration rather than treating an old
success as revalidated.

SQLite history is stored in `conversions.sqlite3` beside `repositories.json`
under `$XDG_STATE_HOME/os400-knowledge-workbench`, defaulting to
`~/.local/state/os400-knowledge-workbench`. The directory is private (0700)
and database is 0600. It retains the latest 100 conversions across sessions:
request/profile/confirmed assumptions, timestamps, progress, diagnostic results,
source manifests, rewrite recipes, validation environment and Neo4j generation
identity/content digest. It stores neither source snapshots nor a graph copy.
Recipes, paths and diagnostics can still be sensitive. Only eight conversion
jobs are cached in memory; older retained jobs are loaded from SQLite on demand.
Repository removal through either the CLI or browser deletes its local job
history as well as its workbench graph.
Copies/backups of SQLite and downloaded ZIPs need separate retention handling.

An unfinished saved job becomes **Interrupted — start a new conversion** on
restart. It is never silently resumed or marked successful. Completed comparisons
are reconstructed from verified current sources plus saved recipes. Browser
session ownership survives a server restart through a private HttpOnly,
SameSite cookie and an expiring hash in SQLite; no bearer cookie or CSRF secret
is stored in the database. Reconnecting refreshes the CSRF token. Sessions expire
after eight hours without reconnecting; an expired or cleared cookie cannot
recover another session's private jobs. Stop the old server before starting a
replacement: an exclusive runtime lock prevents concurrent servers from
interrupting each other's jobs in the same state directory.

Graph generation and conversion share one worker, so only one runs at a time.
Limits are 20 selected translation units, 250 KB per selected file, 1 MB for the
complete input inventory, 64 fields per converted record and 100 record copies
per selected file. Native parser budgets also apply.

**Download conversion draft** creates an explicit ZIP containing chosen converted
files, inventoried headers unchanged, and a checksum/source-hash manifest with
generation provenance, request/profile assumptions, review and validation
limitations. It is not a complete build-system migration.
Blocked jobs cannot be downloaded as successful conversions. No file is
overwritten and no output directory is created. Conversion reads Neo4j; its
history/results are recorded in SQLite, not published as new graph facts.
Downloaded copies cannot be recalled; review them and build/test on the actual
Linux x86-64 target before use. All conversion routes require the local session;
job status, comparisons and downloads are restricted to their owning session,
and starting/cancelling a job also requires CSRF protection.

## Optional documentation

Markdown remains an optional **output**, never an ingestion input. Editing an
excluded guide does not invalidate a code graph; changing supported C++ inputs
does.

**As-built documentation** describes observed structural facts and their source
citations. Comments and guides do not prove an integration exists or that a test
ran. Byte-order operations, text encoding and ABI layout are distinct concerns.

**Spec Kit-style drafts** are explicit proposals for human review, not recovered
business requirements, completed implementation tasks or official certification.
[GitHub Spec Kit](https://github.com/github/spec-kit) is a Spec-Driven Development
toolkit, not a universal reverse-engineering documentation standard. Its
[existing-project guide](https://github.github.io/spec-kit/guides/existing-projects.html)
does not claim initialization infers specifications.

This tool never installs or executes Spec Kit or writes `.specify/`, agent skills
or the original guides. Review draft requirements and reconcile them with the
official templates of the Spec Kit version you choose before importing them.

Web previews and ZIP downloads are generated in memory after source verification.
ZIP manifests record the generation, source hashes and output checksums.
Downloaded/copied exports cannot be recalled: delete them or regenerate them
when their sources change. Deleting a registered repository removes its
workbench graph metadata; it does not delete application sources or unrelated
Neo4j data. Database backups remain subject to your own retention policy.

## Checks

Run the focused tool checks from this directory:

```sh
.venv/bin/python -m pytest
.venv/bin/python -m ruff check src tests
cd web
npm test -- --run
npm run build
```

An optional live Neo4j check is separate from the normal suite and needs a local
test instance with the authentication mode configured above. Do not treat a
skipped live check as a passed one.
Parser, API and UI tests use isolated test inputs; they must not rewrite the
original demonstration to make checks pass.

With the connection variables already set locally, run this opt-in check from
`tooling/knowledge-workbench/`:

```sh
NEO4J_LIVE_TEST=1 .venv/bin/python -m pytest \
  tests/test_store.py::test_live_neo4j_roundtrip_and_cleanup -q \
  --basetemp ../../.squad/.scratch/knowledge-workbench-live
```

The test uses a unique workbench repository ID and cleans up its graph data.
It needs graph read/write/delete permissions and permission to create three
workbench uniqueness constraints. The test scratch path is workbench-owned;
do not reuse it for application files.

## Data and operational limits

Repository registration is local and explicit. Hidden directories, secrets,
generated/runtime files, symlinks and unapproved paths are not ingestion inputs.
Profiles and parser diagnostics are constrained; unsafe inputs fail explicitly.
Files/bytes, graph/render size, parser work and worker concurrency are bounded.
The implementation's profile validation is authoritative for accepted limits:

| Resource | Default | Maximum |
|---|---:|---:|
| Input files | 200 | 2,000 |
| Bytes per file | 1,000,000 | 5,000,000 |
| Total input bytes | 10,000,000 | 50,000,000 |
| Graph nodes / edges / evidence spans | Fixed caps | 5,000 / 10,000 / 15,000 |
| Diagnostics | Fixed cap | 200 |
| Parser worker deadline | Fixed | 45 seconds |
| Neo4j transaction timeout | Fixed | 20 seconds |

This initial parser intentionally rejects computed includes, absolute/traversal
include paths, `include_next`, import/embed/line directives, unsupported pragmas,
raw string literals and continued preprocessing input before native parsing.
These are explicit capability limits, not claims that such constructs are
invalid C++. Local includes must resolve to approved inventoried files. Profile
defines accept simple names/scalar values only. Missing system headers produce
sanitized diagnostics and partial results. C++ inputs are parsed through an
in-memory virtual tree rather than unrestricted original repository paths.
Unknown or unsupported source formats require a separate capability assessment.

No background watcher, unattended agent, hosted provider, workflow, commit or
cloud provisioning is part of this tool. Docker startup is an explicit operator
command, not an automatic application action. Stop the foreground API with Ctrl-C. Remove
only named workbench-owned artifacts after checking their paths; never reset or
clean unrelated worktree changes.
