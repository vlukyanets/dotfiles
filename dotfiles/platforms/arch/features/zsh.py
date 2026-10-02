"""zsh on Arch: oh-my-zsh in ~/.oh-my-zsh, loaded from the top of ~/.zshrc; zsh the login shell."""

import os
import pwd
import re
import shutil
from pathlib import Path
from typing import ClassVar

from dotfiles.feature import Feature
from dotfiles.render import source, template
from dotfiles.retry import retrying

_OMZ = "https://github.com/ohmyzsh/ohmyzsh.git"
_SNIPPET = "~/.config/zsh/dotfiles.zsh"
_SOURCE = f"source {_SNIPPET}"
_P10K = "~/.p10k.zsh"  # powerlevel10k's settings, made by `p10k configure`
_ZSH = "/usr/bin/zsh"
# zsh-completions is only its package: its functions are in zsh's fpath already.
_EXTRAS = ("zsh-autosuggestions", "zsh-syntax-highlighting", "zsh-completions")
_NAME = r"[A-Za-z0-9._-]+"


class Zsh(Feature):
    """zsh, oh-my-zsh with its theme and plugins, the extras from the repositories."""

    rules: ClassVar[dict[str, tuple]] = {
        "theme": (
            lambda v: re.fullmatch(f"{_NAME}(/{_NAME})?", v),
            "a theme of oh-my-zsh, e.g. robbyrussell, or <dir>/<name> of theme_repo",
        ),
        "theme_repo": (
            lambda v: v == "" or re.fullmatch(r"https://\S+", v),
            "empty, or an https git URL",
        ),
        "plugins": (
            lambda v: all(re.fullmatch(_NAME, p) for p in v),
            "names of oh-my-zsh's plugins",
        ),
        "extras": (lambda v: set(v) <= set(_EXTRAS), f"names from {', '.join(_EXTRAS)}"),
    }

    def packages(self) -> list[str]:
        """zsh, git for the clones, and the extras."""
        return ["zsh", "git", *self.settings["extras"]]

    def apply(self) -> None:
        """oh-my-zsh and its theme cloned, our part of ~/.zshrc written and sourced, zsh the
        login shell.
        """
        system, home, settings = self.system, Path.home(), self.settings
        omz = system.files.path(home / ".oh-my-zsh")
        if not (omz / "oh-my-zsh.sh").is_file():
            self._clone(_OMZ, omz, "oh-my-zsh")
        # powerlevel10k/powerlevel10k: the theme powerlevel10k of the clone powerlevel10k.
        clone = settings["theme"].partition("/")[0]
        if settings["theme_repo"] and not (omz / "custom/themes" / clone / ".git").is_dir():
            self._clone(settings["theme_repo"], omz / "custom/themes" / clone, f"theme {clone}")
        p10k = clone == "powerlevel10k"
        if p10k:
            system.files.ensure(home / _P10K.removeprefix("~/"), source(_P10K))
        text = template(_SNIPPET, zsh=settings, p10k=p10k)
        system.files.ensure(home / _SNIPPET.removeprefix("~/"), text)
        # At the top: the rest of ~/.zshrc stays the user's, and overrides ours.
        system.files.line(home / ".zshrc", f"^{re.escape(_SOURCE)}$", _SOURCE, before=".")
        me = pwd.getpwuid(os.geteuid())
        if Path(me.pw_shell).name != "zsh":  # /bin/zsh is /usr/bin/zsh too
            with system.shell.as_root():
                system.shell.run("chsh", "-s", _ZSH, me.pw_name)
            system.report.changed(f"login shell of {me.pw_name}: {_ZSH} (was {me.pw_shell})")
            system.report.notice("zsh is the login shell — log out and back in for it")

    def _clone(self, url: str, dst: Path, what: str) -> None:
        """URL cloned into DST, as WHAT in the report; never pulled after (`omz update` is)."""
        shell = self.system.shell
        if not shell.dry_run:
            for attempt in retrying(self.system.report):
                with attempt:
                    shutil.rmtree(dst, ignore_errors=True)  # a clone cut off halfway
                    shell.run("git", "clone", "--quiet", "--depth", "1", url, str(dst))
        self.system.report.changed(f"{what} cloned into {dst}")
