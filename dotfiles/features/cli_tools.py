from dotfiles.feature import Feature


class CliTools(Feature):
    class Arch:
        def packages(self):
            return [
                "jq",
                "yq",
                "tmux",
                "direnv",
                "zoxide",
                "eza",
                "fzf",
                "bat",
                "tealdeer",
                "ripgrep",
                "fd",
                "unzip",
                "zip",
                "7zip",
                "rsync",
                "wget",
                "curl",
                "ncdu",
                "duf",
                "just",
                "git-delta",
                "lazygit",
                "git-lfs",
                "shellcheck",
                "luacheck",
                "lychee",
                "ffmpeg",
                "pipewire-jack",
                "cmatrix",
                "sbctl",
                "nano",
                "vim",
                "less",
                "tree",
                "clock-rs-git",
            ]

        def replaces(self):
            return ["jack2"]  # ffmpeg would pull jack2, which conflicts with pipewire-jack
