# Architecture

## Principle

One frontend and one semantic engine: the compiler's. The server links `compiler.frontend.*` and asks it every semantic question through the compiler's tooling API (`compiler/frontend/tooling_queries.sn`, `tooling_facts.sn`, `tooling_completion.sn`). It keeps no symbol table, Type information or diagnostics of its own. The server's own work is the protocol: positions, ranges, JSON, scheduling, caching and talking to the editor.

Text-structure features (folding, selection ranges) and the mapping of last-good results across an edit are the only answers computed from text, because they must work on files that do not parse.

## Modules

| Directory | Module | Role |
|---|---|---|
| `src/` | `main.sn` | Entry point: runs the server loop |
| `src/server/` | `server.sn` | JSON-RPC loop, lifecycle, request dispatch, one handler per method |
| `src/protocol/` | `decode.sn`, `encode.sn`, `serialize.sn`, `model.sn` | LSP wire types, capabilities, JSON writing |
| | `semantic_queries.sn`, `diagnostics.sn`, `code_actions.sn`, `code_lens.sn`, `structure.sn`, `text_document.sn`, `workspace_diagnostics.sn`, `initialize.sn` | Replies per feature family |
| `src/analysis/` | `frontend.sn` | The bridge to the compiler: compilation settings, analysis sessions |
| | `cache.sn` | Analysis snapshots per workspace revision, last-good snapshots |
| | `semantic_queries.sn` | Every semantic answer, from the compiler's tooling API |
| | `refactors.sn` | Extract and inline, checked by the compiler on a copy |
| | `structure.sn` | Folding and selection ranges from the text |
| | `library_index.sn`, `symbol_match.sn` | std names for auto-import; identifier matching for workspace symbols |
| | `keywords.sn` | Keywords in both spellings, generated (`tools/generate_keywords.py`) |
| `src/workspace/` | `documents.sn`, `changes.sn`, `positions.sn` | Open documents, incremental edits, UTF-16 ⇄ UTF-8 positions |
| | `folders.sn`, `package_graph.sn` | Workspace roots, file listing, `supax metadata` |
| | `flycheck.sn` | Check on save |
| `src/transport/` | `stdio.sn` | Content-Length framing |
| | `scheduler.sn` | Reader thread, request queue, cancellation, background check |

## Analysis

### Sessions

Analyses go through the compiler's incremental sessions (`compiler/frontend/incremental_analysis.sn`, `ابن_واجهة_في_جلسة`):

- a **project session** for project-wide requests (references, rename, workspace symbols, reference CodeLens);
- a **document session** for per-document requests (diagnostics, hover, completion, CodeLens, inlay hints).

A session keeps std and unchanged modules analysed and returns the same result as a full analysis. The analysed document is declared open, so an edit re-analyses it and its importers only. When nothing is queued after a reply, the server lets each session prepare the state its next request starts from (`جهز_جلسة_تحليل`).

### Snapshots

A snapshot is one analysed interface (`نتيجة_واجهة_وحدة`) for one revision of the workspace. Snapshots share the interface through `مشترك<…>` (std.sync.arc), so storing, reading and answering never copy it. For each document the last snapshot without errors is kept, so hover, signature help and semantic tokens keep working while the text does not analyse.

Texts of unopened files are re-read only when their size or modification time changed.

## Scheduling and cancellation

Requests run one at a time on the main thread. A reader thread receives frames while a request runs:

- `$/cancelRequest` for the running request sets the compiler's cancellation token (`حالة_إلغاء_واجهة`, an atomic flag); the analysis stops at its next checkpoint and the request answers `RequestCancelled` (-32800);
- `didChange` or `didClose` of the running request's document cancels it the same way, with `ContentModified` (-32801); pull diagnostics answer `ServerCancelled` (-32802) with `retriggerRequest: true`;
- a queued request whose cancellation or document change is already queued answers the same way without running;
- a cancelled analysis is never cached.

If the reader thread cannot start, the server polls stdin with a zero timeout between requests.

The check on save runs the compiler as a separate process on its own thread and hands its report back to the main loop as an internal frame (`$/sultanc/flycheck`), so it never blocks requests.

## Performance

Measured on the final6 checkpoint (2026-11-23) with the compiler sources (`compiler/`, about 640 modules with the layered std) as the workspace and the package graph from `supax metadata`, pausing 1.5 s between edits:

| Request | Time |
|---|---|
| References of `معلومة_العامل` (`precedence.sn`), cold | 9.5 s |
| The same after an edit of `precedence.sn` (median of 4) | 2.6 s |
| Pull diagnostics of the open document after the edit | 0.01 s |
| Completion | 0.32 s |
| `$/cancelRequest` of a running project analysis | answered in 0.15 s (`-32800`, measured on final) |
| Memory | peak 1.30 GB |

After an edit, the references request is the compiler's incremental session re-analysing the edited module and its 56 importers (`SULTANC_ANALYZER_LOG=1`: `analysed 57, reused 585`, 2.7 s), although the edit changes no declaration; the document session re-analyses only the edited module (`analysed 1`, 14 ms). Keeping importers when a module's interface is unchanged is requested from the compiler ([COMPILER_REQUESTS.md](COMPILER_REQUESTS.md), P2).

`SULTANC_ANALYZER_LOG=1` logs each request's time and each session request (state used, modules analysed and reused).

## Distribution

The server is built per target with the compiler's own cross-compilation and linker (`tools/dist.sh`). A release bundle is laid out like a checkout (`build/sultanc-analyzer`, `library/`), so the server finds its standard library the same way in both. The VS Code extension ships one bundle per platform in platform-specific packages; see [RELEASING.md](RELEASING.md).
