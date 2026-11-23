# Features

Every method `sultanc-analyzer` answers, and where its answer comes from. Compiler functions are named as they appear in the compiler sources (`compiler/frontend/tooling_queries.sn`, `tooling_facts.sn`, `tooling_completion.sn`).

## Lifecycle and documents

| Method | Notes |
|---|---|
| `initialize`, `initialized`, `shutdown`, `exit` | Options in [CONFIGURATION.md](CONFIGURATION.md). `serverInfo` carries the version |
| `textDocument/didOpen`, `didChange` (incremental), `didSave`, `didClose` | UTF-16 positions, as LSP requires |
| `workspace/didChangeWorkspaceFolders`, `workspace/didChangeWatchedFiles` | Folders and `Supax.toml` / `Supax.lock` changes re-read the project |
| `$/cancelRequest` | Stops the running analysis (see [ARCHITECTURE.md](ARCHITECTURE.md#scheduling-and-cancellation)) |

## Diagnostics

| Method | Notes |
|---|---|
| `textDocument/diagnostic` (pull) | Live diagnostics for open documents. `textDocument/publishDiagnostics` is used instead for clients without pull support |
| `workspace/diagnostic` | Open documents, bounded |
| `textDocument/publishDiagnostics` (check on save) | Diagnostics of files that are not open, from the compiler's check (below) |

Diagnostics carry the compiler's code (`SULTANC-…`), its full message in the document's language, related locations, and structured `data` with the compiler's fixes. An error located in another module (std or a dependency) is shown at the top of the importing document as information, with `path:line:column`.

### Check on save

As rust-analyzer runs `cargo check`, the server runs the compiler's check after each save of a `.sn` file and once at start, and publishes the diagnostics of every file that is not open. An open file keeps its live diagnostics; opening a file drops its check diagnostics and closing it brings them back.

- Command: `sultanc --lang=<ar|en> check --diagnostic-format=json <entry>`, with `--package-graph=-` and the graph on standard input in a Supax package.
- Entry: `src/main.sn` or `main.sn` of each workspace folder, or of the folder of its `Supax.toml`, or the files in `checkEntries`.
- Language: each file's (the report runs in English, and again in Arabic when a reported file is Arabic), or `language` when set.
- It runs on its own thread; a save during a check queues one more. Progress lines go to `window/logMessage`.

## Understanding code

| Method | Notes |
|---|---|
| `textDocument/hover` | Declaration as written, its doc comment (the `//` block directly above), full record and enum bodies, types in the document's language, visibility, owner, link to the definition. Keywords show both spellings. With `bidiIsolates`, lines that start in Arabic are isolated right to left |
| `textDocument/definition`, `declaration` | From the compiler's occurrences. On an import, the imported module's file (layered std included: `std.text.number` opens `library/alloc/text/number.sn`) |
| `textDocument/typeDefinition` | The declaration of the value's Type |
| `textDocument/implementation` | A declaration written once per target (`if (target.platform == …)` at module level): the other targets' declarations (`تصريحات_لأهداف_أخرى_واجهة`) |
| `textDocument/references` | The whole project, from `مراجع_رمز_واجهة`. When an importer's names could not be bound (`اكتمال_مصدر_واجهة`), the reply comes with a warning naming those files |
| `textDocument/documentHighlight` | Write for declarations, assignments and `&متغير` borrows; Read otherwise |
| `callHierarchy/*`, `typeHierarchy/*` | Incoming and outgoing calls of a function; supertypes and subtypes of a Type, from the compiler |
| `textDocument/documentSymbol` | Declarations and their locals |
| `workspace/symbol` | The compiler's top-level symbols with containers (`رموز_عليا_واجهة`), matched by identifier identity (Alef forms and Kashida folded), ASCII case-folded, as an in-order subsequence |
| `textDocument/documentLink` | Each import statement, linked to the module file the compiler loaded (`علاقات_استيراد_واجهة`) |
| `textDocument/semanticTokens/full`, `full/delta`, `range` | function, type, struct, enum, enumMember, parameter, variable, with `declaration`. The last clean colouring is kept while the text does not analyse |
| `textDocument/inlayHint` | Parameter names at call sites; Types of bindings that have none written (match patterns, loop variables); closing brace hints (`} // def main`, `} // عرف الرئيسية`) after declarations of at least `closingBraceHintsMinLines` lines |
| `textDocument/foldingRange`, `selectionRange` | From the text structure, so they work on files that do not parse |

## Writing code

| Method | Notes |
|---|---|
| `textDocument/completion` (trigger `.`) | The compiler's completion on the unfinished line (`tooling_completion.sn`): names visible at the cursor (locals first, then parameters, the module, imports, std), `value.` fields through references, calls and indexing, `Type.` constructors (inserted as calls: `Red()`, `Circle(`), Types only in Type positions, the remaining fields in a record literal (`name: `), patterns after `\|` in a match, arguments of the expected Type first, child modules after `import a.` / `استورد أ.`. Nothing inside strings and comments. Keywords in the document's language follow the names; std names that need an import come last and add it. The list is `isIncomplete` while it depends on more letters |
| `textDocument/signatureHelp` (`(`, `,`) | The declaration as written, named parameters, the active parameter, docs |
| `textDocument/formatting`, `rangeFormatting` | The compiler's formatter (`compiler/format`, the one `sultanc fmt` runs) on the unsaved text. A file that does not parse is not formatted (null). A range gets the edits of the whole-file format that touch it |
| `textDocument/onTypeFormatting` (`}`, `;`) | After `;` its line, after `}` the block it closes: the same edits `rangeFormatting` gives |

## Refactoring

| Method | Notes |
|---|---|
| `textDocument/rename`, `prepareRename` | Project-wide. Refused with the compiler's first conflict as the message (`تعارضات_إعادة_تسمية_واجهة`), or when an importer is incomplete |
| `workspace/willRenameFiles` | Renaming or moving a `.sn` file rewrites the import statements that name it, at the ranges of the compiler's import edges: a quoted path becomes the new relative path; a dotted import of a file renamed in its folder gets the new last segment. A dotted import of a file moved to another folder names a different module, so it is left as is |
| `textDocument/codeAction` | Compiler quick fixes (`اقتراح_من_إصلاح`) with their edits, preferred when `machine-applicable`; add import (`import-module`); add missing match arms (`add-missing-arms`); `source.organizeImports` (unused imports from `استيرادات_غير_مستخدمة_واجهة`, sorted and deduplicated); `refactor.extract.function` (`حلل_استخراج_دالة_واجهة`); `refactor.extract.variable` (Type from `نوع_تعبير_بمدى_واجهة`); `refactor.inline` (`معلومات_تضمين_محلي_واجهة`); invert `if`, add `else`. Edits that can change meaning are checked by the compiler on a copy of the document and offered only when they add no error |

## Running and tests

| Method | Notes |
|---|---|
| `textDocument/codeLens`, `codeLens/resolve` | "▶︎ Run" and "Debug" above the program entry (the compiler's `رمز_بدء_البرنامج`), commands `sultanc.runFile` / `sultanc.debugFile` (uri). "▶︎ Run Test" and "Debug" above each runnable test, commands `sultanc.runTest` / `sultanc.debugTest` (uri, name). With `lensReferences`, "N references" above functions, Types and top-level values, counted in resolve (the declaration excluded), command `sultanc.showReferences` (uri, position, locations). Titles in the document's language, with Arabic number agreement |
| `sultanc/tests` | The document's `@@test` / `@@اختبار` functions from the compiler's discovery (`compiler/test_mode/discovery.sn`): `[{ name, range, runnable }]`. Invalid tests are compiler diagnostics while editing (`SULTANC-TEST-*`) |
| `sultanc/packageGraph` | `{ graph }` for a file in a Supax package (the `supax metadata` graph with that file's package as `root`), for `sultanc test --package-graph=-`; null elsewhere |

The commands named by CodeLens are the client's, as with rust-analyzer. The VS Code extension implements them; other clients can map them to their own run and debug actions.

## While typing

Completion answers on the current text. Hover and signature help answer from the last analysis without errors when the current text does not analyse; lines are mapped across the edit by their common prefix and suffix.
