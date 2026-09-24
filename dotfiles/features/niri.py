"""The niri compositor with what a session needs around it, and the GTK
dark theme through gsettings, so portals and GTK apps follow it."""

from dotfiles.feature import Feature


class Niri(Feature):
    def apply(self, strategy):
        strategy.ensure_gsetting("org.gnome.desktop.interface", "color-scheme", "'prefer-dark'")
        strategy.ensure_gsetting("org.gnome.desktop.interface", "gtk-theme", "'Adwaita-dark'")

    class Arch:
        def packages(self):
            return [
                "niri", "xwayland-satellite", "xdg-desktop-portal-gtk", "xdg-utils",
                "wl-clipboard", "gnome-themes-extra",
            ]  # fmt: skip
