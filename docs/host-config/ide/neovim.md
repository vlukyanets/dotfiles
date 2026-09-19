# Neovim

[`dot_config/nvim/init.lua.tmpl`](../../../dot_config/nvim/init.lua.tmpl) has
exactly one templated value — `vim.g.have_nerd_font`, from
[`fonts.nerd_font`](../fonts.md) — everything else is host-independent.
`.chezmoiignore.tmpl` skips `~/.config/nvim` entirely on a host that leaves
`ide.neovim.enabled` unset — see [IDE](../ide.md).

It's a single-file config in the [kickstart.nvim](https://github.com/nvim-lua/kickstart.nvim)
style — no plugin distro (LazyVim/NvChad) underneath it, just
[lazy.nvim](https://github.com/folke/lazy.nvim) bootstrapped directly and a
flat list of plugins, meant to be read top to bottom and edited in place
rather than configured through some framework's own options layer.

## LSP servers

Language servers are installed by [Mason](https://github.com/mason-org/mason.nvim)
(`mason-tool-installer.nvim`'s `ensure_installed`, built from the `servers`
table in `init.lua`) the first time Neovim starts — not by pacman, so
adding a language means editing that table, not `ide.neovim.packages`.
Currently configured:

| Language     | Server                    |
| ------------ | ------------------------- |
| C / C++      | `clangd`                  |
| Go           | `gopls`                   |
| Python       | `pyright` + `ruff`        |
| Rust         | `rust_analyzer`           |
| JS/TS        | `ts_ls`                   |
| Bash         | `bashls`                  |
| C#           | `omnisharp`               |
| Kotlin       | `kotlin_language_server`  |
| Java         | `jdtls`                   |
| Lua          | `lua_ls`                  |

Java and Kotlin get bare-minimum setups (diagnostics, completion, go-to-definition)
— no project-aware extras like `nvim-jdtls`'s test runner/debug integration.
`jdtls` also needs a per-project workspace directory, which `init.lua` derives
from the current working directory's name under `stdpath('cache')`.

## System packages

`ide.neovim.packages` itself is the editor, its plugin manager's hard
dependency on the `git` binary, and `tree-sitter-cli`:

```toml
[hyper-lin.ide.neovim]
enabled = true
packages = ["neovim", "git", "tree-sitter-cli"]
```

`tree-sitter-cli` is there for [nvim-treesitter](https://github.com/nvim-treesitter/nvim-treesitter)'s
`main` branch, which `init.lua` pins explicitly: it's a from-scratch
rewrite for Neovim 0.12+ (the old `master` is frozen for 0.11) that
builds every parser through the `tree-sitter` binary — 0.26.1 or later,
from the distro's package rather than npm. The config shape changed with
it: no `require('nvim-treesitter.configs').setup { highlight = … }` —
parsers come from `require('nvim-treesitter').install { … }` (a no-op
once present, `:TSUpdate` on plugin update), and highlighting is
Neovim's own `vim.treesitter.start()`, which `init.lua` calls from a
`FileType` autocmd for every buffer that has a parser (plus the plugin's
`indentexpr`), leaving the rest on regex highlighting.

Everything else a fully-working LSP setup needs lives in other entries
instead, each one already justified for its own reasons and just
happening to double as a Neovim dependency:

| Needed for                                             | Comes from                                    |
| ------------------------------------------------------ | ---------------------------------------------- |
| `unzip` (most Mason installs extract a zip)             | [`cli_tools.enabled`](../cli-tools.md)         |
| `rg`/`fd` (Telescope's `live_grep`/`find_files`)        | [`cli_tools.enabled`](../cli-tools.md)         |
| a C/C++ compiler + `make` (treesitter parsers, telescope-fzf-native, `clangd`) | [`development.cpp.gcc`/`development.cpp.clang`](../development.md) |
| a JVM for `jdtls` to run on                             | [`development.jdk`](../development.md)         |
| `kotlinc`/`gradle` for `kotlin_language_server` to resolve a project | [`development.kotlin`](../development.md) |
| a .NET runtime for `omnisharp` to run on                | [`development.dotnet`](../development.md)      |
| `npm` (`pyright`, `ts_ls`, `bashls` are npm packages)   | [`development.fnm`](../development.md#node-via-fnm) |

None of these are enforced by the install script — a host with
`ide.neovim.enabled` but one of the above unset still gets a working
Neovim, just with that specific piece missing (a language server that
won't start, or a Telescope picker that errors) instead of a failure at
apply time.
