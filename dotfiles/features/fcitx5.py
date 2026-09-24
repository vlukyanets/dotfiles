from dotfiles.feature import Feature


class Fcitx5(Feature):
    class Arch:
        def packages(self):
            packages = ["fcitx5", "fcitx5-gtk", "fcitx5-qt", "fcitx5-configtool"]
            if "chinese" in self.cfg["features"]["locale"]["languages"]:
                packages.append("fcitx5-chinese-addons")
            return packages
