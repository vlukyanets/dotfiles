"""oomd on every Linux: systemd-oomd on, killing earlier than its stock limits."""

from dotfiles.feature import Feature
from dotfiles.render import template

_DROP_INS = (
    "/etc/systemd/oomd.conf.d/10-dotfiles.conf",
    "/etc/systemd/system/-.slice.d/10-oomd.conf",
    "/etc/systemd/system/user@.service.d/10-oomd.conf",
)
_UNIT = "systemd-oomd.service"


class Oomd(Feature):
    """Its drop-ins, read again when one changed, and the service on; part of systemd."""

    def apply(self) -> None:
        """The drop-ins; daemon-reload and a restart when one changed; the service on."""
        system = self.system
        # A list, not any(generator): every drop-in is written, not just up to the first change.
        edits = [system.files.ensure(dst, template(dst), owner="root:root") for dst in _DROP_INS]
        if any(edits):
            with system.shell.as_root():
                system.shell.run("systemctl", "daemon-reload")
                # oomd.conf.d is read when oomd starts, not on daemon-reload.
                system.shell.run("systemctl", "try-restart", _UNIT)
        system.ensure_service(_UNIT)
