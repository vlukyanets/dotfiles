# Spec: `packages` — installing from the repositories and the AUR

Status: approved. Module of the [capability map](CAPABILITY-MAP.md);
depends on `engine`.

## Objective

Make `Pacman`, `ArchLinuxOs`'s package manager, a package backend:
`install()` takes every package a feature lists from the repositories,
in one transaction, after removing the installed packages they replace,
and leaves the rest to `build()`: the AUR, built by makepkg as the user
and installed by pacman as root. pacman's own configuration is the
`packaging` feature (`SPEC-features`).

User stories:

- `packages()` of a feature says `["docker", "docker-buildx"]`; the first
  apply on a fresh Arch installs both.
- A feature that installs `pipewire-jack` says it replaces `jack2`; on a
  machine with `jack2` the swap happens in the same apply, where
  `--noconfirm` alone would refuse it.
- `packages()` says `["claude-code"]`, which only the AUR has: it is
  built as the user and installed through the root process at the
  feature's turn, after the features it requires.
- A package neither the repositories nor the AUR have fails its feature,
  naming it.

## Tech Stack

Stdlib only (`re`, `subprocess`, `json`, `urllib.parse`); pacman,
makepkg, git and curl on the machine (curl comes with pacman).

## Replaced packages

```python
class Tools(Feature):  # platforms/arch/features/tools.py
    def packages(self):
        return ["ffmpeg", "pipewire-jack", ...]

    def replaces(self):
        return ["jack2"]  # conflicts with pipewire-jack; ffmpeg would pull it otherwise
```

`Feature.replaces()` returns `[]`, like `packages()`. The runner collects
every enabled feature's `replaces()` into `Step.replaces` and passes their
union to `install(names, replaces)`, which runs only when something is
missing. A replaced package conflicts with its replacement, so the two are
never installed together and removing it matters only while the
replacement is being installed.

## `Pacman.install(names, replaces)`

1. **Replaced.** Each of `replaces` installed under exactly that name
   (`pacman -Qq` also answers for a package that only provides the name)
   is removed with `pacman -Rdd --noconfirm`, as root: `-> removed jack2,
   its replacement follows`.
2. **Known.** `pacman -Si` (no root) answers for the names in the sync
   databases; the others are returned, for `build()`. `-Si` knows package
   names only, not what they provide, so a feature lists real names.
3. **Download.** `pacman -Sw --needed --noconfirm …`, as root, retried:
   the network part. Failure after the retries: `pacman -Sw failed; if
   downloads returned 404 the sync databases are stale: run pacman -Syu
   and apply again`.
4. **Install.** `pacman -S --needed --noconfirm …`, as root, once, one
   transaction from the cache: a conflict fails the same every time, so it
   is not retried.

`apply` re-checks `missing` afterwards, so a failed install blocks only
the features that list a package still missing.

## `Pacman.build(names)`: the AUR (`arch/_aur.py`)

`apply` calls it at the turn of the feature that lists the names install()
returned, just before its `apply()`, so what the feature requires has run
(`paru` builds with rustup's toolchain set). A failure fails that feature.
The base `PackageManager.build` fails with `not in the repositories: a b`.

1. **As root** it fails at once: makepkg refuses root.
2. **Resolve.** The AUR RPC (`curl -fsSL
   https://aur.archlinux.org/rpc/v5/info?arg[]=…`, retried) gives each
   package's `PackageBase`, `Depends` and `MakeDepends`; a name it does
   not have fails with `not in the repositories nor the AUR: a b`.
   `pacman -T` drops what is installed (versions and provides included);
   a missing one that `pacman -Sp --print-format %n` finds is a
   repository dependency, any other an AUR one, resolved the same way.
   AUR packages needing each other fail. No `CheckDepends`: no `check()`.
3. **Repository side.** `base-devel` and `git` if missing, then the
   repository dependencies with `--asdeps`, through `sync()`: `-Sw`
   retried, `-S` once, as root.
4. **Build, as the user,** each package base once, dependencies first, in
   `~/.cache/dotfiles/aur/<pkgbase>` (not `/tmp`, whose tmpfs may be too
   small), kept between builds so nothing is downloaded twice: `git clone
   --depth 1` of `https://aur.archlinux.org/<pkgbase>.git` the first time,
   then `git fetch --depth 1` and `git reset --hard FETCH_HEAD`; a
   directory without `.git` (a clone cut off) is cloned again. makepkg
   keeps a source file already there that passes its checksum. The
   packages of earlier builds are deleted first; their sources stay.
   `makepkg --noconfirm --force --cleanbuild --clean --nocheck`, retried;
   no `-s`, which would call sudo itself.
5. **Install, as root:** of the files `makepkg --packagelist` lists and
   that exist, the ones whose `pacman -Qqp` name was wanted, with
   `pacman -U --noconfirm`, `--asdeps` for those only needed by others.
   No `--needed`: a package of the same version is installed again, the
   point of building one that stopped working. `-> a b built from the
   AUR` per package base.

## Project Structure

```
dotfiles/platforms/arch/_pacman.py     Pacman: missing, install, build, sync, direct, provides, upgrade
dotfiles/platforms/arch/_aur.py        Aur: resolve, build as the user, install as root
dotfiles/platforms/package_manager.py  PackageManager: setup, install(names, replaces), build, upgrade, depends
dotfiles/feature.py                    Feature.replaces()
dotfiles/plan.py                       Step.replaces
dotfiles/apply.py                      passes them to install
tests/test_platforms.py                install, build and depends against a fake pacman
tests/test_apply.py                    replaces reach install, only when something is missing
```

## Testing Strategy

- Every command through a fake shell (`execute` and `root`), answers from a dict.
- A replaced package removed only when installed under its own name,
  before the install; one `pacman -Sw` and one `pacman -S` with every
  name; a name outside the repositories returned, not installed; the 404
  hint when the download fails; a failed install is not retried.
- AUR: the repository dependency synced `--asdeps`, the AUR dependency
  cloned, built without sudo and installed `--asdeps` before the package
  that needs it; a second build fetches into the same directory, keeps
  the sources and deletes the old packages; a name the AUR lacks fails;
  as root nothing runs.
- apply: a feature's AUR package built at its turn, after the feature it
  requires, and not again once installed.

## Boundaries

- **Always:** check before mutating; root only through `shell.as_root`; every
  network step retried.
- **Never:** `pacman -Sy` without `-u`; removing a package no feature
  says it replaces.

## Decisions

1. **Where a package comes from is pacman's answer** (`-Si`), not a list
   kept by hand: what the repositories lack is the AUR's.
2. **A replaced package is named by the feature** that installs its
   replacement (`replaces()`) and removed with `pacman -Rdd` just before the
   install, rather than left to pacman's undocumented `--ask` answers.
3. **No setup in the platform.** pacman and makepkg are the
   `packaging` feature, the mirrorlist the `reflector` one; the AUR,
   paru and rustup went with the features that used them, and came back
   as the `paru` and `rustup` features.
4. **The AUR without an AUR helper.** makepkg builds as the
   user, the root process installs, so nothing but `pacman` asks for
   root and a password is asked at most once. paru, or `makepkg -si`,
   would call sudo themselves. A feature's AUR packages are built at its
   turn rather than with the repositories' transaction, after what it
   requires; the AUR is never one transaction anyway.
