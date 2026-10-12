# Symlinks

A node keeps a symlink as a symlink, so `add`, `install`, `status`,
`restore` and `forget` handle the ones the owner set on purpose: the
enabled systemd units (`etc/systemd/system/*.wants/*`,
`etc/systemd/user/*.wants/*`, `display-manager.service`) and
`/etc/localtime`. This plan is deleted by the last commit of its pull
request.

## Decisions

The owner made these; they go into `docs/decisions.md` as row 30.

| Question | Decision | Why |
|---|---|---|
| What a node keeps | Any symlink, as a symlink in git (mode `120000`), its target as it is, absolute or relative | One mechanism for units and `/etc/localtime`; git keeps symlinks itself |
| Owner and mode | A symlink's owner is the default of decision 2, set when it is made, and never compared; its mode is not kept. A `.meta` line for a symlink is an error | Linux ignores a symlink's mode, and its owner matters only in sticky directories, where no kept symlink lives |
| The machine has another thing at the path | `install` replaces a symlink with another target, or a file where the node has a symlink, or a symlink where the node has a file, keeping the old one as a backup | Nothing is lost, as with decision 11; a run keeps a symlink as a symlink, so `restore` needs no code of its own |

## How it works

### The node

- A symlink in `nodes/<node>/` is the machine's symlink; its target is not
  rewritten and may not exist.
- It has no `.meta` line; `install` and `status` stop on one with
  `.meta: a symlink has no owner or mode: <path>`.
- It cannot be a template.
- A node is read with `lstat`: a symlink in it is never followed, and a
  symlink to a directory is not entered.

### `add`

- A path that is itself a symlink is kept as a symlink, whatever it points
  to, a directory included; the target is read with `readlink`, through
  `sudo` when needed. A symlinked directory on the way becomes an error,
  `a symlink, not a directory: <path>`, since `install` refuses one; until
  now `add` went through it.
- It prints `added nodes/<node>/<path> -> <target>`, `updated …` when the
  node has another target or a file there, or `unchanged …`.
- No `.meta` line is written for it; a file it replaces loses its line.
  The directories above it get theirs as now.
- `--template` on a symlink is an error. So is a symlink at a path kept as
  a template: forget the template first.
- The target is not checked for secrets: it is a path. The pre-commit
  scan still reads it in the staged diff.

### `forget`

Removes a symlink from the node like a file; a node path counts when it is
a file or a symlink.

### `install` and `restore`

| On the machine | What happens | Printed |
|---|---|---|
| Nothing | The symlink is made | `installed /etc/localtime -> <target>` |
| A symlink with the same target | Nothing; its owner is left alone | Nothing |
| A symlink with another target, or a file | The old one goes to the backup run, then the symlink replaces it | `updated /etc/localtime -> <target> (backup …)` |
| A symlink, where the node has a file | The old symlink goes to the backup run, then the file replaces it | `updated /etc/x (backup …)` |
| A directory, or a symlinked directory on the way | An error before the first write, as now | — |

- A symlink is made beside its path under a temporary name, given its
  owner with `lchown` (as the user, or through `sudo` when the owner is
  not the user), then renamed over the path with `os.replace`.
  `machine.Local` and `machine.Sudo` get `readlink` and `symlink`.
- A backed-up symlink lies in the run as a symlink, owned by the user,
  with no `.meta` line; a backed-up file keeps its line. `restore` puts
  both back through `make_plan`, and takes a symlink's path as an
  argument.
- A symlink made or replaced counts as written for `.hooks`. A symlink in
  `*.wants/` does not start a unit; systemd reads it on `daemon-reload` or
  at boot. The README shows the hook
  `etc/systemd/system/*.wants/* sudo systemctl daemon-reload`.
- `--dry-run` prints the same lines and changes nothing.

### `status`

A new kind of line, `target:`, from the node to the machine; a file on
either side shows as `(a file)`:

```
        target:    /etc/localtime  /usr/share/zoneinfo/Europe/X → /usr/share/zoneinfo/UTC
        target:    /etc/x  /srv/y → (a file)
        target:    /etc/y  (a file) → /srv/z
        missing:   /etc/systemd/system/multi-user.target.wants/sshd.service
```

- `target:` when the targets differ, or one side is a symlink and the
  other a file. Two files that differ stay `modified`, with their diff
  under `-v`; `-v` adds nothing to a `target:` line.
- A missing symlink is `missing:`. A symlink's owner and mode are not
  compared. A dangling symlink is not a difference.
- A directory where the node has a symlink, or a symlinked directory on
  the way, is the error `install` stops on.

## Steps

Branch `feature/symlinks`, one pull request. Each commit runs
`uv run pytest`, `uv run ruff check` and `uv run mypy`, and works on its
own.

1. `Added readlink and symlink to the machine operations`: `Local` and
   `Sudo`, the atomic replace with `lchown`; tests in
   `tests/test_machine.py`, through `serve()` too.
2. `Made install, restore and status handle symlinks`: `survey` with
   `lstat`, the branches in `make_plan` and `status`, the `.meta` error;
   the README (the `install` table, the `status` example, the hook) and
   row 30 in `docs/decisions.md`. Tests: each row of the `install` table,
   a symlink's backup and its restore, a hook on a symlink, `--dry-run`,
   each `target:` case, a dangling symlink.
3. `Made add and forget keep symlinks`: `add` and `forget`, the README;
   tests in `tests/test_add.py` and `tests/test_forget.py`. The tests that
   expect `symlinks are not supported` change to the new behaviour; the
   symlinked directory on the way stays an error. This commit also
   deletes this plan.

`install` comes before `add` so no commit has `add` putting a symlink into
a node that `install` would still read through.
