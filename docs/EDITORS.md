# Using sultanc-analyzer outside VS Code

`sultanc-analyzer` is a standard Language Server Protocol server over stdio, so any
editor with an LSP client can use it. VS Code users should install the SultanC
extension instead (it finds the installed server and adds the RTL editor, Run/Check/Build, debugging and the Test Explorer).

## 1. Install the server

Install it into the SultanC toolchain, next to the compiler ([README](../README.md#install)):

```sh
sultanc-analyzer/tools/install.sh /path/to/sultanc     # writes ~/.supax/bin/sultanc-analyzer
```

`~/.supax/bin` is on `PATH` after Supax's installer, so every setup below starts
`sultanc-analyzer` by name. The server finds its standard library next to itself
(`~/.supax/lib/sultanc/library`), so the editor can start it from any directory.

Settings are sent as `initializationOptions`; the full list is in
[CONFIGURATION.md](CONFIGURATION.md). Commonly used:

| key | values | meaning |
|---|---|---|
| `language` | `auto` (default), `ar`, `en` | language of diagnostics, hover and CodeLens |
| `checkOnSave` | `true` (default), `false` | compiler diagnostics for unopened files after each save |

## Neovim 0.11+

`~/.config/nvim/init.lua`:

```lua
vim.filetype.add({ extension = { sn = 'sultanc' } })

vim.lsp.config('sultanc', {
  cmd = { 'sultanc-analyzer' },
  filetypes = { 'sultanc' },
  root_markers = { 'Supax.toml', '.git' },
  init_options = { language = 'auto' },
})
vim.lsp.enable('sultanc')
```

Highlighting comes from the server's semantic tokens (Neovim 0.9+). For
tree-sitter highlighting, folds and text objects use the plugin in
`sultanc-language-support/editors/neovim` (`require('sultanc').setup({ home = ... })`
also sets up this server). Useful keys: `K` hover, `gd` definition, `grn` rename,
`gra` code actions, `grr` references, `]d` next diagnostic.

Neovim 0.10 with nvim-lspconfig:

```lua
local configs = require('lspconfig.configs')
configs.sultanc = { default_config = {
  cmd = { 'sultanc-analyzer' },
  filetypes = { 'sultanc' },
  root_dir = require('lspconfig.util').root_pattern('Supax.toml', '.git'),
  init_options = { language = 'auto' },
} }
require('lspconfig').sultanc.setup({})
```

## Helix

`~/.config/helix/languages.toml`:

```toml
[language-server.sultanc-analyzer]
command = "sultanc-analyzer"
config = { language = "auto" }

[[language]]
name = "sultanc"
scope = "source.sultanc"
file-types = ["sn"]
roots = ["Supax.toml"]
comment-token = "//"
indent = { tab-width = 4, unit = "    " }
language-servers = ["sultanc-analyzer"]
```

Helix does not use LSP semantic tokens; colours, indentation and text objects
come from the tree-sitter grammar. `sultanc-language-support/editors/helix`
has the full `languages.toml` (with the `[[grammar]]` entry) and the queries.

## Emacs (eglot, Emacs 29+)

```elisp
(define-derived-mode sultanc-mode prog-mode "SultanC"
  (setq-local comment-start "// "))
(add-to-list 'auto-mode-alist '("\\.sn\\'" . sultanc-mode))
(with-eval-after-load 'eglot
  (add-to-list 'eglot-server-programs
               '(sultanc-mode . ("sultanc-analyzer"))))
(add-hook 'sultanc-mode-hook #'eglot-ensure)
```

For right-to-left Arabic lines, Emacs's bidirectional display works as is
(`bidi-paragraph-direction` nil).

## Sublime Text (LSP package)

`Preferences > Package Settings > LSP > Settings`:

```json
{
  "clients": {
    "sultanc": {
      "enabled": true,
      "command": ["sultanc-analyzer"],
      "selector": "source.sultanc",
      "initializationOptions": { "language": "auto" }
    }
  }
}
```

Sublime Text can use the TextMate grammar from
`sultanc-language-support/grammars/sultanc.tmLanguage.json` for colours (save
it as a `.tmLanguage` or convert it with PackageDev).

## Zed

Install `sultanc-language-support/editors/zed` as a dev extension
(`zed: install dev extension`). It brings the tree-sitter grammar and starts
this server from `SULTANC_HOME`; see that directory's README.

## Checking the server by hand

```sh
sultanc-analyzer/tests/run.sh
```

See [TESTING.md](TESTING.md).
