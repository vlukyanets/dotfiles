# Development

[`.chezmoiscripts/run_once_before_24-configure-development.sh.tmpl`](../../.chezmoiscripts/run_once_before_24-configure-development.sh.tmpl)
installs whatever's listed under `development.<name>` with `enabled = true`
(default `{}` — no entries, script exits immediately), the same
`enabled`/`source`/`packages` shape as [Office](office.md), plus one more
field, `post_install` (see below). `<name>` is just a label, not read
anywhere except log output — pick anything, e.g. `"uv"`, `"fnm"`, `"go"`,
`"rustup"`.

A `<name>` can also be a group instead of a leaf: one more level of
nesting, `development.<name>.<subname>`, each `<subname>` its own leaf
with the same fields. The script tells the two apart structurally (does
this entry have a `packages` key, or does it just contain more entries?)
rather than by name, so this works for any `<name>`, not just the one
below. Use it when a language has more than one competing toolchain worth
toggling independently — `development.cpp.gcc`/`development.cpp.clang` —
a plain leaf is for anything with just one obvious choice.

`source` is one of:

- `"pacman"` (default) — installed with `pacman -S --needed`.
- `"aur"` — installed with `paru -S --needed` instead. Requires
  `pkg-mgmt.aur.enabled = true` on this host (see [AUR/paru](aur.md)) — the
  script exits with an error if it isn't, rather than silently falling back
  to pacman.

Each entry's own `packages` list (default `[]` — enabling an entry with none
listed just errors out on pacman/paru's own "no targets specified") is
installed with its own single call. A language and its package manager go
in the same entry's `packages` when they ship as separate packages, since
they're installed together anyway.

## Version managers over system packages

`uv`, `fnm`, and `rustup` are all the same idea: a single pacman package
that is itself a version manager, not a fixed runtime/compiler version —
preferred here over a plain `python`/`nodejs` entry so a project can pin
whatever version it actually needs instead of whatever Arch's rolling
repos happen to ship today. `go` is the one exception: left as a plain
`go` package, since `GOTOOLCHAIN=auto` (Go 1.21+) already has the `go`
command itself download and use whatever toolchain a project's `go.mod`
asks for, with no separate manager needed.

`cpp`, `jdk`, and `dotnet` follow `go`'s pattern rather than `uv`/`fnm`'s —
C/C++, Java, and .NET don't have an equivalent single-binary version
manager in the Arch repos worth preferring over the plain toolchain, so
these are just `pacman -S`-installed under an `enabled` flag like any
other entry here. `cpp` is the one that's a group, not a leaf — `gcc` and
`clang` are two competing compilers, each toggled independently:

```toml
[hyper-lin.development.cpp.gcc]
enabled = true
packages = ["gcc", "gdb", "make", "cmake", "meson", "ninja", "cppcheck"]

[hyper-lin.development.cpp.clang]
enabled = true
packages = ["clang", "lldb", "lld", "llvm", "make", "cmake", "meson", "ninja", "cppcheck"]

[hyper-lin.development.jdk]
enabled = true
packages = ["jdk-openjdk"]

[hyper-lin.development.dotnet]
enabled = true
packages = ["dotnet-sdk"]
```

`make`/`cmake`/`meson`/`ninja` go in both `cpp` entries — which build
system a given C/C++ project uses is independent of which compiler it's
built with, and each entry installs its own packages independently, so
neither one alone is a complete C/C++ setup without the other's build
tools duplicated in. The debugger is the opposite case and follows its
compiler: `gdb` with `gcc`, `lldb` with `clang` (plus `lld`, LLVM's
linker, which `clang -fuse-ld=lld` needs) — either debugger can load the
other compiler's DWARF output, but each tracks its own toolchain's
extensions first, so pairing them is the setup that just works. `llvm`
rounds the clang side out with the rest of the toolchain (`llvm-objdump`,
`llvm-ar`, `llvm-symbolizer`, `opt`…) that `clang` alone doesn't pull in.

`cppcheck` is compiler-agnostic like the build tools and goes in both
entries too. Compilation caching isn't a `cpp` package at all — see
`sccache` below.

`go` carries `delve` alongside it: the Go debugger, and what `nvim-dap`
and VS Code's Go extension drive, has no version-manager story to worry
about, so it's just a second package in the same entry.

`kotlin` is a plain leaf on top of `jdk`: the `kotlin` package is only the
compiler (`kotlinc`), so `gradle` — the build tool practically every
Kotlin project assumes — goes in the same entry. Both run on whatever
`development.jdk` installed; enabling `kotlin` without it just leaves
`kotlinc` failing to find a JVM. This is also what backs
[`ide.neovim`](ide/neovim.md)'s `kotlin_language_server`.

These exist mainly to give [`ide.neovim`](ide/neovim.md)'s `clangd`,
`jdtls`, and `omnisharp` language servers a compiler/runtime to run
against — `gcc`/`clang` (plus `make`) also happen to be what compiles
`nvim-treesitter`'s parsers and `telescope-fzf-native.nvim`'s native
module. A host with `ide.neovim.enabled` but one of these unset just gets
that language's LSP server failing to start, not an install-time error.

### `sqlite` and `desktop_only`

`sqlite` (the `sqlite3` CLI and library) and `sqlitebrowser` (DB Browser
for SQLite, a Qt GUI over the same files) are two entries rather than one
`packages` list, because they don't belong on the same hosts: the CLI is
wanted everywhere, the GUI only where there's a desktop to draw it on.
That's what `desktop_only` (default `false`) is for — an entry with it set
is skipped, with a log line rather than an error, on any host whose
[`desktop.enabled`](desktop.md) is false, and its `post_install` doesn't
run either. It's a generic field, not sqlite-specific: any GUI companion
to a CLI tool fits the same shape.

```toml
[hyper-lin.development.sqlite]
enabled = true
packages = ["sqlite"]

[hyper-lin.development.sqlitebrowser]
enabled = true
packages = ["sqlitebrowser"]
desktop_only = true
```

### Tracing, and `groups`

`tracing` is its own entry rather than part of `cpp`: `strace`/`ltrace`
trace syscalls and library calls of any binary, `perf` samples anything
with symbols, and `valgrind` instruments native code whichever compiler
produced it — none of them care which toolchain, or language, is on the
other side.

```toml
[hyper-lin.development.tracing]
enabled = true
packages = ["valgrind", "strace", "ltrace", "perf"]
```

Every entry also takes `groups` (default `[]`): a list of system groups
the applying user is added to right after the entry installs, with the
same already-a-member check as [`containers.docker`](containers.md) so
re-applying is a no-op, and the same caveat that a fresh add only takes
effect in a new login session. It's skipped along with everything else
when `desktop_only` skips the entry. Nothing under `development` on
hyper-lin uses it yet — the shape is shared with
[Network tools](network-tools.md), where `wireshark` does.

### `sccache`

[sccache](https://github.com/mozilla/sccache) is its own entry,
`development.sccache`, rather than a package inside `rustup` or `cpp.*`,
because one cache serves both: it wraps `rustc` for cargo and
`gcc`/`clang` for C/C++ builds. It's what this repo uses instead of
ccache — ccache only knows C-family compilers, and sccache covers those
too, at the cost of one difference in how it's wired in: ccache ships a
directory of compiler-named symlinks to put first on `PATH`, sccache
can't masquerade like that and has to be named as a *launcher* wherever
the build system looks for one. So:

- **Rust**: [`dot_cargo/config.toml.tmpl`](../../dot_cargo/config.toml.tmpl)
  becomes `~/.cargo/config.toml` with `[build] rustc-wrapper = "sccache"`.
  Note cargo's incremental compilation (on by default in the `dev`
  profile) is not cacheable, so sccache mostly speeds up dependency
  crates and clean/release builds, not edit-compile loops on your own
  crate.
- **C/C++ via CMake**: [`dot_zshrc.tmpl`](../../dot_zshrc.tmpl) exports
  `CMAKE_C_COMPILER_LAUNCHER=sccache` and `CMAKE_CXX_COMPILER_LAUNCHER=sccache`
  behind `command -v sccache`; CMake picks those up at first configure.
- **meson / plain make**: no global hook — `CC="sccache gcc" CXX="sccache
  g++"` on the command line when wanted.

Both dotfiles are gated in [`.chezmoiignore.tmpl`](../../.chezmoiignore.tmpl)
the same way, with no `enabled` flag of their own: it walks every
`development` leaf and group member and writes them exactly when an
enabled one lists `"sccache"` in its `packages`. A `rustc-wrapper`
pointing at a binary that isn't installed would break every cargo build,
which is why the cargo config in particular can't just be unconditional.

#### sccache config

[`dot_config/sccache/config.tmpl`](../../dot_config/sccache/config.tmpl)
becomes `~/.config/sccache/config` (same gate), filled from
`[<host>.sccache]`. Anything left unset there is omitted from the file,
so sccache's own defaults apply:

| field                        | config key                             | default                          |
| ---------------------------- | -------------------------------------- | -------------------------------- |
| `cache_size`                 | `[cache.disk] size`                    | `""` → sccache's 10G             |
| `cache_dir`                  | `[cache.disk] dir`                     | `""` → `~/.cache/sccache`        |
| `preprocessor_cache_mode.*`  | `[cache.disk.preprocessor_cache_mode]` | `{}` → nothing written           |

`cache_size` takes a `K`/`M`/`G`/`T` suffix (base 1024) and goes into
the file as that string — sccache's docs show `size` as a byte count,
but its parser accepts the same suffixed form as `SCCACHE_CACHE_SIZE`.
`cache_dir` may start with `~/` — the template expands it, because
sccache takes the path literally (its docs list `dir` as required, but
the field has a default in the code, so it's simply left out when
unset).

`preprocessor_cache_mode` is the C/C++-only mode (gcc/clang, local cache)
that skips re-running the preprocessor and tracks included headers
instead — the counterpart of ccache's direct mode, and where the
equivalents of ccache's `sloppiness` live (`ignore_time_macros`,
`skip_system_headers`, `file_stat_matches`…). Its keys are copied through
verbatim rather than given per-key defaults, because three of them
default to `true` upstream and Go template's `default` can't tell an
explicit `false` from unset (the same trap
[ssh-hardening.md](ssh-hardening.md) describes). The keys and sccache's
defaults are listed in [`.hosts.toml`](../../.hosts.toml)'s field
reference; hyper-lin sets none of them, only the cap:

```toml
[hyper-lin.development.sccache]
enabled = true
packages = ["sccache"]

[hyper-lin.sccache]
cache_size = "20G"
```

### Python via `uv`

No plain `python`/`python-pip` entry here — [`uv`](https://github.com/astral-sh/uv)
manages its own Python interpreters and per-project virtualenvs, so
there's nothing else to install for Python development specifically.
Anything else that hard-depends on a system Python still pulls it in as
an ordinary pacman dependency regardless — this entry is only about what
you want on hand for writing Python yourself.

Its `post_install` is `uv python install --default`: with no version
argument, `uv` fetches the latest stable CPython (so the entry never needs
bumping when a new minor lands), and `--default` also links it as plain
`python`/`python3` under `~/.local/bin` — already on `PATH` via
[`dot_zshrc.tmpl`](../../dot_zshrc.tmpl) — so an ad-hoc `python` outside
any project resolves to uv's interpreter rather than whatever Arch's
`python` package happens to be, if it's even installed.

### Node via `fnm`

No plain `nodejs`/`npm` entry either — [`fnm`](https://github.com/Schniz/fnm)
installs and switches between Node versions per project instead. See
`post_install` below for how it ends up with a usable default `node` and
`pnpm` (installed with `npm install -g` inside fnm's own Node via `fnm
exec --using`, rather than Arch's `pnpm` package, which would drag a
system `nodejs` in next to fnm's); the per-directory auto-switching hook (`eval "$(fnm env --use-on-cd)"`) is
wired into [`dot_zshrc.tmpl`](../../dot_zshrc.tmpl), gated on
`development.fnm.enabled` — see [Shell](shell.md).

## `post_install`

A package that's a toolchain *manager* rather than a ready-to-use
runtime — `rustup`, `fnm` — doesn't give you a working compiler/runtime
right after `pacman -S`; something still has to pick a version. `<name>`'s
`post_install` (default `""` — nothing runs) is a shell command run once,
right after that entry's packages install, for exactly that:

```toml
[hyper-lin.development.rustup]
enabled = true
packages = ["rustup"]
post_install = "rustup default stable"

[hyper-lin.development.fnm]
enabled = true
packages = ["fnm"]
post_install = "fnm install --lts && fnm default lts-latest && fnm exec --using=lts-latest -- npm install -g pnpm"

[hyper-lin.development.uv]
enabled = true
packages = ["uv"]
post_install = "uv python install --default"
```

It's a plain string run as-is (not quoted/escaped further), so it can be
a `&&` chain like `fnm`'s above — same trust level as every other host
config value in this repo that ends up interpolated straight into a
script body (e.g. `packages`, `settings` elsewhere).

hyper-lin's config:

```toml
[hyper-lin.development.uv]
enabled = true
packages = ["uv"]
post_install = "uv python install --default"

[hyper-lin.development.fnm]
enabled = true
packages = ["fnm"]
post_install = "fnm install --lts && fnm default lts-latest && fnm exec --using=lts-latest -- npm install -g pnpm"

[hyper-lin.development.go]
enabled = true
packages = ["go", "delve"]

[hyper-lin.development.rustup]
enabled = true
packages = ["rustup"]
post_install = "rustup default stable"

[hyper-lin.development.sccache]
enabled = true
packages = ["sccache"]

[hyper-lin.development.gh]
enabled = true
packages = ["github-cli"]

[hyper-lin.development.cpp.gcc]
enabled = true
packages = ["gcc", "gdb", "make", "cmake", "meson", "ninja", "cppcheck"]

[hyper-lin.development.cpp.clang]
enabled = true
packages = ["clang", "lldb", "lld", "llvm", "make", "cmake", "meson", "ninja", "cppcheck"]

[hyper-lin.development.jdk]
enabled = true
packages = ["jdk-openjdk"]

[hyper-lin.development.dotnet]
enabled = true
packages = ["dotnet-sdk"]

[hyper-lin.development.kotlin]
enabled = true
packages = ["kotlin", "gradle"]

[hyper-lin.development.sqlite]
enabled = true
packages = ["sqlite"]

[hyper-lin.development.sqlitebrowser]
enabled = true
packages = ["sqlitebrowser"]
desktop_only = true

[hyper-lin.development.tracing]
enabled = true
packages = ["valgrind", "strace", "ltrace", "perf"]
```

## `gh` and its config

`development.gh` and `development.go` are the entries with a dotfile
riding on their `enabled` flag, the same way [`ide.vscode`](ide/vscode.md)'s
config does. For `gh`:
[`dot_config/gh/config.yml`](../../dot_config/gh/config.yml) is only
written when the entry is enabled (gated in
[`.chezmoiignore.tmpl`](../../.chezmoiignore.tmpl)). It sets
`git_protocol: ssh` and a `co` → `pr checkout` alias, and leaves
`editor`/`pager` blank so they fall through to `$EDITOR`/`$PAGER`. Two
things to know: `gh config set` rewrites the file and strips comments, so
changes go in the chezmoi source and get re-applied; and `hosts.yml` next
to it — where `gh auth login` stores tokens — is deliberately not managed.

For `go`: [`dot_config/go/env.tmpl`](../../dot_config/go/env.tmpl) is the
file the `go` command reads on its own (`GOENV`, what `go env -w` writes
to), so it holds in any shell, hooked or not. It moves `GOPATH` to
`~/.local/share/go` — `GOMODCACHE` follows as `<GOPATH>/pkg/mod` — and
points `GOBIN` at `~/.local/bin`, which is already on `PATH`; without it
Go's default `GOPATH` is `~/go`, and the first `go install` (Mason
fetching `gopls`, say) plants a visible `go/` directory in `$HOME`. An
existing `~/go` is only a module cache plus installed binaries, safe to
delete once the file is in place. Same caveat as `gh`: `go env -w`
rewrites the file without its comments.
