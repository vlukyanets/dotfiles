# Spec: `packages` — pacman ready, repositories and the AUR

Status: approved 2026-09-24. Module of the [capability map](CAPABILITY-MAP.md);
depends on `engine`.

## Objective

Make `Arch` a complete package backend: `setup()` prepares pacman (its
options, multilib, the build flags of local packages, fresh mirrors) before
anything is installed, and `install()` takes every package from wherever
it lives, the repositories or the AUR. A strategy lists its packages by
name, repository and AUR alike, and the installed packages they replace.

User stories:

- `packages()` of a strategy says `["docker", "docker-buildx"]` or
  `["clock-rs-git"]`; the first apply on a fresh Arch installs both,
  building paru first when an AUR package needs it.
- A strategy that installs `pipewire-jack` says it replaces `jack2`; on a
  machine with `jack2` the swap happens in the same apply, where
  `--noconfirm` alone would refuse it.
- A host with `features.aur` off never builds anything from the AUR: an
  AUR package fails its feature with a message naming the package and the
  switch.
- A change to `features.reflector` refreshes the mirrorlist in the same
  apply, before the packages are downloaded.

## Tech Stack

Stdlib only (`os.cpu_count`, `tempfile`, `re`); pacman, makepkg, git,
paru, reflector and systemd on the machine. No new dependency.

## `Arch.setup()` — before any install

Runs on every apply; each part checks first and is gated by its feature,
read from `self.cfg`. In this order, the first failure stopping the rest
(`error: platform: …`, nothing is installed this apply):

1. **pacman** (`features.pacman`)
   - `/etc/pacman.conf.d/options.conf`: `ParallelDownloads = N`.
   - `Include = /etc/pacman.conf.d/options.conf` in `/etc/pacman.conf`,
     inserted before the first repository section: options after it would
     be ignored. The only edit to `pacman.conf` besides multilib's line.
   - `multilib = true`, and `pacman.conf` has no `[multilib]` section of
     its own: `/etc/pacman.conf.d/multilib.conf` (`[multilib]`, `Include =
     /etc/pacman.d/mirrorlist`) and its `Include` line appended to
     `pacman.conf`. While `/var/lib/pacman/sync/multilib.db` does not
     exist: `pacman -Syu --noconfirm`, as root, retried. A full upgrade,
     not `-Sy`, which followed by `-S` is a partial upgrade; keyed on the
     database, so a sync the network cut off is redone next time.
2. **makepkg** (`features.makepkg`) —
   `/etc/makepkg.conf.d/dotfiles.conf`:
   ```
   MAKEFLAGS="-j4"
   OPTIONS+=(ccache !debug)
   PACKAGER="Valentin Lukyanets <valikluks95@gmail.com>"
   ```
   `jobs = "20%"` is that share of `os.cpu_count()`, at least 1; any other
   value (`"4"`, `"$(nproc)"`) is written verbatim and evaluated by
   makepkg at every build. `OPTIONS+=` only when `options` is not empty.
3. **reflector** (`features.reflector`)
   - `reflector` installed (through `install`, the one package setup
     installs).
   - `/etc/xdg/reflector/reflector.conf`: `--save
     /etc/pacman.d/mirrorlist`, then `--country` (only when not empty),
     `--protocol`, `--latest`, `--sort`, `--age`, `--completion-percent`,
     `--download-timeout`, one per line.
   - `/etc/systemd/system/reflector.timer.d/override.conf`: `OnCalendar`
     and `OnBootSec`, each reset first; `systemctl daemon-reload` when it
     changed.
   - `ensure_service("reflector.timer")`.
   - Any of these changed: `systemctl start reflector.service`, as root.
     Its failure is a notice, not an error: the old mirrorlist stays and
     the timer tries again.

Every file is `root:root`, mode 644, written with `ensure_file`, so a dry
run prints what would change and writes nothing.

## Replaced packages

```python
class Tools(Feature):
    class Arch:
        def packages(self):
            return ["ffmpeg", "pipewire-jack", ...]

        def replaces(self):
            return ["jack2"]  # conflicts with pipewire-jack; ffmpeg would pull it otherwise
```

`Platform.replaces()` returns `[]`, like `packages()`. The runner collects
every enabled strategy's `replaces()` into `Step.replaces` and passes their
union to `install(names, replaces)`, which runs only when something is
missing. A replaced package conflicts with its replacement, so the two are
never installed together and removing it matters only while the
replacement is being installed.

## `Arch.install(names, replaces)` — repositories, then the AUR

1. **Replaced.** Each of `replaces` installed under exactly that name
   (`pacman -Qq` also answers for a package that only provides the name,
   `rustup` for `rust`) is removed with `pacman -Rdd --noconfirm`, as root:
   `-> removed jack2, its replacement follows`. Its dependents stay
   unsatisfied until the install below provides the name again.
2. **Split.** `pacman -Si` (no root) answers for the names in the sync
   databases; those are repository packages, the rest are taken as AUR
   packages. `-Si` knows package names only, not what they provide, so a
   strategy lists real names (`rust`, not `cargo`).
3. **Repositories.** `pacman -S --needed --noconfirm …`, as root,
   retried, one transaction. Failure after the retries:
   `pacman -S failed; if downloads returned 404 the sync databases are
   stale: run pacman -Syu and apply again`.
4. **AUR.** With `features.aur` off: `not in the repositories: a b —
   enable features.aur to build them from the AUR`, after the repository
   packages are installed. Otherwise `ensure_paru()`, then
   `paru -S --needed --noconfirm …` as the user, retried; paru calls sudo
   itself, with `--sudo` and `--sudoflags` taken from `SUDO_CMD` and the
   snapper variables, so a test's `SUDO_CMD=false` holds for it too.

`apply` re-checks `missing` afterwards, so a failed AUR package blocks
only the features that list it.

### `Arch.ensure_paru()`

paru runs (`paru --version` prints a version: a paru left behind by a
libalpm bump no longer does) → nothing. Otherwise, in a temp dir:

1. `git clone --depth 1 https://aur.archlinux.org/paru.git`, retried.
2. Its `.SRCINFO` gives `depends` and `makedepends` (version constraints
   dropped); `install(missing(...))` for those, so root goes through
   `as_root` as everywhere else. `cargo` is satisfied by `rustup` when it
   is installed, otherwise pacman picks `rust`. A rustup with no default
   toolchain gets `rustup default stable` (retried): cargo does not run
   without one, and the feature that sets it runs only after the packages.
3. `makepkg --noconfirm` as the user, `makepkg --packagelist` for the
   files, `pacman -U --noconfirm <files>` as root.
4. `-> paru built from the AUR`.

`features.aur` is also a feature, `features/aur.py`: its `Arch` strategy
has no packages, and its `apply` calls `strategy.ensure_paru()`, so an
enabled AUR has a working paru even when no feature needs an AUR package.

## Project Structure

```
dotfiles/platforms/arch.py   Arch: setup (pacman, makepkg, reflector), install, ensure_paru
dotfiles/features/aur.py     class Aur(Feature), an Arch strategy that ensures paru
dotfiles/platforms/__init__.py  Platform.replaces(), install(names, replaces)
dotfiles/apply.py            Step.replaces, passed to install
dotfiles/defaults.toml       comments of features.pacman / makepkg / reflector / aur
tests/test_platforms.py      setup, install and ensure_paru against a fake pacman
tests/test_apply.py          replaces reach install, only when something is missing
```

## Commands

```
uv run --isolated --group dev pytest tests/test_platforms.py
uv run --exact dotfiles apply --dry-run     # on hyper-lin: setup's files and the missing packages, no sudo
```

## Code Style

As in `engine`. Setup reads like the file it writes:

```python
def _makepkg(self) -> None:
    makepkg = self.cfg["features"]["makepkg"]
    lines = [f'MAKEFLAGS="-j{_jobs(makepkg["jobs"])}"']
    if makepkg["options"]:
        lines.append(f"OPTIONS+=({' '.join(makepkg['options'])})")
    git = self.cfg["git"]
    lines.append(f'PACKAGER="{git["name"]} <{git["email"]}>"')
    ensure_file("/etc/makepkg.conf.d/dotfiles.conf", "\n".join(lines) + "\n", owner="root:root")
```

## Testing Strategy

- `SYSROOT` in a temp dir with a `pacman.conf` of `[options]` and `[core]`;
  every command through the fake `_run`, answers from a dict.
- pacman: the `Include` lands before `[core]`; a second setup changes
  nothing; a `[multilib]` in `pacman.conf` is left alone; `-Syu` runs
  only while `multilib.db` is missing.
- makepkg: `"20%"` of a patched `cpu_count`, never below 1; `"$(nproc)"`
  verbatim; no `OPTIONS+=` for an empty list.
- reflector: `daemon-reload` only when the override changed; a failed
  `start` is a notice and setup goes on; nothing started when nothing
  changed.
- install: a replaced package removed only when installed under its own
  name, before the install; one `pacman -S` with the repository names only; AUR
  names through paru with `--sudo false`; AUR names with `features.aur`
  off fail after the repository install; the 404 hint on failure.
- ensure_paru: nothing when `paru --version` answers; otherwise clone,
  `.SRCINFO` dependencies installed, makepkg, `pacman -U` as root, in
  that order.
- Every setup part off: no command runs.

## Boundaries

- **Always:** check before mutating; root only through `as_root` (and
  paru's own sudo, which is `SUDO_CMD`); every network step retried.
- **Ask first:** editing `pacman.conf` beyond the two `Include` lines; a
  second AUR helper; an automatic `-Syu` outside enabling multilib.
- **Never:** `pacman -Sy` without `-u`; removing a package no strategy
  says it replaces; building anything from the AUR with `features.aur`
  off.

## Success Criteria

1. hyper-lin's `dotfiles apply --dry-run` lists setup's files and the
   missing packages and runs no sudo; a second real apply prints nothing.
2. A conflicting package is swapped in one apply, named once, in the
   strategy that installs its replacement.
3. A strategy lists AUR and repository packages alike.
4. pytest, ruff and `dotfiles check` are green.

## Decisions

1. **Setup is part of the platform**, not features: it must finish before
   the one install, which the package graph cannot order.
2. **Where a package comes from is pacman's answer** (`-Si`), not a list
   kept by hand.
3. **A replaced package is named by the strategy** that installs its
   replacement (`replaces()`) and removed with `pacman -Rdd` just before the
   install, rather than left to pacman's undocumented `--ask` answers.
4. **paru is built on demand**: by `install` when an AUR package is
   missing, by the `aur` feature otherwise.
5. **Enabling multilib runs `pacman -Syu` once**, as the Arch wiki asks
   after enabling a repository.
