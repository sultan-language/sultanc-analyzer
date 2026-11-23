# sultanc-analyzer

The language server for [SultanC](https://github.com/sultan-language), the Arabic-first systems programming language.

`sultanc-analyzer` speaks the Language Server Protocol 3.17 over stdio. It is written in SultanC and links the compiler's own frontend, so every diagnostic, type, name and quick fix it reports is the compiler's. The server does not parse or resolve SultanC on its own: a feature the compiler cannot answer is not offered.

Arabic and English source files are equally supported. Messages, hover labels and CodeLens titles follow each document's language.

## Contents

- [Features](#features)
- [Install](#install)
- [Build from source](#build-from-source)
- [Configuration](#configuration)
- [Repository layout](#repository-layout)
- [Testing](#testing)
- [Documentation](#documentation)
- [License](#license)

## Features

| Area | What the server provides |
|---|---|
| Diagnostics | Live compiler diagnostics for open files (pull and push), check on save for unopened files, errors in imported modules surfaced at the import |
| Navigation | Hover, go to definition, declaration, type definition and implementation, references, document highlights, call and type hierarchy, document and workspace symbols, import links |
| Editing | Completion (scopes, fields, constructors, Type positions, record fields, match arms, call arguments ranked by expected Type, std auto-import), signature help, inlay hints, closing brace hints, semantic tokens |
| Refactoring | Rename (project-wide, with conflict checks), import updates when a file is renamed, compiler quick fixes, organize imports, extract function, extract variable, inline variable |
| Formatting | Document, range and on-type formatting through the compiler's formatter (`sultanc fmt`) |
| Tests and running | Run and Debug CodeLens above the program entry and each `@@test`, test discovery for test explorers |
| Projects | Supax packages through `supax metadata`, standalone folders otherwise; incremental analysis and request cancellation |

The full list of methods, with what each one returns, is in [docs/FEATURES.md](docs/FEATURES.md).

## Install

### VS Code

Install the **SultanC** extension. It is published as platform-specific packages that bundle this server and the standard library it was built with:

| Platform | Package |
|---|---|
| Linux x64, Linux arm64 | `linux-x64`, `linux-arm64` |
| macOS Intel, macOS Apple silicon | `darwin-x64`, `darwin-arm64` |
| Windows x64, Windows arm64 | `win32-x64`, `win32-arm64` |

VS Code picks the package for your platform. To use another server build, set `sultanc.server.path`.

### Other editors

Download the bundle for your platform from the [releases](https://github.com/sultan-language/sultanc-analyzer/releases) and unpack it:

```
sultanc-analyzer-<version>-<target>/
  build/sultanc-analyzer        the server (sultanc-analyzer.exe on Windows)
  library/                 the standard library it was built against
```

Start `build/sultanc-analyzer` with the bundle directory as its working directory. Neovim, Helix, Emacs, Sublime Text and Zed setups are in [docs/EDITORS.md](docs/EDITORS.md).

Running and checking programs needs the SultanC compiler. The server finds it in this order: the `compilerPath` option, `$SULTANC`, `build/sultanc` next to the standard library, `~/.supax/bin/sultanc` (the Supax installer), then `sultanc` on `PATH`.

## Build from source

The server links the compiler's frontend, so it is built against the [SultanC compiler](https://github.com/sultan-language/sultanc) sources. `Supax.toml` names them:

```toml
[dependencies]
compiler = { git = "https://github.com/sultan-language/sultanc", branch = "main" }
```

Requirements: `git`, and a SultanC compiler (`sultanc`) that can compile those sources: `$SULTANC`, `~/.supax/bin/sultanc` (Supax's installer), or `sultanc` on `PATH`.

```sh
tools/build.sh
```

This fetches the head of `main` into `build/deps/sultanc` (again only when `main` moved) and writes `build/deps/sultanc/build/sultanc-analyzer`. The server runs with `build/deps/sultanc` as its working directory, where the standard library it was built against is.

To build against a local compiler checkout instead (when working on the compiler and the server together):

```sh
tools/build.sh /path/to/sultanc       # writes /path/to/sultanc/build/sultanc-analyzer
```

`supax build` will build the same package once Supax resolves a package in a subdirectory of a git dependency (the compiler is `compiler/Supax.toml` in its repository; see [docs/COMPILER_REQUESTS.md](docs/COMPILER_REQUESTS.md), S1).

Release bundles for every supported platform are built with `tools/dist.sh`; the compiler cross-compiles and links each target itself. See [docs/RELEASING.md](docs/RELEASING.md).

## Configuration

Clients pass settings as `initializationOptions`:

| Option | Default | Meaning |
|---|---|---|
| `language` | `auto` | Language of messages and labels: `auto` (each document's), `ar`, `en` |
| `checkOnSave` | `true` | Run the compiler's check after each save and report unopened files |
| `checkEntries` | `[]` | Entry files for the check; empty means `src/main.sn` or `main.sn` |
| `compilerPath` | | The compiler for the check on save |
| `lensRun` | `true` | Run and Debug CodeLens above the entry and tests |
| `lensReferences` | `false` | Reference counts above declarations |
| `bidiIsolates` | `false` | Arabic hover lines read right to left (for clients that render Markdown as HTML) |
| `closingBraceHintsMinLines` | `25` | Closing brace hints after declarations this long; `0` turns them off |

Environment variables, the working directory and logging are described in [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Repository layout

```
Supax.toml               package manifest
src/
  main.sn                entry point
  server/                JSON-RPC loop, dispatch, lifecycle
  protocol/              LSP wire types, one file per feature family
  analysis/              bridge to the compiler frontend, caches, queries, refactorings
  workspace/             open documents, positions, folders, package graph, check on save
  transport/             stdio framing, reader thread, scheduling
tests/
  integration/           JSON-RPC end-to-end tests and their fixtures
tools/
  build.sh               build against the compiler's main branch or a local checkout
  dist.sh                release bundles for every platform
  compiler-source.sh     where the compiler checkout and executable come from
  sultanc-analyzer-editor.sh  launcher for editors other than VS Code
  generate_keywords.py   regenerate src/analysis/keywords.sn
docs/                    reference documentation
```

The design is described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Testing

```sh
tests/run.sh                          # the server tools/build.sh built
tests/run.sh /path/to/sultanc         # the server built against a local checkout
```

The suite starts the server, drives every feature over JSON-RPC on the fixtures in `tests/integration/fixtures/`, and asserts exact replies in English and Arabic. Set `SUPAX` to a Supax executable to include the package tests. Details: [docs/TESTING.md](docs/TESTING.md).

## Documentation

| Document | Contents |
|---|---|
| [FEATURES.md](docs/FEATURES.md) | Every LSP method and extension request, and what it returns |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Options, environment variables, working directory, logging |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Modules, analysis sessions, caching, scheduling and cancellation |
| [EDITORS.md](docs/EDITORS.md) | Setup for Neovim, Helix, Emacs, Sublime Text and Zed |
| [TESTING.md](docs/TESTING.md) | Running and writing tests |
| [RELEASING.md](docs/RELEASING.md) | Building bundles and platform packages, publishing a release |
| [COMPILER_REQUESTS.md](docs/COMPILER_REQUESTS.md) | What the server needs from the compiler |
| [CHANGELOG.md](CHANGELOG.md) | Changes by version |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |

## License

[MIT](LICENSE)
