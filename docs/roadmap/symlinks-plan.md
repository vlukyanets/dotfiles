# Symlinks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A node keeps a symlink as a symlink, and `add`, `forget`,
`install`, `restore` and `status` handle it.

**Architecture:** A symlink is one more kind of `Item` in the existing
flow: `survey` reads the node with `lstat` and notes each side's target,
`make_plan` and `status` get a branch for it, and `machine` gets
`readlink` and `symlink`. Backups and `restore` need no code of their own,
since a run is laid out like a node.

**Tech Stack:** Python 3.12 standard library; pytest with pyfakefs 6.2;
ruff; mypy; all through `uv run`.

**Spec:** `docs/roadmap/symlinks.md`. Read it and `CLAUDE.md` first.

## Global Constraints

- Only the standard library in `dotfiles/`; no new dependency.
- Tests run on pyfakefs with fake owners and `FakeSudo`; nothing touches
  the machine. `os.chown(..., follow_symlinks=False)` is `lchown` there.
- A symlink's target is kept as it is: never resolved, never rewritten,
  may not exist.
- A symlink has no `.meta` line and no mode; its owner is
  `default_owner(key)`, set when it is made, never compared.
- Printed lines, exactly: `installed <path> -> <target>`,
  `updated <path> -> <target> (backup <run>/<rel>)`,
  `added|updated|unchanged nodes/<node>/<rel> -> <target>`,
  `        target:    <path>  <node side> → <machine side>`, a file side
  shown as `(a file)`.
- Errors, exactly: `<node>/.meta: a symlink has no owner or mode: <key>`;
  `a symlink cannot be a template: <path or key>`;
  `a symlink, not a directory: <path>` (a symlinked directory on the way).
- Before each commit: `uv run pytest`, `uv run ruff check`,
  `uv run mypy`, `git diff --cached` holds no secret. Commit titles as
  given, no attribution trailer; read the message back after committing.
- Docs in English, wrapped at about 80 columns.

## Review Focus

1. A node path that is a symlink where the machine now has a file: `add`
   must replace the symlink, not write through it into what it points to.
   Test in Task 3.
2. `forget` leaving a directory that still holds a node symlink to a
   directory: `is_dir()` follows it, and `rmtree` would delete it. Test in
   Task 3.
3. A node symlink to a directory: `survey` must list it as one symlink and
   install nothing under it. Test in Task 2.
4. A dangling target, in the node and on the machine: `install` makes it,
   `status` shows no difference, `restore` accepts its path although
   `is_file()` is false. Tests in Task 2.
5. A machine symlink where the node has a file, pointing at a file closed
   to the user: `survey` must read the link, never the file behind it.
   Test in Task 2.

---

### Task 1: `readlink` and `symlink` in the machine operations

**Files:**
- Modify: `dotfiles/machine.py` (`Local`, `Sudo`)
- Test: `tests/test_machine.py`

**Interfaces:**
- Produces: `Local.readlink(path: str) -> str`;
  `Local.symlink(path: str, target: str, uid: int, gid: int) -> None`;
  the same two on `Sudo`, through `call()`. `serve` needs no change: a
  `str` result goes into JSON as it is.

- [ ] **Step 1: Write the failing tests**

```python
def test_local_symlink_replaces_the_path_with_its_owner():
    Path("/d/x").write_bytes(b"old")
    Local().symlink("/d/x", "/nowhere", ALICE, ALICE)
    st = os.lstat("/d/x")
    assert stat.S_ISLNK(st.st_mode) and (st.st_uid, st.st_gid) == (ALICE, ALICE)
    assert os.readlink("/d/x") == "/nowhere"
    assert os.listdir("/d") == ["x"]

def test_local_symlink_keeps_the_old_path_when_it_fails(monkeypatch):
    Path("/d/x").write_bytes(b"old")
    monkeypatch.setattr(os, "chown", refuse)  # raises PermissionError, as in the write test
    with pytest.raises(PermissionError):
        Local().symlink("/d/x", "/nowhere", ALICE, ALICE)
    assert Path("/d/x").read_bytes() == b"old"
    assert os.listdir("/d") == ["x"]

def test_serve_answers_readlink_and_symlink():
    answers = ask({"op": "symlink", "path": PATH, "target": "rel/t", "uid": ALICE, "gid": ALICE},
                  {"op": "readlink", "path": PATH})
    assert answers == [{"ok": None}, {"ok": "rel/t"}]
```

Extend `test_sudo_starts_one_helper`: `sudo.symlink("/d/l", "t", ALICE, ALICE)`
then `sudo.readlink("/d/l") == "t"`, still one helper started.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_machine.py -q`
Expected: FAIL, `AttributeError: 'Local' object has no attribute 'symlink'`.

- [ ] **Step 3: Implement**

`Local.symlink`: make the link beside `path` under
`.dotfiles-<16 hex chars of os.urandom>`, `os.chown(temp, uid, gid,
follow_symlinks=False)`, `os.replace(temp, path)`; on any exception unlink
the temp and re-raise, as `write` does. `Local.readlink` is `os.readlink`.

- [ ] **Step 4: Run all checks**

Run: `uv run pytest -q && uv run ruff check && uv run mypy`
Expected: all pass.

- [ ] **Step 5: Commit**

`git commit -m "Added readlink and symlink to the machine operations"`

---

### Task 2: `install`, `restore` and `status` handle symlinks

**Files:**
- Modify: `dotfiles/install.py` (`Item`, `survey`, `make_plan`, `replace`,
  `not_a`), `dotfiles/status.py` (`status`), `dotfiles/restore.py` (the
  paths check)
- Modify: `README.md` (Installing a node, Checking what drifted, Restoring),
  `docs/decisions.md` (row 30)
- Test: `tests/test_install.py`, `tests/test_status.py`,
  `tests/test_restore.py`

**Interfaces:**
- Consumes: Task 1's `readlink` and `symlink`, through
  `install.call(op, path, *args, as_user=...)`.
- Produces: `Item.link: str | None = None` (the node's target; None for a
  file or a directory) and `Item.machine_link: str | None = None` (the
  machine's target when it has a symlink there). `Item.st` stays the
  `lstat`. A test helper in `tests/test_install.py`:
  `node_link(rel: str, target: str) -> None`, imported by the status and
  restore tests.

- [ ] **Step 1: Write the failing tests**

In `tests/test_install.py`, with `node_link` beside `node_file`:

- `test_installs_a_missing_symlink`: `node_link("etc/localtime",
  "/usr/share/zoneinfo/UTC")` (dangling); after `run()`,
  `os.readlink("/etc/localtime")` is the target, its `lstat` owner is
  root, output is `installed /etc/localtime -> /usr/share/zoneinfo/UTC\n`.
- `test_installs_a_home_symlink_as_the_user`: `home/alice/.x -> y`; owner
  alice; `install_module.sudo.calls == []`.
- `test_leaves_a_symlink_with_the_same_target`: machine `/etc/l -> t`
  owned by alice, node `etc/l -> t`; output empty, owner still alice.
- `test_replaces_a_symlink_with_another_target_and_keeps_it`: machine
  `/etc/localtime -> A`, node `-> B`; output
  `updated /etc/localtime -> B (backup {run}/etc/localtime)\n`; the backup
  is a symlink to `A`, owned by alice; the run's `.meta` does not exist.
- `test_replaces_a_file_with_a_symlink`: machine file `/etc/x` 0600 root;
  backup holds its bytes, the run's `.meta` is `0600 root:root etc/x\n`.
- `test_replaces_a_symlink_with_a_file`: machine `/etc/x -> hosts`, node
  file; `/etc/x` is a regular file with the node's bytes; the backup is a
  symlink to `hosts`. Remove `a_symlink_target` from the error cases.
- `test_installs_a_symlink_to_a_directory_without_entering_it`: node
  `etc/sub/f` and `node_link("etc/d", str(NODE / "etc/sub"))`; output
  holds no line for `/etc/d/f`; `/etc/d` is a symlink.
- `test_runs_a_hook_on_a_symlink_written`:
  `node_link("etc/systemd/system/multi-user.target.wants/sshd.service",
  "/usr/lib/systemd/system/sshd.service")`, hook
  `etc/systemd/system/*.wants/* sudo systemctl daemon-reload`;
  `hooks == ["sudo systemctl daemon-reload"]`.
- `test_dry_run_changes_no_symlink`: the replace case with
  `dry_run=True`; `snapshot()` unchanged, the `updated` line printed.
- New error cases in `test_errors_before_anything_is_written`:
  `a_meta_line_for_a_symlink` → `a symlink has no owner or mode: etc/l`;
  `a_directory_where_a_symlink_goes` → `/etc/x`;
  `a_symlink_named_like_a_template` (`etc/x.tmpl -> y`) →
  `a symlink cannot be a template: etc/x.tmpl`. `a_symlink_on_the_way`
  stays, matching `a symlink, not a directory: /etc/d`.

In `tests/test_status.py`:

- `test_shows_where_a_symlink_points`: node `etc/a -> /x`, machine
  `-> /y`; node `etc/b -> /x`, machine file; node file `etc/c`, machine
  `-> /etc/secret` where `/etc/secret` is root 0600; node `etc/d -> /x`,
  machine none; node and machine `etc/e -> /dangling`, machine's owned by
  alice. Output, after the header lines:
  ```
          target:    /etc/a  /x → /y
          target:    /etc/b  /x → (a file)
          target:    /etc/c  (a file) → /etc/secret
          missing:   /etc/d
  ```
  and `"read" not in install_module.sudo.calls`.
- `test_stops_on_what_install_stops_on`: the symlinked directory on the
  way, matching `a symlink, not a directory: /etc/d`.

In `tests/test_restore.py`:

- `test_puts_back_a_replaced_symlink`: machine `/etc/localtime -> A`
  (dangling), node `-> B`, `installed(...)`, then
  `restore(REPO, "hyper", None, ["/etc/localtime"])`; the link points to
  `A` again; output
  `updated /etc/localtime -> A (backup {later}/etc/localtime)\n`.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_install.py tests/test_status.py tests/test_restore.py -q`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement `survey`**

- List the node with `p.is_symlink() or p.is_file()`; `rglob` does not
  enter a symlink to a directory on 3.12.
- Before the other `.meta` checks: a key whose path without its trailing
  slash `is_symlink()` raises the `.meta` error.
- A node symlink: a key ending in `.tmpl` raises the template error;
  `link = os.readlink(node_dir / rel)`; wanted owner from
  `wanted(rel, 0o777)` (no `.meta` line can exist).
- On the machine, for a symlink or a file of the node: a path that is
  neither a symlink nor a regular file raises
  `not a symlink or a regular file: <path>`; `machine_link =
  call("readlink", path)` for a symlink; `machine_data = call("read",
  path)` only for a regular file.
- `not_a` returns `a symlink, not {what}` for a symlink; it is now used
  only for directories.

- [ ] **Step 4: Implement `make_plan` and `replace`**

- A symlink item: none on the machine → `installed`, action
  `call("symlink", path, link, uid, gid, as_user=mine)`; same
  `machine_link` → nothing; otherwise → `updated … -> link (backup …)`.
- A file item with a `machine_link` counts as differing.
- `replace(item: Item, mine: bool, backups: Path, run: Path, rel: str)`
  backs up the old one: a symlink with `call("symlink", run/rel,
  machine_link, os.getuid(), os.getgid())` and no `.meta` line, a file as
  now; then writes the item's file or symlink.
- Every symlink made or replaced goes into `written`, for the hooks.

- [ ] **Step 5: Implement `status` and `restore`**

- `status`: an item with `link` or `machine_link` and a machine path:
  `target:` when `link != machine_link`, sides as in Global Constraints;
  never an owner or mode line for it.
- `restore`: a path given is in the run when `is_file()` or
  `is_symlink()`.

- [ ] **Step 6: Update the docs**

- README, Installing a node: the table gets the symlink rows from the spec;
  the error list says "a directory on the way is a symlink" instead of "a
  target or a directory on the way"; a sentence on a `.meta` line for a
  symlink. Running commands: the `daemon-reload` example line and that a
  symlink in `*.wants/` starts nothing by itself. Checking what drifted:
  the `target:` lines in the example and a bullet for them. Restoring: a
  backed-up symlink comes back as one.
- `docs/decisions.md`, row 30:

  `| 30 | A node keeps a symlink as a symlink, its target as it is; its owner is the default of decision 2, set when it is made and never compared, and it has no mode and no .meta line. install replaces a symlink with another target, a file where the node has a symlink, or a symlink where it has a file, keeping the old one in the run | The enabled systemd units and /etc/localtime are symlinks; Linux ignores a symlink's mode and its owner matters only in sticky directories; a run keeps a symlink as a symlink, so restore puts it back with no code of its own |`

- [ ] **Step 7: Run all checks**

Run: `uv run pytest -q && uv run ruff check && uv run mypy`
Expected: all pass.

- [ ] **Step 8: Commit**

`git commit -m "Made install, restore and status handle symlinks"`

---

### Task 3: `add` and `forget` keep symlinks

**Files:**
- Modify: `dotfiles/add.py` (`copy`), `dotfiles/forget.py` (`forget`)
- Modify: `README.md` (Adding a file, Forgetting a file)
- Delete: `docs/roadmap/symlinks.md`, `docs/roadmap/symlinks-plan.md`
- Test: `tests/test_add.py`, `tests/test_forget.py`

**Interfaces:**
- Consumes: `add_module.sudo.readlink(path: str) -> str` from Task 1.

- [ ] **Step 1: Write the failing tests**

In `tests/test_add.py` (`as_root(os.symlink)` makes machine links):

- `test_keeps_a_symlink_as_a_symlink`: `/etc/localtime ->
  /usr/share/zoneinfo/UTC` (dangling); the node's `etc/localtime` is a
  symlink to it; output
  `added nodes/hyper/etc/localtime -> /usr/share/zoneinfo/UTC\n`;
  `meta() is None`. A second run prints `unchanged …`.
- `test_updates_a_symlink_whose_target_changed`: `updated … -> <new>`.
- `test_a_symlink_replaces_a_file_and_its_meta_line`: `/etc/x` 0600 added
  as a file, then made a symlink; the run prints `updated … -> …` and
  `meta: removed etc/x`.
- `test_a_file_replaces_a_symlink_without_writing_through_it`: `/etc/x ->
  /home/alice/.config/plain` added, then `/etc/x` made a regular file with
  `b"file\n"`; the node's `etc/x` is a regular file with those bytes, and
  `/home/alice/.config/plain` still holds `b"plain\n"`.
- `test_keeps_a_symlink_to_a_directory`: `/etc/d -> /srv`; the node's
  `etc/d` is that symlink and nothing else is under `nodes/`.
- `test_reads_a_symlink_in_a_closed_directory_with_sudo`: the link in a
  root 0700 directory; `"readlink" in add_module.sudo.calls`.
- In `test_rejects_what_is_not_an_absolute_regular_file`, the
  `/etc/link` case goes; new cases: a symlink with `as_template=True` →
  `a symlink cannot be a template: /etc/link`; `/etc/d/f` with
  `/etc/d -> /srv` → `a symlink, not a directory: /etc/d`.
- `test_refuses_a_symlink_kept_as_a_template`: node `etc/x.tmpl`, machine
  `/etc/x` a symlink → `kept as a template, nodes/hyper/etc/x.tmpl;
  dotfiles forget it first`.

In `tests/test_forget.py`:

- `test_removes_a_symlink`: `fs.create_symlink(NODE /
  "etc/localtime", "/usr/share/zoneinfo/UTC")`; after forgetting it, the
  link is gone and the output is
  `removed nodes/hyper/etc/localtime\n`.
- `test_keeps_a_symlink_to_a_directory_beside_the_files_forgotten`: a
  symlink `etc/ssh/link -> /repo/nodes/hyper/home`; forgetting both files
  of `etc/ssh/` leaves `etc/ssh/link` and prints no
  `removed nodes/hyper/etc/ssh/`.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_add.py tests/test_forget.py -q`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement `add`**

- Each parent of the path on the way (`PurePosixPath(rel).parents[:-1]`)
  that `lstat`s as a symlink raises `a symlink, not a directory: <path>`.
- A symlink path: the template error with `--template`; with a template
  in the node, `<path> is kept as a template, <plain>.tmpl; dotfiles
  forget it first`; its target from `os.readlink`, or `sudo.readlink` on
  `PermissionError`; no secret check and no closed-file warning.
- Writing a symlink: `unchanged` when the node has a symlink with that
  target; otherwise unlink what is there and `symlink_to`; its `.meta`
  line, if any, is removed with `meta: removed <key>`.
- Writing a file where the node has a symlink: `updated`, the symlink
  unlinked before the bytes are written; `read_bytes`, `exists` and
  `chmod` never go through it.

- [ ] **Step 4: Implement `forget`**

- A path is in the node when its key `is_file()` or `is_symlink()`.
- A directory is left when it holds anything that `is_symlink()` or is not
  a directory.

- [ ] **Step 5: Update the docs and delete the plan**

README, Adding a file: replace "Only regular files are supported; a
directory or a symlink is an error." with how a symlink is kept (the
spec's `add` bullets, shortened). Forgetting a file: "its copy, its
template or its symlink". `git rm docs/roadmap/symlinks.md
docs/roadmap/symlinks-plan.md`.

- [ ] **Step 6: Run all checks**

Run: `uv run pytest -q && uv run ruff check && uv run mypy`
Expected: all pass.

- [ ] **Step 7: Commit**

`git commit -m "Made add and forget keep symlinks"`
