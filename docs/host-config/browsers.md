# Browsers

[`.chezmoiscripts/run_once_before_16-configure-browsers.sh.tmpl`](../../.chezmoiscripts/run_once_before_16-configure-browsers.sh.tmpl)
installs whatever's listed under `browsers.<name>` (default `{}` — no
entries, script exits immediately). Each entry is independent: its own
pacman package, installed with its own `pacman -S --needed` call, so one
host can list several browsers (or several channels of the same one, e.g.
`firefox` and `firefox-nightly`) side by side. `<name>` itself is just a
label for log output — pick anything; it doesn't have to match the package
name.

## Settings

A `browsers.<name>.settings` table (default `{}` — none) maps an
about:config preference name to the value it should default to, e.g.:

```toml
[hyper-lin.browsers.firefox]
package = "firefox"
[hyper-lin.browsers.firefox.settings]
"browser.aboutConfig.showWarning" = false
"browser.tabs.warnOnClose"        = false
```

These are written into
`/usr/lib/<package>/distribution/policies.json` (root-owned, `pacman
-S`-installed browser layout — see [System files](system-files.md) for the
repo's other, unrelated use of a similar "drop a file next to the package"
approach) as a Firefox [distribution policy][enterprise-policies]:

```json
{
  "policies": {
    "Preferences": {
      "browser.aboutConfig.showWarning": { "Value": false, "Status": "default" },
      "browser.tabs.warnOnClose": { "Value": false, "Status": "default" }
    }
  }
}
```

Every preference is written with `"Status": "default"`, not `"locked"` —
this replaces the pref's *default* value (the same effect as shipping a
`user.js`), but leaves it fully changeable afterward in `about:config` or
via the browser's own settings UI. `"locked"` (grey/disabled in
`about:config`, can't be changed even by the user) isn't exposed here on
purpose: this repo's own [SSH hardening](ssh-hardening.md) script is the
one place config already forecloses a choice outright, and only because
getting it wrong there is a lockout risk. A browser preference isn't — so
this stays overridable rather than adding a second policy shape
(`locked` vs. `default`) for a distinction nothing here needs yet.

A browser entry with no `settings` table at all (like `librewolf` in
`.hosts.toml`'s example block) just gets installed — no
`/usr/lib/<package>/distribution/` directory is touched.

## Caveat: package layout

`/usr/lib/<package>/distribution/policies.json` assumes the installed
package's directory under `/usr/lib/` matches `package` exactly — true for
Arch's own `firefox` and for Firefox-based AUR packages that follow the
same convention (e.g. `librewolf`, `floorp`). The script doesn't check this
before writing: with a `settings` table given, it always creates
`/usr/lib/<package>/distribution/` and writes `policies.json` into it,
regardless of where the package actually put its binary. For a browser
that installs somewhere else, or isn't Firefox-based and doesn't read
`policies.json` at all, that write just lands somewhere the browser never
looks — harmless, but no different from not having set `settings`. Such a
browser can still be listed, just without a `settings` table, for the
install alone.

## hyper-lin: Firefox

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
value, `"Status": "default"` throughout — see above), with one caveat:
arkenfox is a `user.js`, reapplied fresh into a Firefox *profile* on every
launch, while `settings` here is a one-time root-owned write at package
install time. A profile-level override (about:config, an extension, sync)
sticks around across restarts instead of being overwritten back on the
next launch the way arkenfox's own `user.js` would. Re-running
`run_once_before_16-configure-browsers.sh.tmpl` (e.g. via `chezmoi init
--apply`, since `run_once_` scripts only re-run when their rendered
content changes) rewrites `policies.json`, but doesn't touch prefs a
profile has since changed by hand.

Practical effects worth knowing about, since none of these are hidden
behind an opt-in flag the way [SSH hardening](ssh-hardening.md)'s
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

None of this is locked (see above) — a setting that's too disruptive for
daily use can be flipped back by hand in `about:config`, or removed from
`hyper-lin.browsers.firefox.settings` in `.hosts.toml` so the next
`chezmoi init --apply` stops re-asserting it.

[arkenfox]: https://github.com/arkenfox/user.js
[enterprise-policies]: https://mozilla.github.io/policy-templates/
