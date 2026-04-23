#!/bin/bash
# Deploy system files to their target locations.
# Must be run with sudo or as root.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install_file() {
    local src="$SCRIPT_DIR/$1"
    local dst="/$1"
    local mode="${2:-644}"
    local owner="${3:-root:root}"

    if [ ! -f "$src" ]; then
        echo "SKIP (not found): $src"
        return
    fi

    install -Dm"$mode" "$src" "$dst"
    chown "$owner" "$dst"
    echo "  installed: $dst (mode=$mode owner=$owner)"
}

echo "==> Installing system files..."

install_file etc/acpi/events/lid 644
install_file etc/acpi/lid.sh 755
install_file etc/udev/rules.d/99-power-profile.rules 644
install_file usr/local/bin/power-profile-switch 755
install_file etc/locale.gen 644
install_file etc/locale.conf 644
install_file etc/vconsole.conf 644
install_file etc/plymouth/plymouthd.conf 644
install_file etc/mkinitcpio.conf 644
install_file etc/pacman.conf 644
install_file etc/makepkg.conf 644
install_file etc/xdg/reflector/reflector.conf 644
install_file etc/ssh/sshd_config 644

# Install the kernel preset matching the running kernel
case "$(uname -r)" in
    *-zen*)
        install_file etc/mkinitcpio.d/linux-zen.preset 644
        ;;
    *-lts*)
        install_file etc/mkinitcpio.d/linux-lts.preset 644
        ;;
    *)
        install_file etc/mkinitcpio.d/linux.preset 644
        ;;
esac

echo "==> Reloading udev rules..."
udevadm control --reload-rules
udevadm trigger

echo "==> Done."
