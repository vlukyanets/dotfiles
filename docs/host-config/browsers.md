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

[enterprise-policies]: https://mozilla.github.io/policy-templates/
