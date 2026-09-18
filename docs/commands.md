# Everyday commands

| command                    | what it does                                         |
|-----------------------------|-------------------------------------------------------|
| `chezmoi edit ~/.zshrc`     | open the source template for a managed file           |
| `chezmoi diff`              | preview what `apply` would change                     |
| `chezmoi apply`             | render templates and write them into `$HOME`          |
| `chezmoi cd`                | drop into the source dir (this repo) as a subshell     |
| `chezmoi update`            | `git pull` + `apply` in one step                       |
| `chezmoi status`            | show which managed files differ from source            |
