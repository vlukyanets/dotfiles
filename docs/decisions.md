# Decisions

Each row is a decision the owner made, with why. A changed decision is an
edited row.

| # | Decision | Why |
|---|---|---|
| 1 | A node is a one-to-one copy of a machine's files at their paths from `/`, in `nodes/<node>/` | The earlier feature engine was too heavy; a copy is read and changed like the machine itself |
| 2 | Owner and mode: `<user>:<user>` for `home/<user>/` and below, `root:root` elsewhere; a file 0644, or 0755 from git's executable bit; a directory 0755. `nodes/<node>/.meta` lists only the exceptions as `<mode> <owner>:<group> <path>`, a directory's path ending in a slash | Almost every file and directory has the defaults, so only the few others need writing down; git keeps the executable bit but nothing about directories |
| 3 | The scripts are a Python package, `dotfiles` in `dotfiles/`, with one `dotfiles` command and a subcommand for each job; it uses only the standard library | Python is easier to test than shell; one command keeps the jobs and their shared code together |
| 4 | Dependencies are kept in `pyproject.toml` and pinned in `uv.lock`; everything runs through `uv` | The same versions on every machine and in CI, from one command: `uv sync` |
| 5 | Tests run with pytest on a fake filesystem (pyfakefs), with fake owners | A test never touches the machine and does not depend on the user who runs it |
| 6 | `dotfiles add` refuses a file that looks like it holds a secret, by the rules in `secret_leaks.toml`, naming the line and the rule but never the value; `--force` copies it anyway, with a warning. It also warns about files closed to others | The repository is public: a pushed secret is leaked; refusing makes copying one a deliberate act |
| 7 | Secrets are checked by our own scanner, `dotfiles scan`, with the rules in `secret_leaks.toml`: hundreds of known token formats borrowed under MIT, with 28 regexes rewritten for Python, plus our own rules for what dotfiles hold, like `psk=` lines. The scanner weighs keywords, entropy and allowlists, and decodes base64, hex, percent and unicode-escaped text | It needs only Python and uv, so every machine runs the same full check; one rules file and one scanner cannot drift apart |
| 8 | `dotfiles add` takes the node name explicitly | The hostname is not always the node's name, and a wrong guess puts files into the wrong node |
