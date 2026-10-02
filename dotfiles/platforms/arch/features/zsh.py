"""zsh on Arch: oh-my-zsh in ~/.oh-my-zsh, loaded from the top of ~/.zshrc; zsh the login shell."""

import os
import pwd
import re
import shutil
from pathlib import Path
from typing import ClassVar

from dotfiles.feature import Feature
from dotfiles.render import template
from dotfiles.retry import retrying

_OMZ = "https://github.com/ohmyzsh/ohmyzsh.git"
_SNIPPET = "~/.config/zsh/dotfiles.zsh"
_SOURCE = f"source {_SNIPPET}"
_ZSH = "/usr/bin/zsh"
# zsh-completions is only its package: its functions are in zsh's fpath already.
_EXTRAS = ("zsh-autosuggestions", "zsh-syntax-highlighting", "zsh-completions")
_NAME = r"[A-Za-z0-9._-]+"


class Zsh(Feature):
    """zsh, oh-my-zsh with its theme and plugins, the extras from the repositories."""

    rules: ClassVar[dict[str, tuple]] = {
        "theme": (lambda v: re.fullmatch(_NAME, v), "a theme of oh-my-zsh, e.g. robbyrussell"),
        "plugins": (
            lambda v: all(re.fullmatch(_NAME, p) for p in v),
            "names of oh-my-zsh's plugins",
        ),
        "extras": (lambda v: set(v) <= set(_EXTRAS), f"names from {', '.join(_EXTRAS)}"),
    }

    def packages(self) -> list[str]:
        """zsh, git for the clone, and the extras."""
        return ["zsh", "git", *self.settings["extras"]]

    def apply(self) -> None:
        """oh-my-zsh cloned, our part of ~/.zshrc written and sourced, zsh the login shell."""
        system, home = self.system, Path.home()
        omz = system.files.path(home / ".oh-my-zsh")
        if not (omz / "oh-my-zsh.sh").is_file():
            self._clone(omz)
        snippet = home / _SNIPPET.removeprefix("~/")
        system.files.ensure(snippet, template(_SNIPPET, zsh=self.settings))
        # At the top: the rest of ~/.zshrc stays the user's, and overrides ours.
        system.files.line(home / ".zshrc", f"^{re.escape(_SOURCE)}$", _SOURCE, before=".")
        me = pwd.getpwuid(os.geteuid())
        if Path(me.pw_shell).name != "zsh":  # /bin/zsh is /usr/bin/zsh too
            with system.shell.as_root():
                system.shell.run("chsh", "-s", _ZSH, me.pw_name)
            system.report.changed(f"login shell of {me.pw_name}: {_ZSH} (was {me.pw_shell})")
            system.report.notice("zsh is the login shell — log out and back in for it")

    def _clone(self, omz: Path) -> None:
        """oh-my-zsh cloned into OMZ; `omz update` keeps it up to date from then on."""
        shell = self.system.shell
        if not shell.dry_run:
            for attempt in retrying(self.system.report):
                with attempt:
                    shutil.rmtree(omz, ignore_errors=True)  # a clone cut off halfway
                    shell.run("git", "clone", "--quiet", "--depth", "1", _OMZ, str(omz))
        self.system.report.changed(f"oh-my-zsh cloned into {omz}")
