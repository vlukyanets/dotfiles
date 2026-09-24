"""pcscd serves ykman's CCID applets (OpenPGP, PIV, OATH); FIDO2 goes over
USB HID through systemd's udev rules and needs no daemon."""

from dotfiles.feature import Feature


class Yubikey(Feature):
    def apply(self, strategy):
        strategy.ensure_service("pcscd.socket")

    class Arch:
        def packages(self):
            return ["yubikey-manager", "pcsclite", "ccid"]
