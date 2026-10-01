# Spec: `packages` — installing from the repositories

Status: approved 2026-09-24, narrowed 2026-09-28. Module of the
[capability map](CAPABILITY-MAP.md); depends on `engine`.

## Objective

Make `Pacman`, `ArchLinuxOs`'s package manager, a package backend:
`install()` takes every package a feature lists from the repositories, in one transaction, after removing the
installed packages they replace. pacman's own configuration is the
`packaging` feature (`SPEC-features`); the AUR is out until a feature
brings it back.

User stories:

- `packages()` of a feature says `["docker", "docker-buildx"]`; the first
  apply on a fresh Arch installs both.
- A feature that installs `pipewire-jack` says it replaces `jack2`; on a
  machine with `jack2` the swap happens in the same apply, where
  `--noconfirm` alone would refuse it.
- A package that is not in the repositories fails the install, naming it,
  before anything changes.

## Tech Stack

Stdlib only (`re`, `subprocess`); pacman on the machine.

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
   databases; any other name fails with `not in the repositories: a b`
   before anything is installed. `-Si` knows package names only, not what
   they provide, so a feature lists real names.
3. **Download.** `pacman -Sw --needed --noconfirm …`, as root, retried:
   the network part. Failure after the retries: `pacman -Sw failed; if
   downloads returned 404 the sync databases are stale: run pacman -Syu
   and apply again`.
4. **Install.** `pacman -S --needed --noconfirm …`, as root, once, one
   transaction from the cache: a conflict fails the same every time, so it
   is not retried.

`apply` re-checks `missing` afterwards, so a failed install blocks only
the features that list a package still missing.

## Project Structure

```
dotfiles/platforms/arch/_pacman.py     Pacman: missing, install, direct, provides, upgrade
dotfiles/platforms/package_manager.py  PackageManager: install(names, replaces), upgrade, depends
dotfiles/feature.py                    Feature.replaces()
dotfiles/plan.py                       Step.replaces
dotfiles/apply.py                      passes them to install
tests/test_platforms.py                install and depends against a fake pacman
tests/test_apply.py                    replaces reach install, only when something is missing
```

## Testing Strategy

- Every command through a fake shell (`execute` and `root`), answers from a dict.
- A replaced package removed only when installed under its own name,
  before the install; one `pacman -Sw` and one `pacman -S` with every
  name; a name outside the repositories fails after `-Si` only; the 404
  hint when the download fails; a failed install is not retried.

## Boundaries

- **Always:** check before mutating; root only through `shell.as_root`; every
  network step retried.
- **Never:** `pacman -Sy` without `-u`; removing a package no feature
  says it replaces.

## Decisions

1. **Where a package comes from is pacman's answer** (`-Si`), not a list
   kept by hand.
2. **A replaced package is named by the feature** that installs its
   replacement (`replaces()`) and removed with `pacman -Rdd` just before the
   install, rather than left to pacman's undocumented `--ask` answers.
3. **No setup in the platform** (2026-09-28): pacman and makepkg are the
   `packaging` feature, the mirrorlist the `reflector` one; the AUR, paru and rustup went with the
   features that used them.
