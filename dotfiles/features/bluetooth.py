from dotfiles.feature import Feature


class Bluetooth(Feature):
    def apply(self, strategy):
        strategy.ensure_service("bluetooth.service")

    class Arch:
        def packages(self):
            return ["bluez", "bluez-utils"]
