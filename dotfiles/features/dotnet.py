from dotfiles.feature import Feature


class Dotnet(Feature):
    class Arch:
        def packages(self):
            return ["dotnet-sdk"]
