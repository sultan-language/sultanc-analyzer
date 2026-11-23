# Configuration

## Starting the server

Editors start `sultanc-analyzer` with no arguments; it speaks LSP over stdin and stdout. Standard output carries only LSP frames; logs go to standard error.

⚠️ **The working directory must be the directory that holds `library/`** — a SultanC checkout, or an unpacked release bundle. The compiler resolves the standard library (`library/core`, `library/alloc`, `library/std`) relative to the working directory. Documents and workspace folders arrive as absolute URIs, so projects can be anywhere.

```sh
cd /path/to/sultanc && build/sultanc-analyzer                       # a checkout
cd sultanc-analyzer-0.21.0-arm64-darwin && build/sultanc-analyzer        # a release bundle
```

`tools/sultanc-analyzer-editor.sh` does this for editors that cannot set a working directory (`SULTANC_HOME`, optional `SULTANC_ANALYZER`). The VS Code extension does it automatically.

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
3. `build/sultanc` next to the standard library the server uses (a checkout, or a bundle that includes the compiler)
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
