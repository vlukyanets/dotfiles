from dotfiles.feature import Feature


class ClaudeDesktop(Feature):
    class Arch:
        def packages(self):
            return ["claude-desktop"]
