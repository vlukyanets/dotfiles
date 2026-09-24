from dotfiles.feature import Feature


class MissionCenter(Feature):
    class Arch:
        def packages(self):
            return ["mission-center"]
