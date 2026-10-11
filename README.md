# dotfiles

The configuration of my machines, kept as plain copies of their files.

- `nodes/<node>/` holds one machine's files at their paths from `/`:
  `nodes/hyper/etc/ssh/sshd_config.d/10-local.conf`.
- `nodes/<node>/.meta` lists only the files and directories whose owner or
  mode differ from the defaults, one per line:
  `0600 root:root etc/ssh/ssh_host_ed25519_key`. A directory's path ends in
  a slash: `0700 valentinl:valentinl home/valentinl/`. The defaults are
  `<user>:<user>` for `home/<user>/` and below, `root:root` elsewhere; 0644
  for a file, or 0755 if executable; 0755 for a directory.
- `dotfiles/` is the Python package behind the `dotfiles` command;
  `uv run python -m dotfiles` runs it too.
- `tests/` holds its tests.

Why it is built this way: [docs/decisions.md](docs/decisions.md).

## Setting up

```sh
sudo pacman -S python uv
uv sync
```

## Checking for secrets

```sh
uv run dotfiles scan --staged          # the lines the staged changes add
uv run dotfiles scan --history         # the lines every commit adds
uv run dotfiles scan nodes/hyper       # whole files, or a directory
```

The rules are in `secret_leaks.toml`: hundreds of known token formats,
plus rules for what dotfiles hold, like Wi-Fi passwords in `psk=` lines.
The scanner weighs keywords, entropy and allowlists, so placeholders like
`${WIFI_PASSWORD}` or `{{ .psk }}` pass, and it decodes base64, hex,
percent and unicode-escaped text to find secrets hidden in it. It names
the file, the line and the rule, never the value, and exits with 1 if it
finds something. A line that only looks like a secret can be marked with
`secret-leaks:allow`. `dotfiles add` runs the same check on each file it
copies.

## Adding a file

```sh
uv run dotfiles add hyper /etc/ssh/sshd_config.d/10-local.conf ~/.config/niri/config.kdl
```

The command copies each file into `nodes/hyper/` at its path and updates
`nodes/hyper/.meta` when the owner or mode of the file, or of any directory
above it, is not the default. Running it again updates the copies that
changed and prints `unchanged` for the rest.

This repository is public, so the command refuses a file that looks like it
holds a secret: a known token format (GitHub, AWS, Slack, API keys), a
private key, or a line like `psk=…` or `password: …`. It names the file,
the line and the kind of secret, never the value. Keep such a file as a
template instead. It also warns about a file that others cannot read, since
it may hold a secret too. A file or directory closed to you is read with
`sudo`.

- `--dry-run` prints what would change and changes nothing.
- `--force` copies a file even if it looks like it holds a secret.
- `--root DIR` reads the files from `DIR` instead of `/`.

Only regular files are supported; a directory or a symlink is an error.

## Testing

```sh
uv run pytest
```

The tests run on a fake filesystem (pyfakefs) with fake owners; they never
touch the machine.

## License

Released into the public domain; see [LICENSE](LICENSE). `secret_leaks.toml`
contains third-party rules under the MIT license; see the notice at its top.
