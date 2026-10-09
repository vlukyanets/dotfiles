"""Steam on Arch, from [multilib], on the 32-bit drivers of the host's GPUs."""

from dotfiles.feature import Feature, Setting


class Steam(Feature):
    """steam, and the font its ttf-font would otherwise get from --noconfirm."""

    def packages(self) -> list[str]:
        """steam; ttf-liberation, the font Arch's wiki names for it."""
        return ["steam", "ttf-liberation"]

    def requires(self) -> list[str | Setting]:
        """hardware.graphics's 32-bit drivers: installed first, they are steam's vulkan-driver."""
        return [Setting("hardware.graphics.lib32", True)]
