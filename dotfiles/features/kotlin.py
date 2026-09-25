from dotfiles.feature import Feature


class Kotlin(Feature):
    class Arch:
        def packages(self):
            return ["kotlin", "gradle"]

        def requires(self):
            return ["jdk"]  # kotlin needs a java-environment; jdk picks which
