from dotfiles.feature import Feature


class CppGcc(Feature):
    class Arch:
        def packages(self):
            return ["gcc", "gdb", "make", "cmake", "meson", "ninja", "cppcheck"]
