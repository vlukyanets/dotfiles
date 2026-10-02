"""zsh on Arch: oh-my-zsh in ~/.oh-my-zsh, loaded from the top of ~/.zshrc; zsh the login shell."""

import os
import pwd
import re
import shutil
from pathlib import Path
from typing import ClassVar

from dotfiles.engine import die
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
        "theme.name": (
            lambda v: re.fullmatch(f"{_NAME}(/{_NAME})?", v),
            "a theme of oh-my-zsh, e.g. robbyrussell, or <dir>/<name> of the repo",
        ),
        "theme.repo": (lambda v: v == "" or re.fullmatch(r"https://\S+", v), "an https git URL"),
        "theme.branch": (lambda v: re.fullmatch(r"[A-Za-z0-9._/-]*", v), "a branch name"),
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
        # Not again once it is there: it may be the user's own, with their custom/.
        if not (omz / "oh-my-zsh.sh").is_file():
            self._clone(_OMZ, omz, "oh-my-zsh")
        theme = settings["theme"]
        # powerlevel10k/powerlevel10k: the theme powerlevel10k of the clone powerlevel10k.
        clone, slash, _ = theme["name"].partition("/")
        if theme["repo"]:
            if not slash:
                die(f"zsh: theme {theme['name']} of a repo must be <dir>/<name>")
            dst = omz / "custom/themes" / clone
            if not self._cloned(dst, theme["repo"], theme["branch"]):
                self._clone(theme["repo"], dst, f"theme {clone}", theme["branch"])
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

    def _cloned(self, dst: Path, url: str, branch: str) -> bool:
        """DST a clone of URL, on BRANCH unless that is empty."""
        git = ["git", "-C", str(dst)]
        output = self.system.shell.output
        return (
            (dst / ".git").is_dir()
            and output(*git, "remote", "get-url", "origin") == url
            and (not branch or output(*git, "rev-parse", "--abbrev-ref", "HEAD") == branch)
        )

    def _clone(self, url: str, dst: Path, what: str, branch: str = "") -> None:
        """URL, its BRANCH or its default, cloned into DST in place of what is there, as WHAT
        in the report; never pulled after (`omz update` and the user are).
        """
        shell = self.system.shell
        flags = ["--branch", branch] if branch else []
        if not shell.dry_run:
            for attempt in retrying(self.system.report):
                with attempt:
                    shutil.rmtree(dst, ignore_errors=True)  # a clone cut off halfway, another's
                    shell.run("git", "clone", "--quiet", "--depth", "1", *flags, url, str(dst))
        self.system.report.changed(f"{what} cloned into {dst}" + (f" ({branch})" if branch else ""))
