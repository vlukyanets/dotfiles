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
entries too.

`go` carries `delve` alongside it: the Go debugger, and what `nvim-dap`
and VS Code's Go extension drive, has no version-manager story to worry
about, so it's just a second package in the same entry.

`kotlin` is a plain leaf on top of `jdk`: the `kotlin` package is only the
compiler (`kotlinc`), so `gradle` — the build tool practically every
Kotlin project assumes — goes in the same entry. Both run on whatever
`development.jdk` installed; enabling `kotlin` without it just leaves
`kotlinc` failing to find a JVM. This is also what backs
[`ide.neovim`](ide/neovim.md)'s `kotlin_language_server`.

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

These exist mainly to give [`ide.neovim`](ide/neovim.md)'s `clangd`,
`jdtls`, and `omnisharp` language servers a compiler/runtime to run
against — `gcc`/`clang` (plus `make`) also happen to be what compiles
`nvim-treesitter`'s parsers and `telescope-fzf-native.nvim`'s native
module. A host with `ide.neovim.enabled` but one of these unset just gets
that language's LSP server failing to start, not an install-time error.

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
hyper-lin uses it yet.

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
