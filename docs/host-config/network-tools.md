# Network tools

[`.chezmoiscripts/run_once_before_26-configure-network-tools.sh.tmpl`](../../.chezmoiscripts/run_once_before_26-configure-network-tools.sh.tmpl)
installs whatever's listed under `network_tools.<name>` with `enabled =
true` (default `{}` — no entries, script exits immediately). It's the
same leaf shape as a [Development](development.md) entry —
`enabled`/`source`/`packages`/`post_install`/`desktop_only`/`groups`, each
with the same meaning — just without development's optional second level
of nesting, since there's no "competing toolchains" case here. `<name>`
is a label for log output only.

It exists as a separate feature, rather than as entries under
`development` or packages in [`cli_tools.enabled`](cli-tools.md), because
network diagnostics aren't tied to any language toolchain, and at least
one of them needs more than a flat list can say: `wireshark-qt` is a Qt
app (`desktop_only`) whose package creates a `wireshark` group that gates
packet capture without root (`groups`). Splitting the CLI tools off into
`cli_tools` and leaving only wireshark here would scatter one category
across two files for no gain, so all of them live together.

hyper-lin's config:

```toml
[hyper-lin.network_tools.nmap]
enabled = true
packages = ["nmap"]

[hyper-lin.network_tools.mtr]
enabled = true
packages = ["mtr"]

[hyper-lin.network_tools.dig]
enabled = true
packages = ["bind"]

[hyper-lin.network_tools.tcpdump]
enabled = true
packages = ["tcpdump"]

[hyper-lin.network_tools.wireshark]
enabled = true
packages = ["wireshark-qt"]
desktop_only = true
groups = ["wireshark"]
```

`dig` is labeled by the command, not the package: Arch ships
`dig`/`host`/`nslookup` inside `bind`, the same package as the `named`
server. Nothing here enables `named.service` — it's installed, and stays
off.

`wireshark-qt` pulls in `wireshark-cli`, so `tshark` comes along on a
desktop host; a headless host that wants `tshark` alone lists
`wireshark-cli` in its own entry, with the same `groups = ["wireshark"]`
and no `desktop_only`. Without the group membership both only see
interfaces under `sudo`; as with [docker](containers.md), a fresh add
takes effect in the next login session, which the script prints as a
reminder.
