# SSH hardening

[`.chezmoiscripts/run_once_before_10-configure-ssh-hardening.sh.tmpl`](../../.chezmoiscripts/run_once_before_10-configure-ssh-hardening.sh.tmpl)
is gated behind `ssh.enabled` (default `false`) — hosts that leave it unset
skip it entirely and sshd's own config is never touched. When enabled, it
writes `/etc/ssh/sshd_config.d/dotfiles.conf` with `PasswordAuthentication`
and `PermitRootLogin` set from `ssh.disable_password_auth` (default
`false` — `PasswordAuthentication` stays at sshd's own compiled-in default
of `yes`) and `ssh.permit_root_login` (default `"prohibit-password"`,
also sshd's own compiled-in default) — leaving both unset writes a drop-in
with no practical effect. The drop-in is written whether or not `"sshd"`
appears in [`services.enabled`](services.md): it's independent of that
script, and only reloaded through `systemctl reload sshd` when sshd is
already active — on a host where sshd isn't running yet, the file just
sits there ready for whenever it's installed and started.

**CAUTION:** setting `ssh.disable_password_auth = true` disables password
login outright. Only do that once key-based login is confirmed working
from a session you already have open on that host — there's no automatic
rollback if it turns out a key wasn't actually in place.

`disable_password_auth` defaults `false` (rather than mirroring sshd's
`yes` as a `true`-shaped default) deliberately: Go template's `default`
treats a field explicitly set to `false` as unset and substitutes the
fallback, so a `true`-shaped default would silently ignore a host trying
to turn hardening back off. Keeping every boolean here false-shaped, the
same as `ssh.enabled` and every other opt-in flag in this repo, sidesteps
that entirely.
