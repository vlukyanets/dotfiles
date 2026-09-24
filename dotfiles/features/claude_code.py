from dotfiles.feature import Feature


class ClaudeCode(Feature):
    class Arch:
        def packages(self):
            return ["claude-code"]
