# Configuration

## Starting the server

Editors start `sultanc-analyzer` with no arguments; it speaks LSP over stdin and stdout. Standard output carries only LSP frames; logs go to standard error.

The server finds the standard library (`library/core`, `library/alloc`, `library/std`) as the compiler does (`compiler/driver/std_location.sn`):

1. `$SULTANC_STD`, the library directory;
2. `./library` in the working directory;
3. next to the server: `<bin>/library`, `<bin>/../library` (a checkout's `build/sultanc-analyzer`), `<bin>/../lib/sultanc/library` (the toolchain: `~/.supax/bin/sultanc-analyzer` and `~/.supax/lib/sultanc/library`).

So an installed server starts from any directory. Documents and workspace folders arrive as absolute URIs, so projects can be anywhere.

## initializationOptions

| Option | Type | Default | Meaning |
|---|---|---|---|
| `language` | `"auto"`, `"ar"`, `"en"` | `"auto"` | Language of diagnostics, hover labels and CodeLens titles. `auto` follows each document's surface language; an Arabic client `locale` also selects Arabic |
| `checkOnSave` | boolean | `true` | Run the compiler's check after each save and at start, and publish diagnostics of unopened files |
| `checkEntries` | string array | `[]` | Entry files for the check, absolute or relative to the first workspace folder. Empty: `src/main.sn` or `main.sn` of each folder or of its Supax package |
| `compilerPath` | string | `""` | The compiler the check runs |
| `lensRun` | boolean | `true` | "▶︎ Run" / "Debug" above the program entry and "▶︎ Run Test" / "Debug" above each test |
| `lensReferences` | boolean | `false` | "N references" above declarations. Off by default, as in rust-analyzer: each lens is a project-wide query |
| `bidiIsolates` | boolean | `false` | Wrap each hover line that starts in Arabic in Unicode isolates (RLI … PDI), so an Arabic signature reads right to left inside a left-to-right hover. For clients that render hover Markdown as HTML (VS Code sends `true`); terminal clients show the controls as characters |
| `closingBraceHintsMinLines` | number | `25` | Closing brace hints after declarations of at least this many lines; `0` turns them off |

## Finding the compiler

The check on save runs the first of:

1. `compilerPath`
2. `$SULTANC`
3. `build/sultanc` next to the standard library the server uses (a checkout)
4. `~/.supax/bin/sultanc` (installed by Supax's `tools/install.sh`)
5. `sultanc` on `PATH`

## Environment variables

| Variable | Meaning |
|---|---|
| `SULTANC` | The compiler for the check on save (see above) |
| `SUPAX` | The Supax executable for `supax metadata`; otherwise `supax` on `PATH`, then `~/.supax/bin/supax` |
| `SULTANC_ANALYZER_LOG=1` | Log each request's duration, analysis decisions and incremental session activity to standard error |
| `SULTANC_ANALYZER_MAX_PROJECT_FILES=N` | Cap the number of files in project-wide analyses (no cap by default) |

## Projects

- **Supax package** — a workspace folder that holds `Supax.toml`, or lies inside a folder that does. The package graph comes from `supax metadata`, run where `Supax.toml` is. Each file is analysed with that graph, rooted at the package whose `source_root` holds it. The graph is read again at start, when folders change, and when `Supax.toml` or `Supax.lock` changes. When Supax is missing or fails, a warning names the problem.
- **Folder** — any other folder: a standalone compilation of its `.sn` files.

Files are listed under each root, except the standard library directory, hidden folders, `build`, `node_modules` and symbolic links.
