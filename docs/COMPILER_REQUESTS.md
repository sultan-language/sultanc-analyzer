# Compiler requests

Checkpoint: **SultanC_20261125_b28b8a6_incremental-cutoff** (2026-11-25). sultanc-analyzer 0.1.2, VS Code extension 0.15.0.

Everything the editor tooling still needs from the compiler. Each item names
the exact query or data, the reproduction, and the expected result. The LSP
does not copy symbol tables, types, diagnostics or semantics: a feature whose
answer the compiler cannot give is not offered.

## Open

### C10 — Completion after `.` is empty when `;` or `)` follows on the line

`رقع_مصدر_للإكمال` / `إكمال_عند_رقعة_واجهة` (final6, still on b28b8a6) give the record's fields after `name.` only when nothing but `with` or the end of the line follows. With `;` or `)` after the cursor, the list is empty: editing a field in an existing statement offers nothing.

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

### P2 — Early cutoff never applies to the module being edited (it is the analysis root)

b28b8a6 adds early cutoff (`حلل_أجساما_في_جلسة`), and its test passes: there the edited module, `lib.sn`, is imported by the root `root.sn`. In an editor the edited document is the root of every analysis the server makes (it is declared open and analysed as the root, as the session was designed for), and `وحدة_تقبل_فحص_الأجسام` (semantic_pipeline.sn:5441–5444) refuses the root:

```
طابق (*الحالة).شجرة_الجذر مع
| اختياري.موجود(الشجرة) -> { إذا (الشجرة == الموضع) { أرجع خطأ; }; }
...
إذا (وحدة_هي_الجذر(&(*الحالة).الجذر, (*الحالة).الوحدات[الموضع].الوحدة)) { أرجع خطأ; };
```

So every body edit in the editor still re-analyses the edited module and all its importers.

Reproduction (the server built against b28b8a6, `SULTANC_ANALYZER_LOG=1`): `lib.sn` = `public def helper(x: int): int { return x + 1; }`, imported by `main.sn` and `other.sn`. Open `lib.sn`; references on `helper`; then change `x + 1` to `x + 2` (`didChange`), wait 1.5 s, references again; repeat.

```
sultanc-analyzer: session 1: 76 ms, state 1, analysed 3, reused 57, changed 1, prepared no, full no
```

With a print at each refusal in a scratch copy of the compiler, every request after an edit stops at `حلل_أجساما_من_نهائية` → `وحدة_تقبل_فحص_الأجسام` → line 5442 (`الشجرة == الموضع`). Same on `compiler/` as the workspace, editing `precedence.sn`: `analysed 61, reused 594`, references 6.3 s after each edit (5.7 s of it the session).

Request: allow the early cutoff when the changed module is the root. Expected for a body-only or comment-only edit of the open document: `state 3`, `analysed 1` (the root has no importer in its own analysis; the importers that the project session adds as extra keys keep their facts, as for a non-root module), and the references request well under 1 s on `compiler/`. If something specific to the root forbids it (the entry point, its unused imports), the same check for that part only.

---

## Already delivered by the compiler and wired in the LSP

- b28b8a6 incremental-cutoff (2026-11-25): builds clean; 42/42 integration
  tests. The early cutoff itself works in the compiler's test, but not yet
  for the edited document (P2).

- 13bcb36 text-slices-views (2026-11-25): B2 fixed, a clean checkout builds
  (`./build.sh`, 5 min). Text-slice borrow errors reach the editor at the
  compiler's positions (`SULTANC-BORROW-REFERENCE-ESCAPE` at 9:5,
  `SULTANC-BORROW-CONFLICT` at 16:5 in the e2e tests). 42/42 integration
  tests, VS Code end-to-end 27/27, RTL editor 23/23.

- patterns (2026-11-25): the Arabic comma `،` (COMMA_OPERATOR) and the bare
  prelude constructors in completion (`some(`, `none()`; `موجود(`,
  `لا_شيء()`). Wired: parameter-name hints split arguments at `،` (and skip
  `«…»`), signature help is triggered by `،`, the tree-sitter grammar and
  highlight queries accept it. 42/42 integration tests.

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
