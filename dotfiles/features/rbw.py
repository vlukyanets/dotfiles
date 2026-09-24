"""Not a feature of the schema: switched by secrets.backend. Its config is a
dotfile; logging in and unlocking are the user's."""

from dotfiles.feature import Feature


class Rbw(Feature):
    class Arch:
        def packages(self):
            return ["rbw", "pinentry"] if self.cfg["secrets"]["backend"] == "rbw" else []
