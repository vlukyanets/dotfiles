# CLAUDE.md: dotfiles

The configuration of the owner's machines, kept as plain copies of their
files, and the `dotfiles` command that keeps and installs them. Read this file in full before the
first change.

## What this is

| Path | What it holds |
|---|---|
| `nodes/<node>/` | One machine: its files at their paths from `/`, one to one (`nodes/hyper/etc/ssh/sshd_config.d/10-local.conf`) |
| `nodes/<node>/.meta` | Only the files and directories whose owner or mode differ from the defaults below, one per line: `0600 root:root etc/ssh/ssh_host_ed25519_key`; a directory's path ends in a slash: `0700 valentinl:valentinl home/valentinl/` |
| `dotfiles/` | The Python package behind the `dotfiles` command: a subcommand for each job (adding files, installing a node, filling templates, checking what drifted) |
| `tests/` | The tests: `tests/test_add.py` checks `dotfiles add` |
| `secret_leaks.toml` | The secret rules, read by `dotfiles scan` and `dotfiles add` |
| `.githooks/`, `.github/workflows/` | The pre-commit hook and CI, both checking for secrets |
| `pyproject.toml`, `uv.lock` | The package and its dependencies, pinned; everything runs through `uv` |
| `docs/` | How it works now, the decisions with why, and plans |

- A file or directory under `nodes/<node>/home/<user>/`, and that directory
  itself, belongs to that user; any other belongs to `root:root`. A file's
  mode is the one git keeps: 0644, or 0755 if executable. A directory's mode
  is 0755.
- Directories need their metadata as much as files do: git keeps nothing
  about them, so a directory with another owner or mode (`~/.ssh/`,
  `/etc/sudoers.d/`) must have its line in `.meta`.
- A file is a copy, not a template, unless it cannot be: a secret, or a value
  only the machine knows. A template is filled at install time.
- Keeping the copies current is a job for the owner and the agent, with the
  drift check's help: it lists what differs between a machine and its node.

## Principles

1. **The owner decides.** Every significant or hard-to-reverse choice is the
   owner's. The agent brings two or three options with their trade-offs and
   a recommendation; a decision is recorded only once the owner made it.
2. **Simple and boring.** The least code and the fewest moving parts that do
   the job. This repository once was a feature engine and was dropped for
   being too heavy: no engine, no plugin system, no configuration for a
   value that never changes, nothing built "for later".
3. **Small steps.** One logical change at a time, each one working and
   reviewable on its own.
4. **Documents first.** A change in how things work updates `docs/` in the
   same pull request. A new decision gets a row in `docs/decisions.md`, with
   why.
5. **A machine is changed only on purpose.** Commands that write to a machine
   show what they would do first and do it only when asked.

## Rules for the agent

### Always

- **Ask before deciding.** Anything not already settled by `docs/` or
  `docs/decisions.md` goes to the owner as options.
- **Read before writing.** Read the docs, the decisions and the files a
  change touches. Reuse what exists before adding something new.
- **Explain** what you are about to do and why, and afterwards what you did,
  plainly, in the owner's language.
- **Verify.** Run the checks before saying something works. Report failures
  as they are, and any check that could not run.
- **Check for AI attribution after every commit and pull request.** Tools
  may add it on their own: a `Co-Authored-By` or session trailer, a
  "Generated with …" footer. Read the commit message back after every commit
  and the pull request back after creating or editing it; remove any
  attribution and read it back again.

### Never, without asking first

- Run `dotfiles` to install, or anything else that writes to a real machine
  (`/etc`, a home directory, packages, services). Reading a machine for the
  drift check is fine.
- Delete data, branches or files that are not part of the current change.
- Publish, create repositories or releases, or send messages.
- Add a dependency: a package in `pyproject.toml`, or a tool the command
  needs beyond Python and uv. The command itself uses only the standard
  library; pytest and the like are development dependencies.

### Never

- Push to `master`, merge a pull request or rewrite `master`'s history.
- Put a secret into the repository, a log, a commit or the chat: private
  keys, tokens, passwords, Wi-Fi credentials. **This repository is public.**
  A file that holds a secret is kept as a template with a placeholder, or not
  kept at all.
- Record a decision the owner did not make, or contradict one in
  `docs/decisions.md`; bring options to change it instead.
- Claim a check passed without running it, or invent facts, package names,
  options or paths: check them on the machine or in the upstream source.
- Add AI attribution to commits or pull requests.
- Change these rules without the owner's approval.

## Working with several agents

The agent the owner talks to is the **lead**; the agents it starts are
**helpers**. The lead stays responsible for everything a helper does.

- **One agent by default.** Start helpers only for work that splits into
  independent parts: separate files, separate nodes, a search across many
  files, a review. A small change is done by the lead alone. More than
  five helpers at once only with the owner's approval.
- **Helpers follow this file.** Every brief tells the helper to read
  `CLAUDE.md` first; all its rules apply to helpers as they are, including
  the ones on machines, secrets and attribution.
- **A brief stands on its own.** It names the goal, the files the helper may
  change, what it must not touch, how to verify the result and what to
  report back. A helper does not see the conversation with the owner.
- **Only the lead talks to the owner.** A helper that meets an open
  question stops and reports it with options; the lead takes it to the
  owner. A helper never decides it on its own.
- **One working tree per writer.** A helper that changes files works in its
  own git worktree on its own branch. Two agents never change the same
  file at the same time. Helpers that only read may share the lead's tree.
- **Helpers do not publish.** They do not push, open pull requests or touch
  a real machine. The lead brings their work together into one branch per
  logical change, commits it and opens the pull request.
- **Trust, but check.** The lead reads every helper's diff and runs the
  checks itself before using the result; a helper's "done" is a claim, not
  a proof. A finding from a review helper is checked before it is fixed.
- **Clean up.** The lead removes the helpers' worktrees and branches once
  their work is in the pull request, and only those.

## Files and code

- A file in `nodes/` is the machine's file as it is, comments and all. Do not
  reformat, reorder or "improve" it; a change to it is a change to the
  machine.
- Copy only what the owner set on purpose. A file a package installed and
  nobody changed stays out.
- A subcommand is a module in `dotfiles/` (`add.py` for
  `dotfiles add`); `cli.py` only parses the arguments and calls it.
- Subcommands are idempotent: run twice, the second run changes nothing.
  They print each change they make, and have a dry run that prints the
  changes and makes none.
- Subcommands fail loudly with a message saying what and where; they never
  swallow an error.
- Subcommands take the root to read from or write to as a parameter, `/` by
  default.
- Tests live in `tests/`, one file per module: `tests/test_add.py`. They run
  with pytest on a fake filesystem (pyfakefs) with fake owners and a fake
  `sudo`, so they never touch the machine and do not depend on who runs
  them.
- A deliberate shortcut with a known limit gets a comment starting with
  `NOTE:` that names the limit and the way out.

## Documentation

| Kind | Place | Lifetime |
|---|---|---|
| What the repository is, how to use it | `README.md` | Permanent |
| How the layout and the command work | `docs/` | Permanent |
| Decisions, each with why | `docs/decisions.md` | Permanent; a changed decision is an edited row |
| Plans and task lists | `docs/roadmap/` | Deleted when done |

- Docs describe how things are now; why lives in `docs/decisions.md`, and
  the docs link to its row instead of repeating it.
- Style: lead with the point, short sentences, plain words, concrete names.
  Tables for things compared on several attributes, numbered lists for
  steps, Mermaid diagrams, never ASCII art. Wrap at about 80 characters.
- Everything committed is in English: files, comments, commits, pull
  requests. Chat with the owner is in the owner's language.

## Git

- `master` is protected: changes arrive only through pull requests, merged by
  rebase, so history stays linear and every commit lands as it is and must
  stand on its own.
- Branch names: `<kind>/<topic>`, lowercase kebab-case, at most 50
  characters. Kind is `feature`, `fix`, `docs`, `refactor` or `chore`:
  `feature/staged-packages`.
- Inside a branch, history may be rewritten before the merge (reorder,
  squash, reword); force-push it with `--force-with-lease`.
- Commit title: a past-tense verb first (`Added …`, `Fixed …`), at most 72
  characters, no trailing period, no `feat:`-style prefixes. Body, if
  needed: one plain paragraph on what changed and why, wrapped at 72.
- Pull request: one logical change. The description says what changed, why,
  how to verify it and any risk. The owner reviews and merges.
- CI pins everything it runs by hash, never by a tag that can move: an
  action by its commit SHA with the tag in a comment
  (`actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`), a
  container image by its digest with the tag next to it, and a runner by its
  version (`ubuntu-24.04`, not `ubuntu-latest`). Look the hash up upstream;
  never write it from memory.

## Before committing

Run this checklist before every commit.

1. The tests pass: `uv run pytest`.
2. No secret is staged: `git diff --cached` holds no private key, token or
   password.
3. Every staged file is in English, except the copies of a machine's
   files, which stay as they are.
4. `docs/` and `docs/decisions.md` still agree with what changed.
