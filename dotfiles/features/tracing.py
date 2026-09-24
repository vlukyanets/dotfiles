from dotfiles.feature import Feature


class Tracing(Feature):
    class Arch:
        def packages(self):
            return ["valgrind", "strace", "ltrace", "perf"]
