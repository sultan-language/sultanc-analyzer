# Compiler requests

Checkpoint: **SultanC_main_20261123_final8** (2026-11-23). sultanc-analyzer 0.21.0, VS Code extension 0.15.0.

Everything the editor tooling still needs from the compiler. Each item names
the exact query or data, the reproduction, and the expected result. The LSP
does not copy symbol tables, types, diagnostics or semantics: a feature whose
answer the compiler cannot give is not offered.

## Open

### S1 (Supax) — a git dependency on a package in a subdirectory of its repository

The server depends on the compiler's frontend, the package `compiler` declared in `compiler/Supax.toml` of https://github.com/sultan-language/sultanc. Its `Supax.toml` names it as a git dependency, so every user builds against the same sources wherever their own checkout is:

```toml
[dependencies]
compiler = { git = "https://github.com/sultan-language/sultanc", branch = "main" }
```

`supax build` (Supax at the `supax7` checkout, compiler final6) stops, because Supax reads only the repository's root manifest (package `sultanc`, no `[lib]`):

```
error: Supax.toml:17: dependency "compiler" is not a library: its manifest /root/.supax/git/checkouts/dab128c2b4e9c150/7c6c6ea0c7dad422a43913ebdbd5011354fa4187/Supax.toml does not declare [lib]
```

Request, either of:

- **As Cargo does:** when the root manifest of a git dependency is not the package named by the dependency key, find the package of that name in the repository (`compiler/Supax.toml`, `name = "compiler"`), and give its directory as the dependency's `source_root`.
- **Explicit:** accept `path` together with `git` as the package's directory inside the checkout: `compiler = { git = "…", branch = "main", path = "compiler" }`. The rule "a path dependency inside a git package cannot leave its repository" applies to it.

Expected: the package graph has `compiler` with `source_root = ~/.supax/git/checkouts/<repo>/<rev>/compiler`; `supax build` writes `build/sultanc_analyzer`; `Supax.lock` records the repository and revision, with no local path.

Until then, `tools/build.sh` and `tools/dist.sh` read the same `git` and `branch` from `Supax.toml` and fetch its head into `build/deps/sultanc`. With final6's compiler, the server built that way passes all 40 integration tests.

### C10 — Completion after `.` is empty when `;` or `)` follows on the line

`رقع_مصدر_للإكمال` / `إكمال_عند_رقعة_واجهة` (final6, still on final8) give the record's fields after `name.` only when nothing but `with` or the end of the line follows. With `;` or `)` after the cursor, the list is empty: editing a field in an existing statement offers nothing.

```
type Name = { ahmad: string, Ali: string };
def get_name(name: Name): int {
    <LINE>
}
```

| `<LINE>` (cursor at `|`) | Fields offered |
|---|---|
| `match name.\| with` | `ahmad`, `Ali` ✓ |
| `match name.ahma\| with` | `ahmad`, `Ali` ✓ |
| `return name.ahmad\|` | `ahmad`, `Ali` ✓ |
| `return name.\|;` | none ✗ |
| `return name.ah\|;` | none ✗ |
| `return name.ahmad\| ;` | none ✗ |
| `let q: string = name.\|;` | none ✗ |
| `foo(name.\|);` | none ✗ |

Same with `int` fields and with a function that returns `string`, so it is not the expected Type. Expected: the fields in every row, ranked by the expected Type as C9; the text after the cursor (`;`, `)`, the rest of the line) does not change the context.

### P2 — Incremental analysis: keep importers when a module's interface did not change

Measured with `compiler/` as the workspace (about 640 modules with the layered std), the package graph from `supax metadata`. Append a comment line to `compiler/frontend/parser/precedence.sn` (`didChange`), wait 1.5 s, then `textDocument/references` on `معلومة_العامل`.

final5 (ownership analysis kept per state) made each edit faster, but the importers are still re-analysed:

```
final3: sultanc-analyzer: session 1: 6616 ms, state 2, analysed 57, reused 586, changed 1, prepared yes, full no
final5: sultanc-analyzer: session 1: 2675 ms, state 2, analysed 57, reused 585, changed 1, prepared yes, full no
```

| | final3 | final5 | final6 |
|---|---|---|---|
| References after the edit (median of 4) | 7.2 s | 3.0 s | 2.6 s |
| References, cold | 10.6 s | 9.6 s | 9.5 s |
| Peak memory | 1.46 GB | 1.30 GB | 1.30 GB |

The edit changes no declaration, so no importer's result can change.

Request: in the incremental session, when a changed module's exported interface (its public declarations and their Types) is identical to the kept state's, reuse its importers' states (early cutoff, as rust-analyzer's salsa does). Expected for a comment-only or body-only edit: `analysed 1` (the document session already shows `analysed 1, reused 57, 14 ms`), and the request well under 1 s. An edit that changes a signature still re-analyses the importers.

---

## Already delivered by the compiler and wired in the LSP

- final8 (2026-11-23): the Arabic `let` is `ليكن`. The analyzer's sources,
  keyword table (regenerated from the registry), refactorings and tests use
  it; 41/41 integration tests, VS Code end-to-end 27/27 (28/28 bundled),
  RTL editor 23/23.

- final6 (2026-11-23): B1 fixed, `./build.sh` builds `build/sultanc`.
  `tools/build.sh` builds the server; 40/40 integration
  tests, VS Code end-to-end 27/27 (28/28 with the bundled server), RTL
  editor 19/19. Release bundles rebuilt on final6.

- final5 (2026-11-23): the ownership analysis of a kept state is made once
  per state (`ملكية_مخبأة_واجهة`): references after an edit of
  `precedence.sn` 7.2 s → 3.0 s, peak memory 1.46 → 1.30 GB. All 40
  integration tests pass.

- final3 (2026-11-22):
  - P1: `compiler/Supax.toml` declares the library package `compiler`.
    A path dependency on it builds with `supax build` (25 s, 40/40 tests);
    the server now pins it by git revision instead (S1).
  - `compiler/debuginfo/type_cache.sn` (two `SULTANC-TYPE-MISMATCH` in an
    unimported file) is removed.

- final (2026-11-22), all wired with exact tests:
  - E1: `Color.Red` is `SULTANC-NAME-CONSTRUCTOR-NOT-CALLED` at
    `Color.Red`; its quick fix inserts `()`.
  - E2: a top-level `let c: Color = Color.Red();` no longer ends in an ICE.
  - E3: `نص_الإدراج`: `Color.` inserts `Red()`, `Shape.` `Circle(` /
    `Dot()`, `option.` `none()` / `some(`; a match arm keeps `Color.Red`.
  - Debug one test: `sultanc test --test=NAME -O0 -o PATH --no-run` prints
    `INDEX NAME`; the "Debug" lens and the Test Explorer's Debug profile
    build it and start gdb/lldb on `PATH INDEX`. The e2e test stops inside
    the test at its line with `n = 4`, then the test passes.

- Completion contexts (ssf, `tooling_completion.sn`), wired in 0.19.0 with
  exact tests:
  - C1–C4: `make().`, `make().inner.`, `(*r).`, `arr[0].` → the fields;
  - C5: `option.` → `none`, `some` (`منشئ_مدمج`);
  - C6: `let x: ` → Types only (`Color`, `Inner`, `Outer`, builtins), no values;
  - C7: `let o: Inner = { ` → `depth`, `label`, inserting `depth: `; after
    `depth: 1, ` only `label`;
  - C8: `match c with | ` → `Color.Green`, `Color.Red`; `Shape.Circle(_)`,
    `Shape.Dot` (`نمط_حالة`);
  - C9: `area(` → `top` (an `int`) first (`يلائم_المتوقع`), the others after.

- Check on save (no compiler change): `sultanc check --diagnostic-format=json`
  (with `--package-graph=-` in a Supax package) gives every diagnostic with
  `column_utf16`; the LSP publishes them for unopened files.

- interp1_ci (layered std):
  - `الجذور_القياسية` / `الطبقات_السفلى` are copied with the environment.
    Auto-import indexes `library/core`, `library/alloc` and `library/std`
    (all imported as `std.…`).
  - The new `مصرح_هنا` role is sent as `declared-here`.
  - The `add-missing-arms` fix replaces the LSP's text-based "Add missing
    match arms", and the `import-module` fix is the add-import quick fix.

- Per-edit overhead (000493c):
  - Texts are re-read only when a file's size or modification time changed.
  - `جهز_جلسة_تحليل` is called when nothing is queued after a reply. The log
    shows every later request starting from the prepared copy.
  - The LSP also stopped deep-copying the analysed interface between its cache
    and requests (it is now shared through `مشترك<…>`).
  - `compiler/`, edit of `main.sn`: session 0.27 s; references 0.45 s (was
    1.75 s); diagnostics after `didChange` 0.38 s (was 1.2 s).
  - Edit of `precedence.sn`: references 1.35 s (was 2.5 s).

- test-mode-2 (35b9d86):
  - `--test=<name>`: the Test Explorer runs exactly one test; the e2e test
    checks that running `doubles` gives only `doubles`.
  - `SULTANC-TEST-*` in tooling analysis: `@@test def takes(x: int)` gets
    `SULTANC-TEST-PARAMETERS` at its name while editing (test).
  - `--package-graph=-`: `sultanc/packageGraph` gives the graph rooted at the
    file's package. The Test Explorer pipes it in, and the Supax test runs
    `checks_util` through it.
- 0eaea16: clean source names (the LSP's `..` resolution is removed) and
  `العبارة_غير_مستخدمة`.
- 94bba04: debug builds are `-O0`. The e2e test checks a breakpoint in the
  callee and the locals, under gdb and lldb.
- f411e56: fmt after `@@` (the formatting test now has an annotated file).

- Incremental analysis (3b441bc): every analysis goes through
  `ابن_واجهة_في_جلسة`, with a project session and a document session. The
  analysed root is declared open. Measured with `compiler/` as the workspace,
  references from `precedence.sn`: 7.6 s cold, 8.2 s for the first edit (the
  session builds its kept states), then 2.4 s per edit.
- Test discovery (3b441bc): `sultanc/tests` uses `اكتشف_اختبارات`. The VS Code
  Test Explorer runs `sultanc test` and reads its report. The e2e test checks
  one passing and one failing test, with the error text and location.
- Module spellings (3b441bc, `اللغة` / `الأصلي`): an English file gets
  canonical names only; an Arabic file gets its spellings first (`أخطاء` →
  `error`).

- Completion (0e3479d, `tooling_completion.sn`), wired with tests T1–T7, all
  exact:
  - `return p.` → `x: int`, `y: int`;
  - `أرجع ن.` → `س: عدد`, `ص: عدد`;
  - `استورد المكتبة.دخ.` and `std.io.` → the 7 io modules;
  - `return he` → `total`, then `helper`, `main` (not `a`), then keywords;
  - `Color.` → `Green`, `Red`;
  - inside a string → nothing.
  Items replace the typed word (`textEdit`) and are ranked by `البعد`.
- Whole-checkout analysis (0e3479d): references of `معلومة_العامل` →
  `precedence.sn`, `expressions.sn`.
- Lexer spans cover whole characters (0e3479d).

- Tooling API: references with roles, rename conflicts, top-level symbols with
  containers, UTF-16 ranges, other-target declarations, import links, unused
  imports, per-source completeness.
- Atomic cancellation token, through a reader thread.
- Extract Function, extract variable, inline variable.
- Structured suggestions as quick fixes (`declare-mutable`, `dereference`,
  `similar-name`, `import-module`, keyword and semicolon fixes).
- Formatter: `textDocument/formatting` and `rangeFormatting` give exactly what
  `sultanc fmt` writes.
- Package graph from `supax metadata`, with `root` set to the package that owns
  the file.
- Per-source failures: a partly bound file contributes its references.
- Opaque types (`معتم`).
- DWARF names, arguments, backtrace.
