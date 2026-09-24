"""zsh as the login shell, with oh-my-zsh, powerlevel10k and the two
plugins .zshrc lists. Clones are shallow and never updated here: that is
`omz update`'s job."""

import os
import pwd
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotfiles import engine
from dotfiles.engine import as_root, changed, defer, notice, retrying, run
from dotfiles.feature import Feature

OMZ = ".oh-my-zsh"
CLONES = {
    OMZ: "https://github.com/ohmyzsh/ohmyzsh.git",
    f"{OMZ}/custom/themes/powerlevel10k": "https://github.com/romkatv/powerlevel10k.git",
    f"{OMZ}/custom/plugins/zsh-autosuggestions": "https://github.com/zsh-users/zsh-autosuggestions.git",
    f"{OMZ}/custom/plugins/zsh-syntax-highlighting": "https://github.com/zsh-users/zsh-syntax-highlighting.git",
}  # fmt: skip


class Zsh(Feature):
    def apply(self, strategy):
        zsh = shutil.which("zsh") or "/usr/bin/zsh"
        me = pwd.getpwuid(os.geteuid())
        if me.pw_shell != zsh:
            with as_root():
                run("chsh", "-s", zsh, me.pw_name)
            changed(f"login shell = {zsh}")
            notice("default shell changed to zsh — takes effect at the next login")
        for where, url in CLONES.items():
            ensure_clone(url, Path.home() / where)

    class Arch:
        def packages(self):
            return ["zsh", "git"]


def ensure_clone(url: str, dst: Path) -> bool:
    """DST is a checkout of URL. Cloned next to it and moved into place, so a
    clone cut off halfway is never taken for a finished one."""
    if dst.is_dir():
        return False
    if not engine.DRY_RUN:
        dst.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=dst.parent) as tmp:
            try:
                for attempt in retrying():
                    with attempt:
                        shutil.rmtree(f"{tmp}/clone", ignore_errors=True)
                        run("git", "clone", "--quiet", "--depth", "1", url, f"{tmp}/clone")
            except subprocess.CalledProcessError:
                defer(f"cloning {url} failed")
            os.rename(f"{tmp}/clone", dst)
    changed(f"cloned {dst.name}")
    return True
