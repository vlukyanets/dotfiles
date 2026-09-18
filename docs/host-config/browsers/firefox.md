# Firefox

`hyper-lin`'s `browsers.firefox.settings` (in `.hosts.toml`) carries ~120
preferences ported from [arkenfox/user.js][arkenfox], a widely used,
actively maintained Firefox privacy/hardening template. Only its
non-`OPTIONAL` sections are used — the ones arkenfox's own maintainers
consider safe enough to ship as defaults rather than opt-in tweaks — so
this is arkenfox's baseline, not its more aggressive optional layers (full
`resistFingerprinting`, window-size rounding, spoofed `Accept-Language`,
etc., all skipped as too breakage-prone for a daily-driver profile).
Windows/macOS-only prefs (e.g. `geo.provider.ms-windows-location`) and the
"Clear Data" dialog's checkbox defaults (cosmetic only, not enforced) were
dropped as inapplicable on this Linux host.

Translating arkenfox's `user_pref(...)` lines to this repo's
`policies.json`-based `settings` table is mechanical (same pref name and
value, `"Status": "default"` throughout — see [Browsers](../browsers.md)),
with one caveat: arkenfox is a `user.js`, reapplied fresh into a Firefox
*profile* on every launch, while `settings` here is a one-time root-owned
write at package install time. A profile-level override (about:config, an
extension, sync) sticks around across restarts instead of being
overwritten back on the next launch the way arkenfox's own `user.js`
would. Re-running `run_once_before_17-configure-browsers.sh.tmpl` (e.g.
via `chezmoi init --apply`, since `run_once_` scripts only re-run when
their rendered content changes) rewrites `policies.json`, but doesn't
touch prefs a profile has since changed by hand.

Practical effects worth knowing about, since none of these are hidden
behind an opt-in flag the way [SSH hardening](../ssh-hardening.md)'s
password-auth lockout risk is:

- **New tab is blank**, sponsored tiles and Firefox Suggest are off.
- **No disk cache** (`browser.cache.disk.enable`) — pages re-fetch assets
  every load instead of reading them back from disk.
- **HTTPS-Only mode** is on — plain HTTP sites get an interstitial
  click-through instead of loading directly.
- **Enhanced Tracking Protection is forced to `strict`** — occasionally
  breaks an embed (comments widgets, some video players) that relies on a
  cross-site cookie ETP strict blocks.
- **Cache, cookies, and form data are wiped on every browser close**
  (`privacy.sanitize.sanitizeOnShutdown`) — every site needs a fresh login
  each session. Browsing history and downloads are deliberately *not*
  wiped — that's arkenfox's own default split, not an oversight.
- **DNS prefetching, link preconnect, and search suggestions are all
  off** — the trade is a small amount of perceived latency (no
  head-start network connections) for not leaking every hovered link and
  keystroke to a resolver or search provider ahead of an actual navigation.

None of this is locked (see [Browsers](../browsers.md)) — a setting that's
too disruptive for daily use can be flipped back by hand in
`about:config`, or removed from `hyper-lin.browsers.firefox.settings` in
`.hosts.toml` so the next `chezmoi init --apply` stops re-asserting it.

[arkenfox]: https://github.com/arkenfox/user.js
