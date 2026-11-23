#!/usr/bin/env python3
"""End-to-end JSON-RPC test of sultanc-analyzer over stdio.

usage: tests/lsp_integration.py /path/to/sultanc [path/to/sultanc-analyzer]

Each check drives one LSP method on the fixtures and asserts on the reply.
The server runs with the SultanC checkout as its working directory (the
compiler resolves std as library/ there), as the VS Code extension runs it;
the fixtures live in a separate temporary project folder.
"""
import json, os, queue, shutil, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))


class Client:
    def __init__(self, cmd, cwd, env=None):
        self.p = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.id, self.q, self.notes, self.stderr = 0, queue.Queue(), [], []
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=lambda: [self.stderr.append(l) for l in self.p.stderr], daemon=True).start()

    def _read(self):
        f = self.p.stdout
        while True:
            hdr = b''
            while not hdr.endswith(b'\r\n\r\n'):
                c = f.read(1)
                if not c:
                    self.q.put(None); return
                hdr += c
            n = int([h for h in hdr.decode().split('\r\n') if h.lower().startswith('content-length')][0].split(':')[1])
            body = json.loads(f.read(n).decode('utf-8'))
            (self.q.put if 'id' in body and ('result' in body or 'error' in body) else self.notes.append)(body)

    def send(self, obj):
        b = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.p.stdin.write(b'Content-Length: %d\r\n\r\n' % len(b) + b); self.p.stdin.flush()

    def request(self, method, params, timeout=60):
        self.id += 1
        self.send({'jsonrpc': '2.0', 'id': self.id, 'method': method, 'params': params})
        while True:
            r = self.q.get(timeout=timeout)
            if r is None:
                raise RuntimeError('server exited: ' + b''.join(self.stderr).decode('utf-8', 'replace')[-400:])
            if r.get('id') == self.id:
                if 'error' in r:
                    raise RuntimeError(f"{method}: {r['error']}")
                return r['result']

    def send_batch(self, messages):
        """Writes several frames with one write, so the server finds them all queued."""
        out = b''
        for m in messages:
            b = json.dumps(m, ensure_ascii=False).encode('utf-8')
            out += b'Content-Length: %d\r\n\r\n' % len(b) + b
        self.p.stdin.write(out); self.p.stdin.flush()

    def responses(self, ids, timeout=60):
        got = {}
        while set(got) != set(ids):
            r = self.q.get(timeout=timeout)
            if r is None:
                raise RuntimeError('server exited')
            if r.get('id') in ids:
                got[r['id']] = r
        return got

    def notify(self, method, params):
        self.send({'jsonrpc': '2.0', 'method': method, 'params': params})


def at(text, needle, off=0, nth=0):
    i = -1
    for _ in range(nth + 1):
        i = text.index(needle, i + 1)
    before = text[:i + off]
    return {'line': before.count('\n'), 'character': len(before.split('\n')[-1].encode('utf-16-le')) // 2}


RESULTS = []


def check(name, fn):
    try:
        fn(); RESULTS.append((True, name, ''))
    except Exception as e:  # noqa: BLE001 - report every failure
        RESULTS.append((False, name, f'{type(e).__name__}: {e}'))


def main():
    home = os.path.abspath(sys.argv[1])
    server = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(home, 'build', 'sultanc-analyzer')
    # The compiler the checks compare against (`sultanc fmt`, `sultanc test`):
    # the checkout's, else $SULTANC, else ~/.supax/bin/sultanc, as tools/build.sh.
    global COMPILER
    for candidate in [os.path.join(home, 'build', 'sultanc'), os.environ.get('SULTANC', ''),
                      os.path.expanduser('~/.supax/bin/sultanc'), shutil.which('sultanc') or '']:
        if candidate and os.access(candidate, os.X_OK):
            COMPILER = candidate
            break
    else:
        sys.exit('no SultanC compiler: build the checkout, set SULTANC, or install it with Supax')
    work = tempfile.mkdtemp(prefix='sultanc-analyzer-test-')
    shutil.copytree(os.path.join(HERE, 'fixtures'), work, dirs_exist_ok=True)
    uri = lambda *p: 'file://' + os.path.join(work, *p)
    en_text = open(os.path.join(work, 'sample_en.sn'), encoding='utf-8').read()
    ar_text = open(os.path.join(work, 'sample_ar.sn'), encoding='utf-8').read()

    c = Client([server], cwd=home)
    init = c.request('initialize', {'processId': None, 'rootUri': uri(), 'capabilities': {},
                                    'workspaceFolders': [{'uri': uri(), 'name': 'fixtures'}]})
    c.notify('initialized', {})
    caps = init['capabilities']
    EN, AR = uri('sample_en.sn'), uri('sample_ar.sn')
    for u, t in ((EN, en_text), (AR, ar_text)):
        c.notify('textDocument/didOpen', {'textDocument': {'uri': u, 'languageId': 'sultanc', 'version': 1, 'text': t}})
    D = lambda u: {'uri': u}
    P = lambda u, t, n, o=1, k=0: {'textDocument': D(u), 'position': at(t, n, o, k)}
    hover = lambda u, t, n, o=1, k=0: (c.request('textDocument/hover', P(u, t, n, o, k)) or {}).get('contents', {}).get('value', '')

    def capabilities():
        for k in ['hoverProvider', 'completionProvider', 'signatureHelpProvider', 'foldingRangeProvider',
                  'selectionRangeProvider', 'documentLinkProvider', 'semanticTokensProvider', 'renameProvider']:
            assert k in caps, k
        assert caps['completionProvider']['triggerCharacters'] == ['.']
    check('initialize advertises capabilities', capabilities)

    def hover_en():
        h = hover(EN, en_text, 'area(Shape')
        assert 'def area(shape: Shape): int' in h, h
        assert 'Area of a shape.' in h, h
        assert '`fn(Shape): int`' in h, h
        assert 'Defined in:** [sample_en.sn:13:5](file://' in h, h
    check('hover: signature, doc comment, English types, link', hover_en)
    check('hover: record shows fields', lambda: (lambda h: None if 'type Point = { x: int, y: int };' in h else (_ for _ in ()).throw(AssertionError(h)))(hover(EN, en_text, 'Point = {', 1, 1)))

    def hover_ar():
        h = hover(AR, ar_text, 'الأكبر(الأعداد')
        assert '**الصنف:** دالة' in h and 'دالة(عدد, عدد): عدد' in h, h
    check('hover: Arabic labels and types in Arabic files', hover_ar)

    def hover_std():
        h = hover(EN, en_text, 'println(int')
        assert '`fn(&string): result int, int`' in h, h
    check('hover: std function resolves from the checkout', hover_std)

    def completion():
        reply = c.request('textDocument/completion', P(AR, ar_text, 'اطبع_سطر(', 0))
        # No letter typed yet: auto-import items need two, so the list is
        # incomplete and the client asks again as the word grows.
        assert isinstance(reply, dict) and reply['isIncomplete'] is True, reply if not isinstance(reply, dict) else reply.keys()
        items = reply['items']
        labels = [i['label'] for i in items]
        assert 'الأعداد' in labels, labels[:10]
        assert 'أرجع' in labels, 'Arabic keyword'
        en_items = c.request('textDocument/completion', P(EN, en_text, 'println(int', 0))
        en_items = en_items['items'] if isinstance(en_items, dict) else en_items
        en_labels = [i['label'] for i in en_items]
        assert 'return' in en_labels and 'أرجع' not in en_labels
    check('completion: original spelling, keywords in surface language', completion)

    def signature():
        s = c.request('textDocument/signatureHelp', P(EN, en_text, 'total, 2', 7))
        assert s['signatures'][0]['label'] == 'def scale(value: int, factor: int): int', s
        assert [p['label'] for p in s['signatures'][0]['parameters']] == ['value: int', 'factor: int']
        assert s['activeParameter'] == 1
    check('signatureHelp: named parameters', signature)

    def navigation():
        d = c.request('textDocument/definition', P(EN, en_text, 'area(Shape'))
        d = d[0] if isinstance(d, list) else d
        assert d['range']['start']['line'] == 12
        refs = c.request('textDocument/references', {**P(EN, en_text, 'scale(value'), 'context': {'includeDeclaration': True}})
        assert len(refs) == 2
        edit = c.request('textDocument/rename', {**P(EN, en_text, 'scale(value'), 'newName': 'multiply'})
        assert len(edit['changes'][EN]) == 2
    check('definition, references, rename', navigation)

    def symbols_tokens():
        names = [s['name'] for s in c.request('textDocument/documentSymbol', {'textDocument': D(EN)})]
        assert {'Point', 'Shape', 'area', 'scale', 'main'} <= set(names), names
        data = c.request('textDocument/semanticTokens/full', {'textDocument': D(EN)})['data']
        assert len(data) % 5 == 0 and data
        line = col = 0
        for i in range(0, len(data), 5):  # strictly increasing positions
            dl, dc = data[i], data[i + 1]
            assert dl > 0 or dc > 0 or i == 0
    check('documentSymbol and semanticTokens (ordered)', symbols_tokens)

    def structure():
        folds = c.request('textDocument/foldingRange', {'textDocument': D(EN)})
        assert {'startLine': 12, 'endLine': 15} in folds, folds
        assert any(f.get('kind') == 'imports' for f in folds)
        links = c.request('textDocument/documentLink', {'textDocument': D(EN)})
        assert any(l['target'].endswith('/library/std/io/println.sn') for l in links), links
        sel = c.request('textDocument/selectionRange', {'textDocument': D(EN), 'positions': [at(en_text, 'factor;', 2)]})
        assert sel[0]['parent']['parent']
    check('folding, document links, selection ranges', structure)

    def typing():
        broken = en_text.replace('return 0;', 'let cx: int = corner.\n    return 0;')
        c.notify('textDocument/didChange', {'textDocument': {'uri': EN, 'version': 2}, 'contentChanges': [{'text': broken}]})
        time.sleep(1.0)
        items = c.request('textDocument/completion', P(EN, broken, 'corner.\n', 7))
        assert sorted(i['label'] for i in items) == ['x', 'y'], items
        assert 'def area' in hover(EN, broken, 'area(Shape')
        diags = [n for n in c.notes if n.get('method') == 'textDocument/publishDiagnostics' and n['params']['uri'] == EN]
        assert diags and diags[-1]['params']['diagnostics'], 'expected a syntax diagnostic'
    check('while typing: member completion, hover, diagnostics', typing)
    c.notify('textDocument/didChange', {'textDocument': {'uri': EN, 'version': 3}, 'contentChanges': [{'text': en_text}]})
    time.sleep(1.0)

    def foreign_error():
        c2 = Client([server], cwd=home)
        root = 'file://' + os.path.join(work, 'project')
        c2.request('initialize', {'processId': None, 'rootUri': root, 'capabilities': {},
                                  'workspaceFolders': [{'uri': root, 'name': 'p'}], 'initializationOptions': {'language': 'ar'}})
        c2.notify('initialized', {})
        main = os.path.join(work, 'project', 'main.sn')
        c2.notify('textDocument/didOpen', {'textDocument': {'uri': 'file://' + main, 'languageId': 'sultanc', 'version': 1,
                                                            'text': open(main, encoding='utf-8').read()}})
        deadline = time.time() + 20
        while time.time() < deadline and not any(n.get('method') == 'textDocument/publishDiagnostics' and n['params']['diagnostics'] for n in c2.notes):
            time.sleep(0.2)
        msg = [d['message'] for n in c2.notes if n.get('method') == 'textDocument/publishDiagnostics' for d in n['params']['diagnostics']]
        assert msg and 'helper.sn:2:' in msg[0], msg
        assert any('؀' <= ch <= 'ۿ' for ch in msg[0]), 'expected Arabic message'
        c2.request('shutdown', None); c2.notify('exit', None)
    check('errors in other modules surface with location, in Arabic on request', foreign_error)

    def inlay():
        hints = c.request('textDocument/inlayHint', {'textDocument': D(EN), 'range': {'start': {'line': 0, 'character': 0}, 'end': {'line': 40, 'character': 0}}})
        labels = [h['label'] for h in hints]
        assert 'value:' in labels and 'factor:' in labels, labels
        h = [x for x in hints if x['label'] == 'value:'][0]
        assert h['position'] == at(en_text, 'total, 2', 0), h
    check('inlay hints: parameter names at call sites', inlay)

    def type_definition():
        loc = c.request('textDocument/typeDefinition', P(EN, en_text, 'corner))', 1))
        loc = loc[0] if isinstance(loc, list) else loc
        assert loc and loc['range']['start']['line'] == 4, loc
    check('typeDefinition: variable -> its record type', type_definition)

    def keyword_hover():
        h = hover(EN, en_text, 'return value', 1)
        assert '**Keyword**' in h and '`أرجع`' in h, h
        h2 = hover(AR, ar_text, 'أرجع الثاني', 1)
        assert '**كلمة محجوزة**' in h2 and '`return`' in h2, h2
        # `module` / `وحدة` (MODULE, interp2): a module's spellings in a root file.
        for name, t in (('mod_en.sn', 'module text { ar: نصوص };\n'), ('mod_ar.sn', 'وحدة نصوص { en: text };\n')):
            u = uri(name)
            c.notify('textDocument/didOpen', {'textDocument': {'uri': u, 'languageId': 'sultanc', 'version': 1, 'text': t}})
            h3 = c.request('textDocument/hover', {'textDocument': D(u), 'position': {'line': 0, 'character': 2}})
            assert h3['contents']['value'].endswith('English: `module` · العربية: `وحدة`'), h3
    check('keyword hover shows both spellings', keyword_hover)

    def tokens_range():
        data = c.request('textDocument/semanticTokens/range', {'textDocument': D(EN), 'range': {'start': {'line': 18, 'character': 0}, 'end': {'line': 20, 'character': 0}}})['data']
        assert data and data[0] == 18, data[:10]
    check('semanticTokens/range', tokens_range)

    def workspace_diag():
        r = c.request('workspace/diagnostic', {'previousResultIds': []})
        assert 'items' in r
    check('workspace/diagnostic (bounded)', workspace_diag)

    def open_files_only():
        ws = tempfile.mkdtemp(prefix='sultanc-analyzer-ws-')
        files = {
            'broken.sn': 'def main(): int {\n    let x: int = missing_name;\n    return x;\n}\n',
            'closed_bad.sn': 'def helper(): int {\n    return "text";\n}\n',
        }
        for name, text in files.items():
            open(os.path.join(ws, name), 'w', encoding='utf-8').write(text)
        wuri = lambda n: 'file://' + os.path.join(ws, n)
        c3 = Client([server], cwd=home)
        init = c3.request('initialize', {'processId': None, 'rootUri': 'file://' + ws, 'workspaceFolders': [{'uri': 'file://' + ws, 'name': 'w'}],
                                         'capabilities': {'textDocument': {'diagnostic': {}}}})
        c3.notify('initialized', {})
        assert init['capabilities']['diagnosticProvider']['workspaceDiagnostics'] is False
        assert c3.request('workspace/diagnostic', {'previousResultIds': []})['items'] == []
        c3.notify('textDocument/didOpen', {'textDocument': {'uri': wuri('broken.sn'), 'languageId': 'sultanc', 'version': 1, 'text': files['broken.sn']}})
        doc = c3.request('textDocument/diagnostic', {'textDocument': {'uri': wuri('broken.sn')}})
        assert [d['range']['start']['line'] for d in doc['items']] == [1], doc
        time.sleep(0.5)
        assert not any(n.get('method') == 'textDocument/publishDiagnostics' for n in c3.notes), 'pushed to a pull client'
        c3.request('shutdown', None); c3.notify('exit', None)
    check('diagnostics: open files only, no push to pull clients', open_files_only)

    def refactor_session(files):
        ws = tempfile.mkdtemp(prefix='sultanc-analyzer-rf-')
        for name, text in files.items():
            open(os.path.join(ws, name), 'w', encoding='utf-8').write(text)
        c4 = Client([server], cwd=home)
        c4.request('initialize', {'processId': None, 'rootUri': 'file://' + ws, 'workspaceFolders': [{'uri': 'file://' + ws, 'name': 'w'}],
                                  'capabilities': {'textDocument': {'diagnostic': {}}}})
        c4.notify('initialized', {})
        for name, text in files.items():
            c4.notify('textDocument/didOpen', {'textDocument': {'uri': 'file://' + os.path.join(ws, name), 'languageId': 'sultanc', 'version': 1, 'text': text}})
        return c4, (lambda n: 'file://' + os.path.join(ws, n))

    def apply_edits(text, edits):
        lines = text.split('\n')
        off = lambda p: sum(len(l.encode('utf-16-le')) // 2 + 1 for l in lines[:p['line']]) + p['character']
        # Offsets are UTF-16 code units, so the text is edited as UTF-16.
        units = text.encode('utf-16-le')
        for e in sorted(edits, key=lambda e: off(e['range']['start']), reverse=True):
            a, b = off(e['range']['start']), off(e['range']['end'])
            units = units[:2 * a] + e['newText'].encode('utf-16-le') + units[2 * b:]
        return units.decode('utf-16-le')

    RF_EN = ('import std.text.transform;\nimport std.io.println;\nimport std.text.number;\nimport std.io.println;\n\n'
             'def main(): int {\n    let total: int = 2 + 3;\n    let doubled: int = total * 2;\n'
             '    println(int_to_text(doubled + 1));\n    return 0;\n}\n')
    RANGE = lambda l1, c1, l2, c2: {'start': {'line': l1, 'character': c1}, 'end': {'line': l2, 'character': c2}}

    def code_actions():
        missing = 'def main(): int {\n    println("hi");\n    return 0;\n}\n'
        c4, U = refactor_session({'en.sn': RF_EN, 'missing.sn': missing})
        act = lambda n, r, only=None: c4.request('textDocument/codeAction', {'textDocument': {'uri': U(n)}, 'range': r,
                                                 'context': {'diagnostics': [], **({'only': only} if only else {})}}, timeout=120)
        c4.request('textDocument/diagnostic', {'textDocument': {'uri': U('missing.sn')}})
        fix = [a for a in act('missing.sn', RANGE(1, 4, 1, 4)) if a['kind'] == 'quickfix']
        # The compiler's import-module suggestion (its own words), preferred.
        assert len(fix) == 1 and fix[0]['isPreferred'], fix
        assert fix[0]['edit']['changes'][U('missing.sn')] == [{'range': RANGE(0, 0, 0, 0), 'newText': 'import std.io.println;\n\n'}], fix
        organized = act('en.sn', RANGE(0, 0, 0, 0), ['source.organizeImports'])
        assert len(organized) == 1
        text = apply_edits(RF_EN, organized[0]['edit']['changes'][U('en.sn')])
        assert text.startswith('import std.io.println;\nimport std.text.number;\n\n'), text[:120]
        extract = [a for a in act('en.sn', RANGE(8, 24, 8, 35)) if a['kind'] == 'refactor.extract.variable']
        text = apply_edits(RF_EN, extract[0]['edit']['changes'][U('en.sn')])
        assert '    let value: int = doubled + 1;\n    println(int_to_text(value));' in text, text
        inline = [a for a in act('en.sn', RANGE(6, 9, 6, 9)) if a['kind'] == 'refactor.inline']
        text = apply_edits(RF_EN, inline[0]['edit']['changes'][U('en.sn')])
        assert '    let doubled: int = (2 + 3) * 2;' in text and 'total' not in text, text
        c4.request('shutdown', None); c4.notify('exit', None)
    check('code actions: add import, organize imports, extract and inline variable', code_actions)

    def rewrite_actions():
        opt = ('def show(v: option int): int {\n    match v with\n    | option.some(x) -> { return x; };\n    return 0;\n}\n'
               'def main(): int {\n    return show(option.some(1));\n}\n')
        cond = ('def main(): int {\n    let n: int = 3;\n    if (n > 2) {\n        return 1;\n    } else {\n        return 2;\n    };\n'
                '    if (n > 5) {\n        return 3;\n    };\n    return 0;\n}\n')
        c4, U = refactor_session({'opt.sn': opt, 'cond.sn': cond})
        act = lambda n, r: c4.request('textDocument/codeAction', {'textDocument': {'uri': U(n)}, 'range': r,
                                      'context': {'diagnostics': []}}, timeout=120)
        rep = c4.request('textDocument/diagnostic', {'textDocument': {'uri': U('opt.sn')}})
        assert any(d.get('code') == 'SULTANC-PATTERN-NON-EXHAUSTIVE' for d in rep['items']), rep
        # The compiler's add-missing-arms fix, on the matched value `v`.
        arms = [a for a in act('opt.sn', RANGE(1, 10, 1, 10)) if a['title'] == 'add an arm for each case that is not covered']
        assert arms and arms[0]['kind'] == 'quickfix', arms
        text = apply_edits(opt, arms[0]['edit']['changes'][U('opt.sn')])
        assert '    | option.some(x) -> { return x; }\n    | option.none -> { };\n' in text, text
        inv = [a for a in act('cond.sn', RANGE(2, 5, 2, 5)) if a['title'] == 'Invert condition and swap branches']
        text = apply_edits(cond, inv[0]['edit']['changes'][U('cond.sn')])
        assert 'if (!(n > 2)) {\n        return 2;\n    } else {\n        return 1;\n    };' in text, text
        add = [a for a in act('cond.sn', RANGE(7, 5, 7, 5)) if a['title'] == 'Add else branch']
        text = apply_edits(cond, add[0]['edit']['changes'][U('cond.sn')])
        assert '        return 3;\n    } else {\n' in text, text
        assert not [a for a in act('cond.sn', RANGE(2, 5, 2, 5)) if a['title'] == 'Add else branch']
        c4.request('shutdown', None); c4.notify('exit', None)
    check('code actions: missing match arms, invert if, add else', rewrite_actions)

    def scheduling():
        src = 'def main(): int {\n    let n: int = 1;\n    return n;\n}\n'
        c4, U = refactor_session({'s.sn': src})
        c4.request('textDocument/diagnostic', {'textDocument': {'uri': U('s.sn')}})
        hover = lambda i: {'jsonrpc': '2.0', 'id': i, 'method': 'textDocument/hover',
                           'params': {'textDocument': {'uri': U('s.sn')}, 'position': {'line': 2, 'character': 11}}}
        cancel = lambda i: {'jsonrpc': '2.0', 'method': '$/cancelRequest', 'params': {'id': i}}
        change = lambda v, n: {'jsonrpc': '2.0', 'method': 'textDocument/didChange',
                               'params': {'textDocument': {'uri': U('s.sn'), 'version': v},
                                          'contentChanges': [{'text': src.replace('1;', '%d;' % n)}]}}
        # Each batch starts with a change, so its first request analyses anew
        # while the reader thread receives the rest: the cancellations reach a
        # running request or a queued one, never a finished one.
        # 101 is cancelled; 102 runs (its cancel names another id); "r-3" is a string id.
        c4.send_batch([change(2, 2), hover(101), hover(102), hover('r-3'), cancel(101), cancel(999), cancel('r-3')])
        r = c4.responses([101, 102, 'r-3'])
        assert r[101]['error']['code'] == -32800, r[101]
        assert 'result' in r[102] and 'int' in r[102]['result']['contents']['value'], r[102]
        assert r['r-3']['error']['code'] == -32800, r['r-3']
        # A request followed by a change of its document is stale.
        c4.send_batch([change(3, 3), hover(103), {'jsonrpc': '2.0', 'id': 104, 'method': 'textDocument/diagnostic',
                                    'params': {'textDocument': {'uri': U('s.sn')}}}, change(4, 4), hover(105)])
        r = c4.responses([103, 104, 105])
        assert r[103]['error']['code'] == -32801, r[103]
        assert r[104]['error']['code'] == -32802 and r[104]['error']['data'] == {'retriggerRequest': True}, r[104]
        assert 'result' in r[105], r[105]
        # Lifecycle requests are never cancelled.
        c4.send_batch([{'jsonrpc': '2.0', 'id': 106, 'method': 'shutdown'}, cancel(106)])
        assert c4.responses([106])[106].get('result', 'x') is None
        c4.notify('exit', None)
    check('scheduling: $/cancelRequest, stale requests, ServerCancelled for diagnostics', scheduling)

    def large_project():
        # Over the former 300-file cap: a reference in a closed file is found.
        ws = tempfile.mkdtemp(prefix='sultanc-analyzer-big-')
        decl = 'عام عرف أداة_عرض(): عدد { أرجع 1; }\nعام عرف fmt_arg(): عدد { أرجع 2; }\n'
        open(os.path.join(ws, 'lib.sn'), 'w', encoding='utf-8').write(decl)
        for i in range(319):
            body = 'عرف دالة_%d(): عدد { أرجع %d; }\n' % (i, i)
            if i == 317:
                body = 'استورد "lib.sn";\nعرف المستخدم(): عدد { أرجع أداة_عرض(); }\n'
            open(os.path.join(ws, 'f%03d.sn' % i), 'w', encoding='utf-8').write(body)
        c5 = Client([server], cwd=home)
        c5.request('initialize', {'processId': None, 'rootUri': 'file://' + ws, 'workspaceFolders': [{'uri': 'file://' + ws, 'name': 'big'}], 'capabilities': {}})
        c5.notify('initialized', {})
        lib = 'file://' + os.path.join(ws, 'lib.sn')
        c5.notify('textDocument/didOpen', {'textDocument': {'uri': lib, 'languageId': 'sultanc', 'version': 1, 'text': decl}})
        refs = c5.request('textDocument/references', {'textDocument': {'uri': lib}, 'position': {'line': 0, 'character': 8},
                                                      'context': {'includeDeclaration': True}}, timeout=300)
        got = sorted((r['uri'].rsplit('/', 1)[1], r['range']['start']['line'], r['range']['start']['character']) for r in refs)
        assert got == [('f317.sn', 1, 27), ('lib.sn', 0, 8)], got
        names = lambda q: sorted(x['name'] for x in c5.request('workspace/symbol', {'query': q}, timeout=300))
        assert names('اداة') == ['أداة_عرض'], names('اداة')          # Alef forms are one letter
        assert names('أـداة') == ['أداة_عرض'], names('أـداة')        # Kashida is ignored
        assert names('ادع') == ['أداة_عرض'], names('ادع')            # in-order subsequence
        assert names('FmtArg') == ['fmt_arg'], names('FmtArg')       # ASCII case folds
        assert 'دالة_318' in names('دالة_318') and names('zzz') == []
        c5.request('shutdown', None); c5.notify('exit', None)
    check('large project: closed-file references past 300 files; identity-aware fuzzy workspace symbols', large_project)

    def compiler_fixes():
        # Quick fixes come from the compiler's structured fixes (iSpeak wording),
        # titled in the document's language and tied to their diagnostic.
        files = {'typo.sn': 'عرف الرئيسية(): عدد {\n    ءرجع 0;\n}\n',
                 'semi.sn': 'def main(): i32 {\n    let value: i32 = 42\n    return value;\n}\n',
                 'moved.sn': 'def main(): i32 {\n    let value: i32 = 42\n};\n'}
        c4, U = refactor_session(files)
        expect = {
            'typo.sn': ('SULTANC-PARSE-KEYWORD-TYPO', 'استبدل هذه التهجئة بالكلمة المحجوزة المقترحة', 'عرف الرئيسية(): عدد {\n    أرجع 0;\n}\n'),
            'semi.sn': ('SULTANC-PARSE-SYNTAX', 'insert `;` after this construct', 'def main(): i32 {\n    let value: i32 = 42;\n    return value;\n}\n'),
            'moved.sn': ('SULTANC-PARSE-MISPLACED-SEMICOLON', 'move `;` before the closing `}`', 'def main(): i32 {\n    let value: i32 = 42;\n}\n'),
        }
        for name, (code, title, fixed) in expect.items():
            diags = c4.request('textDocument/diagnostic', {'textDocument': {'uri': U(name)}})['items']
            assert [d['code'] for d in diags] == [code], diags
            acts = c4.request('textDocument/codeAction', {'textDocument': {'uri': U(name)}, 'range': diags[0]['range'],
                                                          'context': {'diagnostics': diags}})
            fixes = [a for a in acts if a['kind'] == 'quickfix']
            assert [a['title'] for a in fixes] == [title], fixes
            assert fixes[0]['isPreferred'] and [d['code'] for d in fixes[0]['diagnostics']] == [code], fixes[0]
            assert apply_edits(files[name], fixes[0]['edit']['changes'][U(name)]) == fixed, fixes[0]
        c4.request('shutdown', None); c4.notify('exit', None)
    check('compiler quick fixes: keyword typo, missing and misplaced semicolon', compiler_fixes)

    def compiler_suggestions():
        # Suggestions from compiler.diagnostics.suggestions (e8d68f0): wording
        # in the document's language, the compiler's UTF-16 positions (the
        # `deref` edit sits after a character outside the BMP), preferred only
        # when machine-applicable, `key` and `applicability` in data.fixes.
        files = {'mut.sn': 'عرف الرئيسية(): عدد {\n    ليكن س: عدد = 1;\n    س := 2;\n    أرجع س;\n}\n',
                 'deref.sn': 'def main(): int {\n    let a: int = 1;\n    let r: &int = &a;\n    let s: string = "𝒳"; let b: int = r;\n    return b;\n}\n',
                 'similar.sn': 'def main(): int {\n    let count: int = 1;\n    return coutn;\n}\n',
                 'lex.sn': 'def main(): int {\n    let 𝒳: int = 1;\n    return 0;\n}\n'}
        c4, U = refactor_session(files)
        expect = {
            'mut.sn': ('SULTANC-MUTABILITY-WRITE-TO-IMMUTABLE', ('declare-mutable', 'machine-applicable'),
                       'صرح بالمتغير بـ`متغير` لتكتب فيه', True, (1, 12, 1, 12, 'متغير '),
                       'عرف الرئيسية(): عدد {\n    ليكن س: متغير عدد = 1;\n    س := 2;\n    أرجع س;\n}\n'),
            'deref.sn': ('SULTANC-TYPE-MISMATCH', ('dereference', 'machine-applicable'),
                         'read the referenced value with `*`', True, (3, 39, 3, 39, '*'),
                         files['deref.sn'].replace('int = r;', 'int = *r;')),
            'similar.sn': ('SULTANC-NAME-UNKNOWN', ('similar-name', 'maybe-incorrect'),
                           'a name with a similar spelling is visible here', False, (2, 11, 2, 16, 'count'),
                           files['similar.sn'].replace('coutn', 'count')),
        }
        for name, (code, data_fix, title, preferred, edit, fixed) in expect.items():
            diags = c4.request('textDocument/diagnostic', {'textDocument': {'uri': U(name)}})['items']
            assert [d['code'] for d in diags] == [code], diags
            assert [(f['key'], f['applicability']) for f in diags[0]['data']['fixes']] == [data_fix], diags[0]['data']
            acts = c4.request('textDocument/codeAction', {'textDocument': {'uri': U(name)}, 'range': diags[0]['range'],
                                                          'context': {'diagnostics': diags}})
            fixes = [a for a in acts if a['kind'] == 'quickfix']
            assert [(a['title'], a['isPreferred']) for a in fixes] == [(title, preferred)], fixes
            e = fixes[0]['edit']['changes'][U(name)]
            assert [(x['range']['start']['line'], x['range']['start']['character'], x['range']['end']['line'],
                     x['range']['end']['character'], x['newText']) for x in e] == [edit], e
            assert apply_edits(files[name], e) == fixed, e
        # A lexer error over a 4-byte character covers it whole: UTF-16 8..10.
        d = c4.request('textDocument/diagnostic', {'textDocument': {'uri': U('lex.sn')}})['items']
        assert [(x['code'], x['range']) for x in d] == [('SULTANC-LEX-INVALID-TOKEN',
            {'start': {'line': 1, 'character': 8}, 'end': {'line': 1, 'character': 10}})], d
        c4.request('shutdown', None); c4.notify('exit', None)
    check('compiler suggestions: declare-mutable (Arabic), dereference after a non-BMP character, similar name; lexer range', compiler_suggestions)

    def supax_package_graph():
        # A folder with Supax.toml: the project is its package graph's root
        # source_root (`supax metadata`), so app/scratch is not a project file
        # and util (a path dependency outside the folder) comes in through the
        # import. Editing Supax.toml and sending didChangeWatchedFiles re-runs
        # metadata. Without supax the server warns. Needs supax: $SUPAX or PATH.
        supax = os.environ.get('SUPAX') or shutil.which('supax')
        if not supax:
            print('skip supax package graph: set SUPAX'); return
        ws = tempfile.mkdtemp(prefix='sultanc-analyzer-supax-')
        files = {'app/Supax.toml': '[package]\nname = "app"\nversion = "0.1.0"\n\n[lib]\npath = "src"\n\n[dependencies]\nutil = { path = "../util" }\n',
                 'util/Supax.toml': '[package]\nname = "util"\nversion = "0.1.0"\n\n[lib]\npath = "src"\n',
                 'util/src/lib.sn': 'public def twice(x: int): int { return x * 2; }\n',
                 'app/src/main.sn': 'import util.lib;\nimport std.debug.assert;\n\ndef main(): int {\n    return twice(21) - 42;\n}\n\n@@test\ndef checks_util(): void {\n    assert(twice(21) == 42);\n}\n',
                 'app/scratch/other.sn': 'def twice(x: int): int { return x; }\n'}
        for n, t in files.items():
            os.makedirs(os.path.dirname(os.path.join(ws, n)), exist_ok=True)
            open(os.path.join(ws, n), 'w', encoding='utf-8').write(t)
        app = os.path.join(ws, 'app')
        def start(path):
            env = dict(os.environ, SUPAX=path)
            k = Client([server], cwd=home, env=env)
            k.request('initialize', {'processId': None, 'rootUri': 'file://' + app, 'capabilities': {},
                                     'workspaceFolders': [{'uri': 'file://' + app, 'name': 'app'}]})
            k.notify('initialized', {})
            return k
        sym = lambda k: sorted(s['location']['uri'][len('file://' + ws) + 1:] for s in k.request('workspace/symbol', {'query': 'twice'}))
        k = start(supax)
        assert sym(k) == ['util/src/lib.sn'], sym(k)
        # Check on save in a Supax package: app/src/main.sn with the graph on
        # standard input; util (a dependency) resolves, so nothing is reported.
        end = time.time() + 60
        logs = lambda: [n['params']['message'] for n in k.notes if n.get('method') == 'window/logMessage']
        while time.time() < end and not any(m.startswith('check on save: done') for m in logs()):
            time.sleep(0.1)
        assert 'check on save: done, diagnostics in 0 file(s)' in logs(), logs()
        assert any(m.endswith(' check ' + os.path.join(app, 'src', 'main.sn')) for m in logs()), logs()
        # sultanc/packageGraph: the graph with the file's package as root, for
        # `sultanc test --package-graph=-`; the test then resolves `util`.
        main_uri = 'file://' + os.path.join(app, 'src', 'main.sn')
        graph = k.request('sultanc/packageGraph', {'textDocument': {'uri': main_uri}})['graph']
        assert 'root = "' in graph and 'source_root' in graph, graph
        run = subprocess.run([COMPILER, '--lang=en', 'test', main_uri[len('file://'):],
                              '--test=checks_util', '--package-graph=-'], input=graph, capture_output=True, text=True, cwd=home)
        assert run.returncode == 0 and run.stdout.startswith('PASS checks_util\n'), (run.returncode, run.stdout, run.stderr)
        alone = 'file://' + os.path.join(ws, 'alone.sn')
        open(alone[len('file://'):], 'w').write('def main(): int { return 0; }\n')
        assert k.request('sultanc/packageGraph', {'textDocument': {'uri': alone}}) is None
        open(os.path.join(app, 'Supax.toml'), 'w', encoding='utf-8').write(files['app/Supax.toml'].replace('"src"', '"scratch"'))
        k.notify('workspace/didChangeWatchedFiles', {'changes': [{'uri': 'file://' + app + '/Supax.toml', 'type': 2}]})
        assert sym(k) == ['app/scratch/other.sn'], sym(k)
        k.request('shutdown', None); k.notify('exit', None)
        k = start('/nonexistent/supax')
        time.sleep(0.5)
        warn = [n['params'] for n in k.notes if n.get('method') == 'window/showMessage']
        assert warn == [{'type': 2, 'message': 'supax could not be started (`/nonexistent/supax`); set SUPAX or put supax on PATH'}], warn
        k.request('shutdown', None); k.notify('exit', None)
    check('supax: project from the package graph, re-run on Supax.toml change, warning without supax', supax_package_graph)

    def formatting():
        # The compiler's formatter (compiler/format): the edits turn the text
        # into exactly what `sultanc fmt` writes; a file that does not parse
        # gets null; a range gets only the edits that touch it.
        files = {'a.sn': 'عرف   الرئيسية( ):عدد{\n  ليكن س:عدد=1 ;\n        أرجع س;}\n',
                 'b.sn': 'def main(): int {\n    return 0\n',
                 'c.sn': 'def f() : int { return 1; }\n// 𝒳 note\ndef  g():int{return 2;}\n',
                 # 35b9d86: the declaration after @@ starts at the annotation's column.
                 'd.sn': 'import std.debug.assert;\n\n    @@test\n  def  t( ):void{ assert(1==1); }\n'}
        c4, U = refactor_session(files)
        opts = {'tabSize': 4, 'insertSpaces': True}
        for name in ('a.sn', 'c.sn', 'd.sn'):
            edits = c4.request('textDocument/formatting', {'textDocument': {'uri': U(name)}, 'options': opts})
            path = U(name)[len('file://'):]
            subprocess.run([COMPILER, 'fmt', path], cwd=home, capture_output=True)
            expected = open(path, encoding='utf-8').read()
            assert apply_edits(files[name], edits) == expected, (edits, expected)
        assert c4.request('textDocument/formatting', {'textDocument': {'uri': U('b.sn')}, 'options': opts}) is None
        ranged = c4.request('textDocument/rangeFormatting', {'textDocument': {'uri': U('c.sn')}, 'options': opts,
                                                               'range': RANGE(2, 0, 2, 23)})
        assert [e['range']['start']['line'] for e in ranged] == [2, 2, 2, 2, 2], ranged
        c4.request('shutdown', None); c4.notify('exit', None)
    check('formatting: compiler formatter edits equal sultanc fmt; null for a file that does not parse; range', formatting)

    def completion_at_cursor():
        # Completion from the compiler (tooling_completion.sn) on unfinished
        # lines: the cases of LSP_COMPILER_REQUESTS.md request 1 (T1-T6).
        files = {
            't1.sn': 'type Point = { x: int, y: int };\ndef main(): int {\n    let p: Point = { x: 1, y: 2 };\n    return p.\n}\n',
            't2.sn': 'نوع نقطة = { س: عدد, ص: عدد };\nعرف الرئيسية(): عدد {\n    ليكن ن: نقطة = { س: 1, ص: 2 };\n    أرجع ن.\n}\n',
            't3.sn': 'استورد المكتبة.دخ.\nعرف الرئيسية(): عدد { أرجع 0; }\n',
            't4.sn': 'def helper(a: int): int { return a; }\ndef main(): int {\n    let total: int = 1;\n    return he\n}\n',
            't5.sn': 'type Color = | Red | Green;\ndef main(): int {\n    let c: Color = Color.\n    return 0;\n}\n',
            't6.sn': 'def main(): int { let s: string = "p.x"; return 0; }\n',
            't7.sn': 'import std.io.println;\ndef main(): int {\n    std.io.\n    return 0;\n}\n',
            't8.sn': 'import std.\ndef main(): int { return 0; }\n',
            't9.sn': 'استورد المكتبة.\nعرف الرئيسية(): عدد { أرجع 0; }\n',
        }
        c4, U = refactor_session(files)
        def items(name, line, char):
            r = c4.request('textDocument/completion', {'textDocument': {'uri': U(name)}, 'position': {'line': line, 'character': char}})
            r = r['items'] if isinstance(r, dict) else (r or [])
            return sorted(r, key=lambda i: (i['sortText'], i['label']))
        got = items('t1.sn', 3, 13)
        assert [(i['label'], i['kind'], i['detail']) for i in got] == [('x', 5, 'int'), ('y', 5, 'int')], got
        assert got[0]['textEdit']['range'] == RANGE(3, 13, 3, 13), got[0]
        got = items('t2.sn', 3, 11)
        assert [(i['label'], i['kind'], i['detail']) for i in got] == [('س', 5, 'عدد'), ('ص', 5, 'عدد')], got
        io = ['buffered_writer', 'io', 'log', 'print', 'print_failure', 'print_formatted', 'println',
              'read_line', 'reader', 'writer']
        # An Arabic file: the Arabic spellings first (each naming its module),
        # then the canonical names.
        io_ar = [('اطبع', 'print'), ('اطبع_سطر', 'println'), ('اطبع_فشل', 'print_failure'),
                 ('اطبع_منسقا', 'print_formatted'), ('اقرأ_سطر', 'read_line'), ('سجل', 'log'),
                 ('قارئ', 'reader'), ('كاتب', 'writer'), ('كاتب_مؤقت', 'buffered_writer')]
        got = items('t3.sn', 0, 18)
        assert [(i['label'], i.get('detail')) for i in got[:len(io_ar)]] == io_ar, got
        assert [(i['label'], i['kind']) for i in got[len(io_ar):]] == [(n, 9) for n in io], got
        got = items('t4.sn', 3, 13)
        assert [(i['label'], i['kind']) for i in got[:3]] == [('total', 6), ('helper', 3), ('main', 3)], got[:4]
        assert got[0]['detail'] == 'int' and got[1]['detail'] == 'def helper(a: int): int', got[:2]
        assert got[0]['textEdit'] == {'range': RANGE(3, 11, 3, 13), 'newText': 'total'}, got[0]
        assert 'a' not in [i['label'] for i in got]                        # helper's parameter
        assert 'return' in [i['label'] for i in got if i['kind'] == 14]     # keywords after names
        got = items('t5.sn', 2, 25)
        assert sorted(i['label'] for i in got) == ['Green', 'Red'] and {i['kind'] for i in got} == {20}, got
        assert items('t6.sn', 0, 37) == []
        got = items('t7.sn', 2, 11)
        assert [(i['label'], i['kind']) for i in got] == [(n, 9) for n in io], got
        # Module spellings (0e3479d+: اللغة / الأصلي): an English document gets
        # the canonical names only; an Arabic one its Arabic spellings first,
        # each naming its canonical module, then the canonical names.
        got = [i['label'] for i in items('t8.sn', 0, 11)]
        assert 'fs' in got and 'io' in got and 'archivos' not in got and 'ملفات' not in got, got
        got = items('t9.sn', 0, 15)
        assert (got[0]['label'], got[0]['detail']) == ('أخطاء', 'error'), got[:2]
        assert 'archivos' not in [i['label'] for i in got] and 'io' in [i['label'] for i in got], got
        c4.request('shutdown', None); c4.notify('exit', None)
    check('completion at the cursor on unfinished lines: fields (en, ar), import path, scope, constructors, string, module path', completion_at_cursor)

    def test_discovery():
        # sultanc/tests: the compiler's discovery (test_mode/discovery.sn) of
        # `@@test` / `@@اختبار` functions; a test with parameters is listed as
        # not runnable (`sultanc test` rejects it: SULTANC-TEST-PARAMETERS).
        files = {'en.sn': 'import std.debug.assert;\n\n@@test\ndef doubles(): void {\n    assert(2 * 2 == 4);\n}\n\n@@test\ndef takes(x: int): void { }\n\ndef main(): int { return 0; }\n',
                 'ar.sn': 'استورد المكتبة.تنقيح.تأكيد;\n\n@@اختبار\nعرف يضاعف(): فراغ {\n    تأكد(2 * 2 == 4);\n}\n',
                 'none.sn': 'def main(): int { return 0; }\n'}
        c4, U = refactor_session(files)
        got = c4.request('sultanc/tests', {'textDocument': {'uri': U('en.sn')}})
        assert got == [{'name': 'doubles', 'range': RANGE(3, 4, 3, 11), 'runnable': True},
                       {'name': 'takes', 'range': RANGE(8, 4, 8, 9), 'runnable': False}], got
        # The compiler reports an invalid test while editing (35b9d86), at its name.
        diags = c4.request('textDocument/diagnostic', {'textDocument': {'uri': U('en.sn')}})['items']
        assert [(d['code'], d['range']) for d in diags] == [('SULTANC-TEST-PARAMETERS', RANGE(8, 4, 8, 9))], diags
        got = c4.request('sultanc/tests', {'textDocument': {'uri': U('ar.sn')}})
        assert got == [{'name': 'يضاعف', 'range': RANGE(3, 4, 3, 9), 'runnable': True}], got
        assert c4.request('sultanc/tests', {'textDocument': {'uri': U('none.sn')}}) == []
        c4.request('shutdown', None); c4.notify('exit', None)
    check('sultanc/tests: compiler test discovery (en, ar, a test with parameters)', test_discovery)

    def implementation():
        # Per-target declarations: the host (linux, the test machine) is active,
        # the others are excluded by the compiler; all three are implementations.
        src = ('if (target.platform == "linux") {\n    def name(): int { return 1; }\n}\n'
               'if (target.platform == "macos") {\n    def name(): int { return 2; }\n}\n'
               'if (target.platform == "windows") {\n    def name(): int { return 3; }\n}\n'
               'def main(): int {\n    return name();\n}\n')
        c4, U = refactor_session({'t.sn': src})
        impl = lambda line, col: sorted((r['range']['start']['line'], r['range']['start']['character']) for r in
                                        c4.request('textDocument/implementation', {'textDocument': {'uri': U('t.sn')},
                                                                                    'position': {'line': line, 'character': col}}))
        assert impl(10, 11) == [(1, 8), (4, 8), (7, 8)], impl(10, 11)    # from the call
        assert impl(4, 9) == [(1, 8), (4, 8), (7, 8)], impl(4, 9)        # from an excluded declaration
        assert impl(9, 5) == [(9, 4)], impl(9, 5)                        # a single declaration is its own
        c4.request('shutdown', None); c4.notify('exit', None)
    check('implementation: per-target declarations from use, active and excluded declarations', implementation)

    def tooling_api():
        # Compiler tooling API (tooling-api.md): reference roles, rename
        # conflicts, top-level symbols with containers, per-source completeness.
        files = {'lib.sn': 'عام عرف حساب(): عدد { أرجع 1; }\nعام نوع لون = | أحمر | أخضر;\n',
                 'use.sn': 'استورد "lib.sn";\nعرف الرئيسية(): عدد {\n    ليكن س: متغير عدد = حساب();\n    س := س + 1;\n    ليكن ص: عدد = 2;\n    أرجع س + ص;\n}\n',
                 'broken.sn': 'استورد "lib.sn";\nعرف ب(): عدد { أرجع غير_معرف_هنا + حساب(); }\n',
                 'en.sn': 'def main(): int {\n    let a: mutable int = 1;\n    let b: int = 2;\n    return a + b;\n}\n'}
        ws = tempfile.mkdtemp(prefix='sultanc-analyzer-api-')
        for n, t in files.items():
            open(os.path.join(ws, n), 'w', encoding='utf-8').write(t)
        U = lambda n: 'file://' + os.path.join(ws, n)
        c6 = Client([server], cwd=home)
        c6.request('initialize', {'processId': None, 'rootUri': 'file://' + ws, 'workspaceFolders': [{'uri': 'file://' + ws, 'name': 'w'}], 'capabilities': {}})
        c6.notify('initialized', {})
        for n in ('lib.sn', 'use.sn', 'en.sn'):
            c6.notify('textDocument/didOpen', {'textDocument': {'uri': U(n), 'languageId': 'sultanc', 'version': 1, 'text': files[n]}})
        P = lambda n, l, ch: {'textDocument': {'uri': U(n)}, 'position': {'line': l, 'character': ch}}
        hl = [(h['range']['start']['line'], h['range']['start']['character'], h['kind'])
              for h in c6.request('textDocument/documentHighlight', P('use.sn', 2, 9))]
        assert hl == [(2, 9, 3), (3, 4, 3), (3, 9, 2), (5, 9, 2)], hl      # decl, write, read, read
        refs = c6.request('textDocument/references', {**P('lib.sn', 0, 8), 'context': {'includeDeclaration': True}})
        got = sorted((x['uri'].rsplit('/', 1)[1], x['range']['start']['line'], x['range']['start']['character']) for x in refs)
        # broken.sn has an unknown name: the compiler keeps every name of it
        # that resolved (e1d4bca), so its call is found, and the file is still
        # reported as incomplete.
        assert got == [('broken.sn', 1, 35), ('lib.sn', 0, 8), ('use.sn', 2, 24)], got
        time.sleep(0.3)
        notes = [n['params']['message'] for n in c6.notes if n.get('method') == 'window/showMessage']
        assert notes == ['قد تكون المراجع ناقصة: تعذر تحليل أسماء هذه الملفات: broken.sn'], notes
        def rename_error(*a):
            try:
                c6.request('textDocument/rename', {**P(*a[:3]), 'newName': a[3]})
            except RuntimeError as e:
                return str(e)
            return None
        assert "'الاسم معرف مسبقا في النطاق نفسه (use.sn:5:10)'" in rename_error('use.sn', 2, 9, 'ص')
        assert "'the name is already declared in the same scope (en.sn:3:9)'" in rename_error('en.sn', 1, 8, 'b')
        assert 'broken.sn' in rename_error('lib.sn', 0, 8, 'جديد')     # an importer could not be analysed
        syms = [(x['name'], x.get('containerName')) for x in c6.request('workspace/symbol', {'query': 'أحمر'})]
        assert syms == [('أحمر', 'لون')], syms
        c6.request('shutdown', None); c6.notify('exit', None)
    check('tooling API: reference roles, rename conflicts, containers, incomplete importers', tooling_api)

    def extract_function_and_imports():
        ar = 'عرف الرئيسية(): عدد {\n    ليكن أ: عدد = 2;\n    ليكن م: متغير عدد = 0;\n    ليكن ب: عدد = أ * 3;\n    م := م + ب;\n    أرجع م + ب;\n}\n'
        en = 'def main(): int {\n    let a: int = 2;\n    let b: int = a * 3 + 1;\n    return b;\n}\n'
        imp = 'from std.io import println, print;\nimport std.text.number;\n\ndef main(): int {\n    println("x");\n    return 0;\n}\n'
        c4, U = refactor_session({'ar.sn': ar, 'en.sn': en, 'imp.sn': imp})
        def extract(name, text, a, b):
            acts = c4.request('textDocument/codeAction', {'textDocument': {'uri': U(name)}, 'range': RANGE(a[0], a[1], b[0], b[1]),
                                                          'context': {'diagnostics': [], 'only': ['refactor.extract.function']}}, timeout=120)
            assert len(acts) == 1, acts
            return acts[0]['title'], apply_edits(text, acts[0]['edit']['changes'][U(name)])
        title, text = extract('ar.sn', ar, (3, 4), (4, 15))
        assert title == 'استخراج إلى دالة'
        assert text == ('عرف الرئيسية(): عدد {\n    ليكن أ: عدد = 2;\n    ليكن م: متغير عدد = 0;\n    ليكن ب: عدد = مستخرجة(أ, &متغير م);\n    أرجع م + ب;\n}\n\n'
                        'عرف مستخرجة(أ: عدد, م: &متغير عدد): عدد {\n    ليكن ب: عدد = أ * 3;\n    (*م) := (*م) + ب;\n    أرجع ب;\n}\n'), text
        title, text = extract('en.sn', en, (2, 17), (2, 26))
        assert title == 'Extract into function'
        assert text == ('def main(): int {\n    let a: int = 2;\n    let b: int = extracted(a);\n    return b;\n}\n\n'
                        'def extracted(a: int): int {\n    return a * 3 + 1;\n}\n'), text
        # A selection that is not whole statements nor one expression: no action.
        acts = c4.request('textDocument/codeAction', {'textDocument': {'uri': U('en.sn')}, 'range': RANGE(2, 10, 2, 20),
                                                      'context': {'diagnostics': [], 'only': ['refactor.extract.function']}}, timeout=120)
        assert acts == [], acts
        diags = c4.request('textDocument/diagnostic', {'textDocument': {'uri': U('imp.sn')}})['items']
        hints = [(d['range']['start']['line'], d['range']['start']['character'], d['range']['end']['character'], d['severity'], d['tags'])
                 for d in diags]
        assert hints == [(0, 28, 33, 4, [1]), (1, 0, 23, 4, [1])], hints      # `print`, the whole std.text.number import
        org = c4.request('textDocument/codeAction', {'textDocument': {'uri': U('imp.sn')}, 'range': RANGE(0, 0, 0, 0),
                                                     'context': {'diagnostics': [], 'only': ['source.organizeImports']}}, timeout=120)
        text = apply_edits(imp, org[0]['edit']['changes'][U('imp.sn')])
        assert text.startswith('from std.io import println;\n\ndef main()'), text
        c4.request('shutdown', None); c4.notify('exit', None)
    check('extract function (Arabic statements, English expression); unused import hints and organize', extract_function_and_imports)

    def type_hints_and_delta():
        src = ('import std.io.println;\nimport std.text.number;\n\ndef main(): int {\n'
               '    let values: vector int = [3, 9];\n    match first(&values) with\n'
               '    | option.some(found) -> { println(int_to_text(found)); }\n    | option.none -> { };\n    return 0;\n}\n'
               'def first(items: &vector int): option int {\n    return option.some((*items)[0]);\n}\n')
        c4, U = refactor_session({'h.sn': src})
        hints = c4.request('textDocument/inlayHint', {'textDocument': {'uri': U('h.sn')}, 'range': RANGE(0, 0, 20, 0)})
        types = [h for h in hints if h.get('kind') == 1]
        assert [(h['position']['line'], h['label']) for h in types] == [(6, ': int')], hints
        full = c4.request('textDocument/semanticTokens/full', {'textDocument': {'uri': U('h.sn')}})
        changed = src.replace('    return 0;\n}\ndef first', '    let extra: int = 1;\n    return extra;\n}\ndef first')
        c4.notify('textDocument/didChange', {'textDocument': {'uri': U('h.sn'), 'version': 2}, 'contentChanges': [{'text': changed}]})
        delta = c4.request('textDocument/semanticTokens/full/delta', {'textDocument': {'uri': U('h.sn')}, 'previousResultId': full['resultId']})
        fresh = c4.request('textDocument/semanticTokens/full', {'textDocument': {'uri': U('h.sn')}})
        data = list(full['data'])
        for e in sorted(delta['edits'], key=lambda e: e['start'], reverse=True):
            data[e['start']:e['start'] + e['deleteCount']] = e.get('data', [])
        assert delta['edits'] and data == fresh['data'], delta
        c4.request('shutdown', None); c4.notify('exit', None)
    check('type hints on pattern bindings; semantic tokens delta', type_hints_and_delta)

    def auto_import():
        t = 'import std.io.println;\n\ndef main(): int {\n    let s: string = int_to_\n    return 0;\n}\n'
        u = uri('auto.sn')
        c.notify('textDocument/didOpen', {'textDocument': {'uri': u, 'languageId': 'sultanc', 'version': 1, 'text': t}})
        items = c.request('textDocument/completion', {'textDocument': D(u), 'position': at(t, 'int_to_\n', 7)})
        auto = {i['label']: i['additionalTextEdits'][0] for i in items if 'additionalTextEdits' in i}
        assert 'int_to_text' in auto, list(auto)[:5]
        assert auto['int_to_text']['newText'] == 'import std.text.number;\n' and auto['int_to_text']['range']['start']['line'] == 1
    check('completion auto-imports std names', auto_import)

    def cancel_running_analysis():
        # A cold project analysis of compiler/ (462 files) takes about 4 s. The
        # reader thread cancels it mid-way: $/cancelRequest answers -32800, a
        # didChange of the same document answers -32801, both within about 1 s.
        # compiler/ is a subfolder of the checkout's Supax package, so its
        # imports resolve through the package graph: this needs supax.
        if not (os.environ.get('SUPAX') or shutil.which('supax')):
            print('skip cancellation of a running analysis: set SUPAX'); return
        root = os.path.join(home, 'compiler')
        path = os.path.join(root, 'frontend', 'parser', 'precedence.sn')
        text, u = open(path, encoding='utf-8').read(), 'file://' + path
        k = Client([server], cwd=home)
        k.request('initialize', {'processId': None, 'rootUri': 'file://' + root, 'capabilities': {},
                                 'workspaceFolders': [{'uri': 'file://' + root, 'name': 'compiler'}]})
        k.notify('initialized', {})
        k.notify('textDocument/didOpen', {'textDocument': {'uri': u, 'languageId': 'sultanc', 'version': 1, 'text': text}})
        params = {'textDocument': {'uri': u}, 'position': at(text, 'معلومة_العامل('), 'context': {'includeDeclaration': True}}
        ref = lambda i: {'jsonrpc': '2.0', 'id': i, 'method': 'textDocument/references', 'params': params}
        k.send(ref(901)); time.sleep(0.8)
        sent = time.time(); k.send({'jsonrpc': '2.0', 'method': '$/cancelRequest', 'params': {'id': 901}})
        r = k.responses([901], timeout=120)[901]
        assert r.get('error', {}).get('code') == -32800 and time.time() - sent < 2.0, (r, time.time() - sent)
        k.send(ref(902)); time.sleep(0.8)
        sent = time.time()
        k.notify('textDocument/didChange', {'textDocument': {'uri': u, 'version': 2}, 'contentChanges': [{'text': text + '\n'}]})
        r = k.responses([902], timeout=120)[902]
        assert r.get('error', {}).get('code') == -32801 and time.time() - sent < 2.0, (r, time.time() - sent)
        r = k.request('textDocument/references', params, timeout=300)
        files = sorted({x['uri'].rsplit('/', 1)[1] for x in r})
        assert files == ['expressions.sn', 'precedence.sn'], files
        k.request('shutdown', None); k.notify('exit', None)
    check('cancellation stops a running project analysis (-32800, -32801)', cancel_running_analysis)

    def flycheck():
        # Check on save (rust-analyzer's flycheck): `sultanc check` of the
        # folder's main.sn runs at start and after each save, on a thread; its
        # diagnostics are published for the files that are not open, each in
        # its file's language, at the compiler's UTF-16 positions.
        from urllib.parse import unquote
        ws = tempfile.mkdtemp(prefix='sultanc-analyzer-flycheck-')
        files = {'main.sn': 'import "util.sn";\nimport "ar.sn";\n\ndef main(): int {\n    return helper() + مساعد();\n}\n',
                 'util.sn': 'public def helper(): int {\n    return yy;\n}\n',
                 'ar.sn': 'عام عرف مساعد(): عدد {\n    أرجع غغ;\n}\n'}
        for n, t in files.items():
            open(os.path.join(ws, n), 'w', encoding='utf-8').write(t)
        U = lambda n: 'file://' + os.path.join(ws, n)
        def start(options):
            k = Client([server], cwd=home)
            k.request('initialize', {'processId': None, 'rootUri': 'file://' + ws, 'capabilities': {'textDocument': {'diagnostic': {}}},
                                     'workspaceFolders': [{'uri': 'file://' + ws, 'name': 'ws'}], 'initializationOptions': options})
            k.notify('initialized', {})
            return k
        def published(k, name):
            path = os.path.join(ws, name)
            return [n['params']['diagnostics'] for n in k.notes if n.get('method') == 'textDocument/publishDiagnostics'
                    and unquote(n['params']['uri'][len('file://'):]) == path]
        def wait(k, cond, what):
            end = time.time() + 60
            while time.time() < end:
                if cond(): return
                time.sleep(0.1)
            raise AssertionError(what + ': ' + json.dumps([n for n in k.notes if n.get('method') != 'textDocument/publishDiagnostics' or True][-6:], ensure_ascii=False))
        logs = lambda k: [n['params']['message'] for n in k.notes if n.get('method') == 'window/logMessage']
        k = start({})
        k.notify('textDocument/didOpen', {'textDocument': {'uri': U('main.sn'), 'languageId': 'sultanc', 'version': 1, 'text': files['main.sn']}})
        wait(k, lambda: published(k, 'util.sn') and published(k, 'ar.sn'), 'first check')
        assert published(k, 'util.sn')[-1] == [{'range': RANGE(1, 11, 1, 13), 'severity': 1, 'code': 'SULTANC-NAME-UNKNOWN', 'source': 'SultanC',
                                                'message': 'unknown name: `yy` — The required name was not found during resolution.'}], published(k, 'util.sn')
        assert published(k, 'ar.sn')[-1] == [{'range': RANGE(1, 9, 1, 11), 'severity': 1, 'code': 'SULTANC-NAME-UNKNOWN', 'source': 'SultanC',
                                              'message': 'الاسم `غغ` غير معروف — الاسم المطلوب مفقود أثناء حل المراجع.'}], published(k, 'ar.sn')
        # The open file keeps its live diagnostics only.
        assert published(k, 'main.sn') == [], published(k, 'main.sn')
        assert any(m.startswith('check on save: ') and m.endswith(' check ' + os.path.join(ws, 'main.sn')) for m in logs(k)), logs(k)
        # Opening a file drops its check diagnostics; closing brings them back.
        n = len(published(k, 'util.sn'))
        k.notify('textDocument/didOpen', {'textDocument': {'uri': U('util.sn'), 'languageId': 'sultanc', 'version': 1, 'text': files['util.sn']}})
        wait(k, lambda: len(published(k, 'util.sn')) > n, 'open')
        assert published(k, 'util.sn')[-1] == [], published(k, 'util.sn')
        n = len(published(k, 'util.sn'))
        k.notify('textDocument/didClose', {'textDocument': {'uri': U('util.sn')}})
        wait(k, lambda: len(published(k, 'util.sn')) >= n + 2, 'close')
        assert published(k, 'util.sn')[-1][0]['code'] == 'SULTANC-NAME-UNKNOWN', published(k, 'util.sn')
        # Fixed on disk, then a save: the next check clears util.sn.
        open(os.path.join(ws, 'util.sn'), 'w', encoding='utf-8').write('public def helper(): int {\n    return 1;\n}\n')
        k.notify('textDocument/didSave', {'textDocument': {'uri': U('main.sn')}})
        wait(k, lambda: published(k, 'util.sn')[-1] == [], 'save')
        assert published(k, 'ar.sn')[-1][0]['code'] == 'SULTANC-NAME-UNKNOWN', published(k, 'ar.sn')
        k.request('shutdown', None); k.notify('exit', None)
        open(os.path.join(ws, 'util.sn'), 'w', encoding='utf-8').write(files['util.sn'])
        # checkOnSave: false runs nothing; checkEntries names the entry.
        k = start({'checkOnSave': False})
        k.notify('textDocument/didSave', {'textDocument': {'uri': U('main.sn')}})
        time.sleep(2)
        assert published(k, 'util.sn') == [] and not any(m.startswith('check on save') for m in logs(k)), k.notes
        k.request('shutdown', None); k.notify('exit', None)
        os.rename(os.path.join(ws, 'main.sn'), os.path.join(ws, 'app.sn'))
        k = start({})
        time.sleep(1)
        assert 'check on save: no entry file (src/main.sn or main.sn); set "sultanc.check.entries"' in logs(k), logs(k)
        k.request('shutdown', None); k.notify('exit', None)
        k = start({'checkEntries': ['app.sn']})
        wait(k, lambda: published(k, 'util.sn'), 'checkEntries')
        k.request('shutdown', None); k.notify('exit', None)
    check('check on save (flycheck): unopened files, Arabic and English, open/close, save, settings', flycheck)

    def code_lens():
        # Run lens above each test (compiler test discovery); references lens
        # (lensReferences) resolved from the compiler's references, titles in
        # the document's language.
        ws = tempfile.mkdtemp(prefix='sultanc-analyzer-lens-')
        files = {'lens.sn': 'import std.debug.assert;\n\ndef double(x: int): int { return x * 2; }\n\ndef main(): int { return double(2) + double(3) - 10; }\n\n@@test\ndef doubles(): void { assert(double(2) == 4); }\n',
                 'lens_ar.sn': 'استورد المكتبة.تنقيح.تحقق;\n\nعرف ضعف(س: عدد): عدد { أرجع س * 2; }\n\n@@اختبار\nعرف يضاعف(): فراغ { تحقق(ضعف(2) == 4); }\n'}
        U = lambda n: 'file://' + os.path.join(ws, n)
        def start(options):
            k = Client([server], cwd=home)
            k.request('initialize', {'processId': None, 'rootUri': 'file://' + ws, 'workspaceFolders': [{'uri': 'file://' + ws, 'name': 'w'}],
                                     'capabilities': {}, 'initializationOptions': dict(options, checkOnSave=False)})
            k.notify('initialized', {})
            for n, t in files.items():
                open(os.path.join(ws, n), 'w', encoding='utf-8').write(t)
                k.notify('textDocument/didOpen', {'textDocument': {'uri': U(n), 'languageId': 'sultanc', 'version': 1, 'text': t}})
            return k
        P = lambda l, ch: {'line': l, 'character': ch}
        k = start({})
        assert k.request('textDocument/codeLens', {'textDocument': {'uri': U('lens.sn')}}) == [
            {'range': RANGE(4, 4, 4, 4), 'command': {'title': '▶︎ Run', 'command': 'sultanc.runFile', 'arguments': [U('lens.sn')]}},
            {'range': RANGE(4, 4, 4, 4), 'command': {'title': 'Debug', 'command': 'sultanc.debugFile', 'arguments': [U('lens.sn')]}},
            {'range': RANGE(7, 4, 7, 4), 'command': {'title': '▶︎ Run Test', 'command': 'sultanc.runTest', 'arguments': [U('lens.sn'), 'doubles']}},
            {'range': RANGE(7, 4, 7, 4), 'command': {'title': 'Debug', 'command': 'sultanc.debugTest', 'arguments': [U('lens.sn'), 'doubles']}}]
        k.request('shutdown', None); k.notify('exit', None)
        k = start({'lensReferences': True})
        lenses = k.request('textDocument/codeLens', {'textDocument': {'uri': U('lens.sn')}})
        refs = [l for l in lenses if 'data' in l]
        # double and main; not the test.
        assert [l['range']['start'] for l in refs] == [P(2, 4), P(4, 4)], lenses
        r = k.request('codeLens/resolve', refs[0])
        assert r['range'] == refs[0]['range'] and r['data'] == refs[0]['data'], r
        assert r['command']['title'] == '3 references' and r['command']['command'] == 'sultanc.showReferences', r
        uri, pos, locs = r['command']['arguments']
        assert uri == U('lens.sn') and pos == P(2, 4), r
        assert sorted((x['range']['start']['line'], x['range']['start']['character']) for x in locs) == [(4, 25), (4, 37), (7, 29)], locs
        assert k.request('codeLens/resolve', refs[1])['command'] == {'title': '0 references', 'command': ''}
        ar = k.request('textDocument/codeLens', {'textDocument': {'uri': U('lens_ar.sn')}})
        ar = [l for l in ar if 'command' not in l or not l['command']['command'].endswith('File')]
        assert ar[0] == {'range': RANGE(5, 4, 5, 4), 'command': {'title': '▶︎ تشغيل الاختبار', 'command': 'sultanc.runTest', 'arguments': [U('lens_ar.sn'), 'يضاعف']}}, ar
        assert ar[1] == {'range': RANGE(5, 4, 5, 4), 'command': {'title': 'تصحيح الأخطاء', 'command': 'sultanc.debugTest', 'arguments': [U('lens_ar.sn'), 'يضاعف']}}, ar
        assert k.request('codeLens/resolve', ar[2])['command']['title'] == 'مرجع واحد', ar
        k.request('shutdown', None); k.notify('exit', None)
        k = start({'lensRun': False})
        assert k.request('textDocument/codeLens', {'textDocument': {'uri': U('lens.sn')}}) == []
        k.request('shutdown', None); k.notify('exit', None)
    check('code lens: run test (en, ar), references count resolved, settings', code_lens)

    def entry_lens_ar():
        # The entry is the compiler's رمز_بدء_البرنامج (الرئيسية), only in the
        # file that declares it.
        ws = tempfile.mkdtemp(prefix='sultanc-analyzer-entry-')
        files = {'رئيسي.sn': 'استورد "مساعد.sn";\n\nعرف الرئيسية(): عدد {\n    أرجع واحد();\n}\n',
                 'مساعد.sn': 'عام عرف واحد(): عدد { أرجع 1; }\n'}
        k = Client([server], cwd=home)
        k.request('initialize', {'processId': None, 'rootUri': 'file://' + ws, 'workspaceFolders': [{'uri': 'file://' + ws, 'name': 'w'}],
                                 'capabilities': {}, 'initializationOptions': {'checkOnSave': False}})
        k.notify('initialized', {})
        U = lambda n: 'file://' + os.path.join(ws, n)
        for n, t in files.items():
            open(os.path.join(ws, n), 'w', encoding='utf-8').write(t)
            k.notify('textDocument/didOpen', {'textDocument': {'uri': U(n), 'languageId': 'sultanc', 'version': 1, 'text': t}})
        lenses = k.request('textDocument/codeLens', {'textDocument': {'uri': U('رئيسي.sn')}})
        assert lenses == [
            {'range': RANGE(2, 4, 2, 4), 'command': {'title': '▶︎ تشغيل', 'command': 'sultanc.runFile', 'arguments': [U('رئيسي.sn')]}},
            {'range': RANGE(2, 4, 2, 4), 'command': {'title': 'تصحيح الأخطاء', 'command': 'sultanc.debugFile', 'arguments': [U('رئيسي.sn')]}}], lenses
        assert k.request('textDocument/codeLens', {'textDocument': {'uri': U('مساعد.sn')}}) == []
        k.request('shutdown', None); k.notify('exit', None)
    check('code lens: Run / Debug above the entry (ar), not in other files', entry_lens_ar)

    def hover_bidi_isolates():
        # bidiIsolates: each hover line that starts in Arabic is wrapped in
        # RLI … PDI (U+2067, U+2069), so the signature reads right to left in
        # a left-to-right hover; English lines are unchanged.
        k = Client([server], cwd=home)
        k.request('initialize', {'processId': None, 'rootUri': 'file://' + work, 'workspaceFolders': [{'uri': 'file://' + work, 'name': 'w'}],
                                 'capabilities': {}, 'initializationOptions': {'checkOnSave': False, 'bidiIsolates': True}})
        k.notify('initialized', {})
        k.notify('textDocument/didOpen', {'textDocument': {'uri': AR, 'languageId': 'sultanc', 'version': 1, 'text': ar_text}})
        k.notify('textDocument/didOpen', {'textDocument': {'uri': EN, 'languageId': 'sultanc', 'version': 1, 'text': en_text}})
        value = k.request('textDocument/hover', {'textDocument': {'uri': AR}, 'position': at(ar_text, 'الأكبر(الأعداد')})['contents']['value']
        lines = value.split('\n')
        assert lines[0] == '```sultanc' and lines[2] == '```', lines
        assert lines[1] == '\u2067عرف الأكبر(الأول: عدد, الثاني: عدد): عدد\u2069', lines
        assert lines[6] == '\u2067**الصنف:** دالة\u2069  ', lines
        assert lines[3] == '' and lines[4] == '---', lines
        en = k.request('textDocument/hover', {'textDocument': {'uri': EN}, 'position': at(en_text, 'area(')})['contents']['value']
        assert '\u2067' not in en and en.startswith('```sultanc\ndef area(shape: Shape): int\n```'), en
        k.request('shutdown', None); k.notify('exit', None)
    check('hover: Arabic lines isolated right to left with bidiIsolates; English unchanged', hover_bidi_isolates)

    def import_links_and_file_rename():
        # documentLink and definition on an import are the compiler's import
        # edges (علاقات_استيراد_واجهة); willRenameFiles rewrites the importers'
        # import statements at the edges' ranges.
        ws = tempfile.mkdtemp(prefix='sultanc-analyzer-links-')
        os.makedirs(os.path.join(ws, 'lib'))
        files = {'main.sn': 'import "shapes.sn";\nimport lib.geo;\nimport std.text.number;\n\ndef main(): int { return side() + corner(); }\n',
                 'shapes.sn': 'public def side(): int { return 1; }\n',
                 'lib/geo.sn': 'public def corner(): int { return 2; }\n'}
        U = lambda n: 'file://' + os.path.join(ws, n)
        for n, t in files.items():
            open(os.path.join(ws, n), 'w', encoding='utf-8').write(t)
        k = Client([server], cwd=home)
        k.request('initialize', {'processId': None, 'rootUri': 'file://' + ws, 'workspaceFolders': [{'uri': 'file://' + ws, 'name': 'w'}],
                                 'capabilities': {}, 'initializationOptions': {'checkOnSave': False}})
        k.notify('initialized', {})
        k.notify('textDocument/didOpen', {'textDocument': {'uri': U('main.sn'), 'languageId': 'sultanc', 'version': 1, 'text': files['main.sn']}})
        links = k.request('textDocument/documentLink', {'textDocument': {'uri': U('main.sn')}})
        got = [(l['range']['start']['line'], l['range']['start']['character'], l['range']['end']['character'], l['target'].split('/')[-3:]) for l in links]
        # The link covers the path inside the quotes.
        assert got[0][:3] == (0, 8, 17) and links[0]['target'] == U('shapes.sn'), links
        assert got[1][:3] == (1, 7, 14) and links[1]['target'] == U('lib/geo.sn'), links
        # Layered std: std.text.number lives in library/alloc.
        assert got[2][:3] == (2, 7, 22) and links[2]['target'].endswith('/library/alloc/text/number.sn'), links
        d = k.request('textDocument/definition', {'textDocument': {'uri': U('main.sn')}, 'position': {'line': 2, 'character': 12}})
        d = d[0] if isinstance(d, list) else d
        assert (d.get('uri') or d.get('targetUri')).endswith('/library/alloc/text/number.sn'), d
        rename = lambda a, b: k.request('workspace/willRenameFiles', {'files': [{'oldUri': U(a), 'newUri': U(b)}]})
        assert rename('shapes.sn', 'geometry.sn') == {'changes': {U('main.sn'): [{'range': RANGE(0, 8, 0, 17), 'newText': 'geometry.sn'}]}}
        assert rename('shapes.sn', 'lib/shapes.sn') == {'changes': {U('main.sn'): [{'range': RANGE(0, 8, 0, 17), 'newText': 'lib/shapes.sn'}]}}
        assert rename('lib/geo.sn', 'lib/geometry.sn') == {'changes': {U('main.sn'): [{'range': RANGE(1, 7, 1, 14), 'newText': 'lib.geometry'}]}}
        # A dotted import moved to another folder names a different module: no edit.
        assert rename('lib/geo.sn', 'geo.sn') is None
        k.request('shutdown', None); k.notify('exit', None)
    check('import links and willRenameFiles from the compiler\'s import edges', import_links_and_file_rename)

    def on_type_formatting_and_brace_hints():
        # onTypeFormatting: `;` formats its line, `}` the block it closes, with
        # the compiler's range formatter. Closing brace hints after long
        # declarations (closingBraceHintsMinLines), in the document's language.
        ws = tempfile.mkdtemp(prefix='sultanc-analyzer-ontype-')
        t = 'def helper(): int {\n    return 1;\n}\n\ndef main(): int {\nlet x:int=1;\n        return x;\n}\n'
        ar = 'نوع نقطة = {\n    س: عدد,\n    ص: عدد\n};\n\nعرف الرئيسية(): عدد {\n    ليكن أ: عدد = 1;\n    أرجع أ;\n}\n'
        k = Client([server], cwd=home)
        k.request('initialize', {'processId': None, 'rootUri': None, 'capabilities': {},
                                 'initializationOptions': {'checkOnSave': False, 'closingBraceHintsMinLines': 4}})
        k.notify('initialized', {})
        for n, text in (('f.sn', t), ('ar.sn', ar)):
            open(os.path.join(ws, n), 'w', encoding='utf-8').write(text)
            k.notify('textDocument/didOpen', {'textDocument': {'uri': 'file://' + os.path.join(ws, n), 'languageId': 'sultanc', 'version': 1, 'text': text}})
        u = 'file://' + os.path.join(ws, 'f.sn')
        o = {'tabSize': 4, 'insertSpaces': True}
        edits = k.request('textDocument/onTypeFormatting', {'textDocument': {'uri': u}, 'position': {'line': 5, 'character': 12}, 'ch': ';', 'options': o})
        assert edits == [{'range': RANGE(4, 17, 5, 0), 'newText': '\n    '}, {'range': RANGE(5, 6, 5, 6), 'newText': ' '},
                         {'range': RANGE(5, 9, 5, 9), 'newText': ' '}, {'range': RANGE(5, 10, 5, 10), 'newText': ' '},
                         {'range': RANGE(5, 12, 6, 8), 'newText': '\n    '}], edits
        block = k.request('textDocument/onTypeFormatting', {'textDocument': {'uri': u}, 'position': {'line': 7, 'character': 1}, 'ch': '}', 'options': o})
        assert block == edits, block
        assert k.request('textDocument/onTypeFormatting', {'textDocument': {'uri': u}, 'position': {'line': 2, 'character': 1}, 'ch': '}', 'options': o}) == []
        hints = lambda name, lines: [h for h in k.request('textDocument/inlayHint', {'textDocument': {'uri': 'file://' + os.path.join(ws, name)}, 'range': RANGE(0, 0, lines, 0)})
                                     if h['label'].startswith('// ')]
        assert hints('f.sn', 9) == [{'position': {'line': 7, 'character': 1}, 'label': '// def main', 'paddingLeft': True}], hints('f.sn', 9)
        assert hints('ar.sn', 10) == [{'position': {'line': 3, 'character': 2}, 'label': '// نوع نقطة', 'paddingLeft': True},
                                      {'position': {'line': 8, 'character': 1}, 'label': '// عرف الرئيسية', 'paddingLeft': True}], hints('ar.sn', 10)
        k.request('shutdown', None); k.notify('exit', None)
    check('on-type formatting (; and }) and closing brace hints (en, ar)', on_type_formatting_and_brace_hints)

    def completion_contexts():
        # The compiler's completion contexts (ssf): any receiver before `.`,
        # builtin constructors, Type positions, record fields, match arms,
        # call arguments ranked by the expected Type.
        ws = tempfile.mkdtemp(prefix='sultanc-analyzer-contexts-')
        base = ('type Inner = { depth: int, label: string };\ntype Outer = { inner: Inner, count: int };\n'
                'type Color = | Red | Green;\ntype Shape = | Circle of int | Dot;\n\n'
                'def area(width: int, height: int): int { return width * height; }\n'
                'def make(): Outer { return { inner: { depth: 1, label: "a" }, count: 2 }; }\n\n'
                'def main(): int {\n    let outer_value: Outer = make();\n    let r: &Outer = &outer_value;\n'
                '    let arr: vector Outer = [make()];\n    let name: string = "x";\n    let top: int = 1;\n'
                '    let c: Color = Color.Red();\n    let sh: Shape = Shape.Dot();\n    @@\n    return 0;\n}\n')
        k = Client([server], cwd=home)
        k.request('initialize', {'processId': None, 'rootUri': None, 'capabilities': {}, 'initializationOptions': {'checkOnSave': False}})
        k.notify('initialized', {})
        def items(n, typed):
            text = base.replace('@@', typed)
            path = os.path.join(ws, n)
            open(path, 'w', encoding='utf-8').write(text)
            k.notify('textDocument/didOpen', {'textDocument': {'uri': 'file://' + path, 'languageId': 'sultanc', 'version': 1, 'text': text}})
            lines = text.split('\n')
            line = max(i for i, l in enumerate(lines) if l.endswith(typed.split('\n')[-1]))
            reply = k.request('textDocument/completion', {'textDocument': {'uri': 'file://' + path}, 'position': {'line': line, 'character': len(lines[line])}})
            got = reply['items'] if isinstance(reply, dict) else reply
            return sorted(got, key=lambda x: x['sortText'])
        pairs = lambda got: [(x['label'], x['kind']) for x in got]
        assert pairs(items('c1.sn', 'let z: int = make().')) == [('count', 5), ('inner', 5)]
        assert pairs(items('c2.sn', 'let z: int = make().inner.')) == [('depth', 5), ('label', 5)]
        assert pairs(items('c3.sn', 'let z: int = (*r).')) == [('count', 5), ('inner', 5)]
        assert pairs(items('c4.sn', 'let z: int = arr[0].')) == [('count', 5), ('inner', 5)]
        assert pairs(items('c5.sn', 'let o: option int = option.')) == [('none', 20), ('some', 20)]
        types = pairs(items('c6.sn', 'let x: '))
        assert types[:3] == [('Color', 13), ('Inner', 22), ('Outer', 22)] and ('int', 22) in types, types
        assert not any(label in ('top', 'outer_value', 'main', 'area') for label, _ in types), types
        fields = items('c7.sn', 'let o: Inner = { ')
        assert [(x['label'], x['textEdit']['newText']) for x in fields] == [('depth', 'depth: '), ('label', 'label: ')], fields
        assert [x['label'] for x in items('c7b.sn', 'let o: Inner = { depth: 1, ')] == ['label']
        assert pairs(items('c8.sn', 'match c with\n    | ')) == [('Color.Green', 20), ('Color.Red', 20)]
        assert pairs(items('c8b.sn', 'match sh with\n    | ')) == [('Shape.Circle(_)', 20), ('Shape.Dot', 20)]
        # E3: a constructor in a value position is a call; in a pattern, its name.
        edits = lambda got: [(x['label'], x['textEdit']['newText']) for x in got]
        assert edits(items('e3a.sn', 'let d: Color = Color.')) == [('Green', 'Green()'), ('Red', 'Red()')]
        assert edits(items('e3b.sn', 'let s: Shape = Shape.')) == [('Circle', 'Circle('), ('Dot', 'Dot()')]
        assert edits(items('e3c.sn', 'let o: option int = option.')) == [('none', 'none()'), ('some', 'some(')]
        assert edits(items('e3d.sn', 'match c with\n    | ')) == [('Color.Green', 'Color.Green'), ('Color.Red', 'Color.Red')]
        args = items('c9.sn', 'let z: int = area(')
        assert args[0]['label'] == 'top' and args[0]['sortText'].startswith('0'), [(x['label'], x['sortText']) for x in args[:4]]
        assert all(not x['sortText'].startswith('0') for x in args if x['label'] in ('outer_value', 'name', 'arr')), args
        # E1: `Color.Red` without `()` is SULTANC-NAME-CONSTRUCTOR-NOT-CALLED,
        # and its quick fix writes the `()`.
        text = base.replace('@@', 'let d: Color = Color.Red;')
        path = os.path.join(ws, 'e1.sn')
        open(path, 'w', encoding='utf-8').write(text)
        k.notify('textDocument/didOpen', {'textDocument': {'uri': 'file://' + path, 'languageId': 'sultanc', 'version': 1, 'text': text}})
        line = text.split('\n').index('    let d: Color = Color.Red;')
        diagnostics = k.request('textDocument/diagnostic', {'textDocument': {'uri': 'file://' + path}})['items']
        found = [d for d in diagnostics if d['code'] == 'SULTANC-NAME-CONSTRUCTOR-NOT-CALLED']
        assert len(found) == 1 and found[0]['range'] == RANGE(line, 19, line, 28), diagnostics
        assert found[0]['message'] == 'constructor `Color.Red` is called with `()`: `Color.Red()`', found
        actions = k.request('textDocument/codeAction', {'textDocument': {'uri': 'file://' + path}, 'range': found[0]['range'], 'context': {'diagnostics': found}})
        fixes = [a for a in actions if a.get('kind') == 'quickfix']
        assert fixes and fixes[0]['edit']['changes']['file://' + path] == [{'range': RANGE(line, 28, line, 28), 'newText': '()'}], actions
        k.request('shutdown', None); k.notify('exit', None)
    check('completion contexts: receivers, option., Type positions, record fields, match arms, call arguments', completion_contexts)

    c.request('shutdown', None); c.notify('exit', None)
    failed = [r for r in RESULTS if not r[0]]
    for ok, name, err in RESULTS:
        print(('ok   ' if ok else 'FAIL ') + name + (f'\n       {err}' if err else ''))
    print(f'\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
