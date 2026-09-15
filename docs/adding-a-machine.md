# Adding a new machine

1. Add a `[<hostname>]` table to `.hosts.toml` (a template is already
   there, commented out) from wherever's convenient, then commit and push
   it:
   ```sh
   chezmoi cd && git add .hosts.toml && git commit -m "add host <name>" && git push
   ```
   This has to happen *before* step 2 — `chezmoi init` on the new machine
   clones the repo fresh from the remote, and now fails outright if that
   clone doesn't already have the new hostname registered.
2. On the new machine:
   ```sh
   sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply vlukyanets
   ```
   (already have chezmoi? just `chezmoi init --apply vlukyanets`)
