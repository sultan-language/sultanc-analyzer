# Testing

## Running

```sh
tools/build.sh && tests/run.sh                      # the compiler's main branch
tools/build.sh /path/to/sultanc
tests/run.sh /path/to/sultanc                       # the server in /path/to/sultanc/build
tests/run.sh /path/to/sultanc /path/to/sultanc-analyzer  # another server build
SUPAX=/path/to/supax tests/run.sh                   # with the Supax package tests
```

Requirements: Python 3.8 or newer, and a SultanC compiler, found as `tools/build.sh` finds it (`<checkout>/build/sultanc`, `$SULTANC`, `~/.supax/bin/sultanc`, `PATH`); some checks compare against `sultanc fmt` and `sultanc test`.

The suite prints one line per check and a total:

```
ok   hover: signature, doc comment, English types, link
...
40/40 passed
```

It exits with a non-zero status when a check fails, so it can run in CI.

## What it covers

`tests/integration/lsp_integration.py` starts the server as an editor does (working directory: the SultanC checkout), sends JSON-RPC over stdio, and asserts the exact replies: ranges, titles, edits and messages, in English and Arabic. Fixtures in `tests/integration/fixtures/` are copied to a temporary folder first; checks that need their own project write it to a temporary folder.

The checks cover every method in [FEATURES.md](FEATURES.md), plus:

- cancellation and stale requests (`-32800`, `-32801`, `-32802`);
- a project of more than 300 files, closed-file references;
- Supax packages (with `SUPAX`);
- the check on save, including Arabic reports, open/close and settings.

## Writing a check

```python
def my_feature():
    reply = c.request('textDocument/hover', P(EN, en_text, 'area(Shape'))
    assert reply['contents']['value'] == '…', reply
check('hover: what it shows', my_feature)
```

- Assert on the full expected value, not on "not empty".
- Compute positions with `at(text, needle, offset)`, which counts UTF-16 code units as LSP does.
- A feature in both languages gets an English and an Arabic case.
- A check that changes a document restores it, or uses its own client and folder.

## Editor tests

The VS Code extension has its own unit, end-to-end and RTL editor tests in [sultanc-language-support](https://github.com/sultan-language/sultanc-language-support) (`editors/vscode`). Its end-to-end suite runs against a server build (`SULTANC_ANALYZER`, `SULTANC_HOME`) or a release bundle (`SULTANC_BUNDLE`).
