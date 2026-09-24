from dotfiles.feature import Feature


class CppClang(Feature):
    class Arch:
        def packages(self):
            return ["clang", "lldb", "lld", "llvm", "make", "cmake", "meson", "ninja", "cppcheck"]
