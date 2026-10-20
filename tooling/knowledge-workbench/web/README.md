# C++ Knowledge Workbench — browser client

Original local React/TypeScript interface for the workbench API. No remote assets,
fonts, telemetry, browser storage, hosted models, or external providers are used.
Neo4j is the only graph backend; the browser never connects to it directly.
Conversion requires the current complete Neo4j generation with matching settings.
SQLite is server-side conversion history/provenance, not another graph backend.

## Local use

Requires Node 22.12+ (22.x) or Node 24+, npm, and the separately configured Python
workbench service. From this directory:

```sh
npm ci
npm test -- --run
npm run build
```

The Python API serves `dist/` in production. For development, explicitly start the
API on `http://127.0.0.1:8765`, then run `npm run dev` and open the address Vite
prints. `/api` is proxied locally with the original Host header preserved; do not
enable `changeOrigin`, because API Host/Origin checks require the browser origin
and forwarded Host to agree. Do not expose the Vite development server publicly.

Register a root with the Python CLI before using the repository selector:

```sh
knowledge-workbench register /absolute/path/to/repository --name my-repository
```

The CLI and service must use the same registry/state directory. Stop the API
before CLI registration, graph generation or removal; these operations share
its exclusive writer lock. After registration, restart the API and refresh the
repository list. No filesystem path is accepted by the UI.

## Workflow and interpretation

1. Select a registered repository. Page load, repository selection and session
   refresh do not fetch or generate a graph. Choose **Load current graph** to
   explicitly load and freshly verify an existing generation.
2. Choose C++17 or C++20 and assess sources. Assessment shows the selected scope,
   configured size limits, include roots, defines, and diagnostics. This operation
   does not run build scripts.
3. Explicitly generate a graph. The client polls only the job it submitted.
   Cancellation is requested from the API; a late cancellation during publishing
   can be rejected and is shown as an error, not a successful cancellation.
4. Review partial/completeness diagnostics. Filter symbols by name/ID, symbol kind,
   target/TU metadata (when recorded), and recorded relation kind. Distinct TU IDs
   remain distinct; labels are not used to merge symbols.
5. Select a symbol and a citation. Original source is reverified by the API.
   The client additionally checks generation identity before showing an excerpt.
   Source and Markdown are displayed as escaped text, never interpreted as HTML.
6. Optionally request an as-built or human-review Spec Kit-style draft preview. ZIP downloads
   are explicit authenticated blob requests and are checked against the current
   generation. Drafts are not recovered requirements, official Spec Kit
   certification, or a claim of full pinned-template compatibility. No Spec Kit
   tool is installed or executed. ZIPs are verified/generated in memory; downloaded
   copies are unmanaged and cannot be recalled after source or registry deletion.

The SVG index renders at most **36 nodes and 100 links**. The equivalent symbol
table is paginated at **100 rows** and remains available for every matching node.
The evidence rail caps citation buttons at 200 and connected relations at 100,
with visible truncation notices. The graph is an index, not a force simulation or
claim that all displayed symbols call one another. Relation direction and kind
are available in the evidence rail.

Use **Zoom in** and **Zoom out** to inspect the graph at 50–300% of its fitted
size, drag to pan, and choose **Fit graph** to show all displayed nodes again.
The viewport fits its contents at every screen size. Focus the graph canvas to
use `+`/`-` for zoom, arrow keys to pan, or `0` to fit; node Enter/Space activation
and browser zoom shortcuts are preserved. Filters and generation changes reset
the view. Zooming does not increase the 36-node/100-link visualization limit;
the paginated table still contains all matching symbols.

The header independently checks **Neo4j** and **SQLite** after session setup and
every 15 seconds: amber means checking, green means a live query passed, and red
means the check failed. Each has a retry button and a 12-second timeout. The
SQLite check verifies the history schema and queries its tables. These checks
do not load graphs, scan sources or generate anything.

## Conversion and saved history

Choose **Convert code** on the initial page to open **Code conversion**; a selected
repository is preserved, or you can select one there. This opens the conversion
workflow, not an automatic conversion or graph-generation job.
Choose **Refresh graph context** to explicitly load and verify the Neo4j generation.
The conversion page does not fetch graph context on mount, including saved-job links.
Use its profile settings
and assess/select inputs before confirming record assumptions. Missing,
incomplete, changed or profile-mismatched graphs cannot start conversion.
Progress and side-by-side comparisons show the generation used for the draft.
The server independently parses generated output; graph reuse is not target
runtime validation.

**Saved conversions** reopens private SQLite-backed jobs, including after an
API restart with a valid owning browser cookie. Reconnect to obtain the new
CSRF token. Interrupted jobs stop polling and require an explicit new conversion;
they are not automatically retried. Sessions expire after eight hours without
reconnecting. The latest 100 jobs across sessions are retained server-side;
clearing/expiring the cookie does not transfer access to another session.
No browser local/session storage or raw session tokens in SQLite are used.
Previews and downloads require the same current Neo4j generation and source
manifest, including for jobs restored from history.
Older graphs without record-access analysis require regeneration. Saved
conversion recipes created under older safety rules cannot be reopened as
validated output: start a new conversion after regenerating the graph.
If any request establishes stale source or graph context, pending comparisons
and downloads are aborted and their delayed results are discarded.

Switching repositories, refreshing the session, or unmounting aborts pending
requests and polling and discards their results. It does **not** cancel a server
job that was already submitted. Keep the workspace open to observe/cancel that
owned job. A network failure does not imply server cancellation; the owned job's
cancel control remains available, and current graph reload is explicit.

Authentication, CSRF, network, stale-source, missing-generation, job failure, and
partial extraction states are visible. No sample graph or success-shaped fallback
is substituted. Session failures require reconnection; stale generations require
reassessment/regeneration. The client does not automatically retry mutations.

## Validation boundary

Focused Vitest/Testing Library tests exercise session rejection, assessment and
generation failure, cancellation, stale repository/evidence responses, generation
change rejection, HTML escaping, graph bounds/pagination, CSRF, and authenticated
download errors. These use an injected API or mocked transport, not a live Neo4j
instance. Passing a frontend build/test does not establish Neo4j connectivity,
compiler/AST completeness, x86 behavior, or IBM i compatibility.
