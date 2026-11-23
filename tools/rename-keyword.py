#!/usr/bin/env python3
"""Rename a statement keyword spelling across the repository (دع -> ليكن).

    tools/rename-keyword.py OLD NEW [--check] [PATH...]

Run it when the compiler accepts the new spelling, then rebuild and test
(tools/build.sh && tests/run.sh). Without PATHs it renames this repository's
src/ tests/ docs/ and top-level Markdown files; with PATHs, those (relative
to the current directory), e.g. the VS Code extension's hand-written files:

    cd sultanc-language-support
    ../sultanc-analyzer/tools/rename-keyword.py دع ليكن editors/vscode/snippets \
        editors/vscode/test linguist/samples tree-sitter-sultanc/test

Files generated from the compiler's token registry are regenerated instead:
src/analysis/keywords.sn (tools/generate_keywords.py) here, and the syntax
surface, grammars and highlight queries of the extension
(tools/sync-from-compiler.sh).

- .sn files: only the keyword is renamed, where a statement starts (at the
  start of a line, or after `{`, `}` or `;`) and followed by a space; strings
  («…», "…") and comments are left as written, and so is a name such as
  `رمز.دع` after a `.`.
- Other text files (tests, docs): the word is renamed where it stands alone
  in Arabic text (not inside a longer word).
- src/analysis/keywords.sn is generated from the compiler's token registry:
  regenerate it with tools/generate_keywords.py instead.

--check lists what would change and exits 1 if anything would.
"""
import os
import re
import sys

ARABIC_LETTER = re.compile(r'[ء-ي٠-٩ٮ-ۓۺ-ۼـA-Za-z0-9_]')
GENERATED = {os.path.join('src', 'analysis', 'keywords.sn')}
TEXT_SUFFIXES = {'.py', '.js', '.json', '.md', '.txt', '.toml', '.scm'}


def is_word_char(ch):
    return bool(ch) and bool(ARABIC_LETTER.match(ch))


def rename_in_source(text, old, new):
    """Renames the keyword `old` in SultanC source, outside strings and comments."""
    out = []
    i = 0
    n = len(text)
    count = 0
    last_code = '\n'  # the last non-space code character, for "a statement starts here"
    while i < n:
        ch = text[i]
        if text.startswith('//', i):
            j = text.find('\n', i)
            j = n if j == -1 else j
            out.append(text[i:j])
            i = j
            continue
        if text.startswith('/*', i):
            j = text.find('*/', i + 2)
            j = n if j == -1 else j + 2
            out.append(text[i:j])
            i = j
            continue
        if ch in '«"':
            close = '»' if ch == '«' else '"'
            j = i + 1
            while j < n and text[j] != close:
                j += 2 if text[j] == '\\' else 1
            j = min(n, j + 1)
            out.append(text[i:j])
            last_code = close
            i = j
            continue
        if (text.startswith(old, i)
                and not is_word_char(text[i - 1] if i > 0 else '')
                and i + len(old) < n and text[i + len(old)] in ' \t'
                and last_code in '\n{};'):
            out.append(new)
            count += 1
            last_code = new[-1]
            i += len(old)
            continue
        out.append(ch)
        if ch == '\n':
            last_code = '\n'
        elif not ch.isspace():
            last_code = ch
        i += 1
    return ''.join(out), count


def rename_in_text(text, old, new):
    pattern = re.compile(r'(?<![ء-يـ_])' + re.escape(old) + r'(?![ء-يـ_])')
    return pattern.subn(new, text)


def files_under(paths):
    for path in paths:
        if os.path.isfile(path):
            yield path
            continue
        for root, dirs, names in os.walk(path):
            dirs[:] = [d for d in dirs if d not in {'.git', 'build', 'dist', 'node_modules', '__pycache__'}]
            for name in sorted(names):
                yield os.path.join(root, name)


def main():
    args = [a for a in sys.argv[1:] if a != '--check']
    check = '--check' in sys.argv[1:]
    if len(args) < 2:
        sys.exit(__doc__)
    old, new = args[0], args[1]
    if args[2:]:
        here = os.getcwd()
        paths = args[2:]
    else:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.chdir(here)
        paths = ['src', 'tests', 'docs', 'README.md', 'CONTRIBUTING.md']
    total = 0
    changed = []
    for path in files_under(paths):
        rel = os.path.relpath(path, here)
        if rel in GENERATED:
            continue
        suffix = os.path.splitext(path)[1]
        if suffix != '.sn' and suffix not in TEXT_SUFFIXES:
            continue
        with open(path, encoding='utf-8') as f:
            text = f.read()
        updated, count = (rename_in_source if suffix == '.sn' else rename_in_text)(text, old, new)
        if count:
            total += count
            changed.append((rel, count))
            if not check:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(updated)
    for rel, count in changed:
        print(f'{count:6}  {rel}')
    print(f'{total} occurrences of {old} {"would be renamed" if check else "renamed"} to {new} in {len(changed)} files')
    keywords = os.path.join('src', 'analysis', 'keywords.sn')
    if os.path.isfile(keywords) and old in open(keywords, encoding='utf-8').read():
        print('src/analysis/keywords.sn: regenerate it from the compiler: tools/generate_keywords.py')
    if check and changed:
        sys.exit(1)


if __name__ == '__main__':
    main()
