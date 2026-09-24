from dotfiles.feature import Feature


class Neovim(Feature):
    class Arch:
        def packages(self):
            return ["neovim", "git", "tree-sitter-cli"]
