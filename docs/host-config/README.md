# How host config works

Machines are declared once in **[`.hosts.toml`](../../.hosts.toml)**,
keyed by hostname:

```toml
[hyper-lin]
```

The name deliberately avoids chezmoi's own `.chezmoidata` prefix. A file
named that way gets auto-merged into *every* template's top-level data on
every run — which here would mean every host's config (not just the one
being applied) becomes visible to every template, even though none of them
would use it. `.hosts.toml` is instead read explicitly, only by
`.chezmoi.toml.tmpl`, so the one host being applied is the only thing that
was ever exposed anywhere.

A host entry can be empty — its presence in the file is what marks the
machine as known. There's no shared `[default]` table; every field's
fallback lives in `.chezmoi.toml.tmpl` instead, and a host only needs a
sub-table for what it wants to override, e.g.:

```toml
[homelab.pkg-mgmt.makepkg]
jobs = "2"
```

**[`.chezmoi.toml.tmpl`](../../.chezmoi.toml.tmpl)** runs once at `chezmoi init`
time, looks up the current machine by hostname, and flattens its entry
(falling back to the hardcoded default for anything unset) into plain
template variables saved to `~/.config/chezmoi/chezmoi.toml`:

| variable                        | meaning                                                |
|-----------------------------------|-----------------------------------------------------------|
| `.hostname`                        | machine hostname                                           |
| `.git.user.name`                   | git user.name                                              |
| `.git.user.email`                  | git user.email (no default — empty unless a host sets one) |
| `.pkg_mgmt.pacman.parallel_downloads` | pacman.conf `ParallelDownloads`                         |
| `.pkg_mgmt.pacman.multilib`         | whether to enable the `[multilib]` repo (needed for any 32-bit package) |
| `.pkg_mgmt.makepkg.jobs`           | makepkg.conf `MAKEFLAGS="-j<value>"` build parallelism      |
| `.pkg_mgmt.reflector.*`            | reflector.conf flags (save, country, protocol, latest, sort, age, download_timeout) |
| `.pkg_mgmt.reflector.timer.*`      | reflector.timer override (on_calendar, on_boot_sec)         |
| `.pkg_mgmt.aur.enabled`            | whether to build and install paru from the AUR              |
| `.locale.*`                        | locale.conf LANG, locale.gen entries, vconsole KEYMAP, timezone |
| `.services.enabled`                | systemd units to `enable --now`                             |
| `.services.packages`                | unit → pacman packages that provide it                      |
| `.shell.zsh.enabled`                | whether to install zsh and make it the login shell           |
| `.shell.zsh.oh_my_zsh.enabled`      | whether to also install oh-my-zsh, powerlevel10k, and the zsh plugins dot_zshrc.tmpl expects |
| `.cli_tools.enabled`                | pacman packages to install (standalone CLI tools, e.g. neovim/zoxide/eza) |
| `.fonts.enabled`                    | pacman packages to install (fonts, e.g. a Nerd Font for powerlevel10k/eza icons) |
| `.containers.docker.enabled`        | whether to install docker, enable docker.service, and add the user to the docker group |
| `.ssh.enabled`                      | whether to write an sshd_config.d hardening drop-in at all |
| `.ssh.disable_password_auth`        | writes PasswordAuthentication no into that drop-in when true |
| `.ssh.permit_root_login`            | PermitRootLogin value in that drop-in |
| `.zram.enabled`                     | whether to install zram-generator and set up a zram0 swap device |
| `.zram.size`                        | zram-generator.conf zram-size= formula for the zram0 section |
| `.zram.compression_algorithm`       | zram-generator.conf compression-algorithm= for the zram0 section |
| `.zram.swap_priority`               | zram-generator.conf swap-priority= for the zram0 section |
| `.thp.enabled`                      | whether to override transparent hugepage mode at all |
| `.thp.mode`                         | value written to /sys/kernel/mm/transparent_hugepage/enabled |
| `.desktop.enabled`                  | whether to install a desktop environment at all |
| `.desktop.environment`              | which desktop environment to install (only `"niri"` implemented) |
| `.desktop.niri.shell`                | which shell/bar layer to install on top of niri (only `"noctalia"` implemented; only read when `.desktop.environment` is `"niri"`) |
| `.greeter.type`                      | which greetd greeter to install and configure — `""` (none, default), `"tuigreet"`, or `"noctalia-greeter"` from the AUR. Independent of `.desktop.*` |
| `.greeter.noctalia_greeter.session`   | forces a specific Wayland session for noctalia-greeter instead of showing its session picker (only read when `.greeter.type` is `"noctalia-greeter"`) |
| `.greeter.noctalia_greeter.user`      | skips noctalia-greeter's user list, straight to the password prompt for this login (only read when `.greeter.type` is `"noctalia-greeter"`) |
| `.nvidia.enabled`                    | whether to detect and install an NVIDIA driver at all |
| `.browsers.<name>.package`           | pacman package to install for this browser entry |
| `.browsers.<name>.settings`          | about:config preference name → value, written into that browser's `policies.json` |
| `.terminal.kitty.enabled`            | whether to install kitty and write `~/.config/kitty/kitty.conf` at all |
| `.tailscale.operator`                | whether to set the applying user as tailscale's operator, so `tailscale` works without sudo (independent of installing/enabling tailscale itself — see [services](#scripts)) |

(Source data uses `pkg-mgmt` with a hyphen; the generated `[data]` uses
`pkg_mgmt` with an underscore instead, because a hyphen can't appear in a Go
template field name — see the comment in `.chezmoi.toml.tmpl`.)

Every other template in the repo can branch on these, plus chezmoi's built-in
`.chezmoi.hostname`, `.chezmoi.os`, `.chezmoi.arch`, `.chezmoi.osRelease.id`,
etc. See [`dot_zshrc.tmpl`](../../dot_zshrc.tmpl) and
[`dot_gitconfig.tmpl`](../../dot_gitconfig.tmpl) for worked examples of
branching on `.chezmoi.*`.

## Scripts

Each `run_once_before_NN-configure-*.sh.tmpl` script consumes some of the
variables above; see its own page for what it does with them:

1. [Pacman & makepkg](pacman.md)
2. [Reflector](reflector.md)
3. [AUR / paru](aur.md)
4. [Locale](locale.md)
5. [Services](services.md)
6. [NVIDIA](nvidia.md)
7. [Shell](shell.md)
8. [CLI tools](cli-tools.md)
9. [Fonts](fonts.md)
10. [Containers](containers.md)
11. [SSH hardening](ssh-hardening.md)
12. [zram](zram.md)
13. [Transparent hugepages](thp.md)
14. [Desktop](desktop.md)
15. [Greeter](greeter.md)
16. [System files](system-files.md)
17. [Browsers](browsers.md)
18. [Tailscale](tailscale.md)
19. [Terminal (kitty)](terminal.md)

[`.chezmoiignore.tmpl`](../../.chezmoiignore.tmpl) is where to skip whole
files on hosts where they don't apply.

## Registering and reapplying

Running `chezmoi init` on a machine that isn't registered fails outright —
there's no interactive prompt and no silent all-defaults fallback. Add a
`[<hostname>]` table to `.hosts.toml` (it can be empty) first.

**`.chezmoi.toml.tmpl` only runs at `chezmoi init`, not at `chezmoi apply`.**
Editing `[<host>.pkg-mgmt.*]` (or any other field it reads) in
`.hosts.toml` does *not* take effect on the next plain `apply` — the
already-generated `~/.config/chezmoi/chezmoi.toml` is reused as-is. Re-run
`chezmoi init` (safe to repeat; it doesn't touch anything outside that one
config file) to regenerate it, then `apply` — or just `chezmoi init --apply`
to do both in one step.
