"""VS Code with the profiles of data/vscode.toml. `code --profile` only uses
a profile that exists and creating one is UI-only, so each is registered in
VS Code's storage.json first, then its extensions come through the CLI.
The shared list goes into the Default profile, flagged the way the UI's
"Apply Extension to all Profiles" does it."""

import copy
import json
import os
import re
import subprocess
from pathlib import Path

from dotfiles import config, engine
from dotfiles.config import ROOT
from dotfiles.engine import (
    RetryPolicy,
    changed,
    defer,
    die,
    ensure_file,
    notice,
    output,
    retrying,
    run,
)
from dotfiles.feature import Feature

# The marketplace answers 5xx now and then, and `code` has no timeout to raise.
MARKETPLACE = RetryPolicy(attempts=5, delay=30, backoff=1.5, max_delay=120)


class Vscode(Feature):
    def apply(self, strategy):
        vscode = config.load(ROOT / "data/vscode.toml", ROOT)["vscode"]
        self.user = Path.home() / ".config/Code/User"
        self.running = _running(Path.home() / ".config/Code/SingletonLock")
        self.failed: list[str] = []
        common = [e.lower() for e in vscode["extensions"]]
        excluded = [e.lower() for e in vscode["excluded"]]
        profiles = vscode["profiles"]

        storage = self._register(profiles)
        self._install("", common)
        installed = self._installed("")
        for id in excluded:
            if id in installed:
                try:
                    run("code", "--uninstall-extension", id, stdout=subprocess.DEVNULL)
                    changed(f"VS Code extension removed: {id}")
                except subprocess.CalledProcessError:
                    self.failed.append(id)
        scoped = self._scope(common, excluded)

        base = json.loads((ROOT / "home/.config/Code/User/settings.json").read_text())
        for name, profile in profiles.items():
            where = self.user / "profiles" / _location(storage, name)
            if "settings" in profile:
                settings = _merged(base, profile["settings"])
                ensure_file(where / "settings.json", json.dumps(settings, indent=4) + "\n")
            self._install(name, [e.lower() for e in profile["extensions"]])
            # An application-scoped extension has no entry of its own in a
            # profile; the ones that got in profile by profile are dropped.
            _rewrite(
                where / "extensions.json",
                lambda entries: [e for e in entries if _id(e) not in scoped],
            )
        if self.failed:
            defer(
                f"VS Code extensions failed for: {' '.join(self.failed)} — profiles and "
                "settings are in place"
            )

    def _register(self, profiles: dict) -> dict:
        """Every profile in storage.json's userDataProfiles; the storage."""
        path = self.user / "globalStorage/storage.json"
        real = engine.path(path)
        storage = json.loads(real.read_text()) if real.exists() else {}
        have = storage.get("userDataProfiles", [])
        want = []
        for name, profile in profiles.items():
            flags = {"keybindings": True, "snippets": True, "tasks": True}
            if "settings" not in profile:  # shares the Default profile's settings.json
                flags["settings"] = True
            want.append({"name": name, "location": _slug(name), "useDefaultFlags": flags})
        missing = [w["name"] for w in want if w["name"] not in {h["name"] for h in have}]
        if not missing:
            return storage
        # storage.json is a running VS Code's state flushed to disk: an edit
        # made under it is lost at its next flush.
        if self.running:
            die(f"VS Code is running and these profiles are not registered yet: {missing} — "
                "close it and apply again")  # fmt: skip
        # A profile already there keeps its entry, so its location; only the
        # flags are set. Unlisted profiles stay.
        known = {h["name"]: h for h in have}
        storage["userDataProfiles"] = [h for h in have if h["name"] not in profiles] + [
            {**known[w["name"]], "useDefaultFlags": w["useDefaultFlags"]}
            if w["name"] in known
            else w
            for w in want
        ]
        ensure_file(path, json.dumps(storage, indent=4) + "\n")
        return storage

    def _installed(self, profile: str) -> set[str]:
        flags = ["--profile", profile] if profile else []
        return set((output("code", *flags, "--list-extensions") or "").lower().split())

    def _install(self, profile: str, ids: list[str]) -> None:
        """IDS in PROFILE ("" is Default); a failure is collected, not raised."""
        missing = [id for id in ids if id not in self._installed(profile)]
        if not missing:
            return
        flags = ["--profile", profile] if profile else []
        installs = [arg for id in missing for arg in ("--install-extension", id)]
        try:
            for attempt in retrying(MARKETPLACE):
                with attempt:
                    run("code", *flags, *installs, stdout=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            self.failed.append(profile or "Default")
            return
        changed(f"VS Code {profile or 'Default'} profile extensions installed: {' '.join(missing)}")

    def _scope(self, common: list[str], excluded: list[str]) -> set[str]:
        """COMMON and the members of the packs among them, transitively, flagged
        isApplicationScoped in extensions.json: every profile sees them."""
        extensions = Path.home() / ".vscode/extensions"
        index = engine.path(extensions / "extensions.json")
        entries = json.loads(index.read_text()) if index.exists() else []
        folders = {_id(e): e.get("relativeLocation") or Path(e["location"]["path"]).name
                   for e in entries}  # fmt: skip
        scoped: set[str] = set()
        queue = list(common)
        while queue:
            id = queue.pop()
            if id in scoped or id in excluded:
                continue
            scoped.add(id)
            package = engine.path(extensions / folders.get(id, "?") / "package.json")
            if id in folders and package.exists():
                queue += [
                    m.lower() for m in json.loads(package.read_text()).get("extensionPack", [])
                ]

        def flag(entries):
            for entry in entries:
                if _id(entry) in scoped:
                    entry.setdefault("metadata", {})["isApplicationScoped"] = True
            return entries

        if _rewrite(extensions / "extensions.json", flag) and self.running:
            notice("VS Code is running — the extension changes take effect at its next start")
        return scoped

    class Arch:
        def packages(self):
            return ["visual-studio-code-bin"]


def _id(entry: dict) -> str:
    return entry["identifier"]["id"].lower()


def _rewrite(path: Path, change) -> bool:
    """The JSON list at PATH through CHANGE, written back when that changed
    anything; compared as data, since VS Code writes it without spaces."""
    real = engine.path(path)
    if not real.exists():
        return False
    before = json.loads(real.read_text())
    after = change(copy.deepcopy(before))
    return after != before and ensure_file(path, json.dumps(after))


def _merged(base: dict, over: dict) -> dict:
    """OVER on top of BASE, tables merged recursively."""
    merged = copy.deepcopy(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merged(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _slug(name: str) -> str:
    """A profile's directory under User/profiles: VS Code picks a random hex
    id, a slug of the name is easier to find."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _location(storage: dict, name: str) -> str:
    """Where profile NAME lives: the slug for one registered here, whatever
    VS Code picked for one adopted from the UI."""
    for profile in storage.get("userDataProfiles", []):
        if profile["name"] == name:
            where = profile["location"]
            return where if isinstance(where, str) else Path(where["path"]).name
    return _slug(name)  # a dry run registered nothing


def _running(lock: Path) -> bool:
    """Chromium's SingletonLock points at "<host>-<pid>" of a running VS Code."""
    try:
        pid = int(os.readlink(lock).rsplit("-", 1)[1])
        os.kill(pid, 0)
    except (OSError, ValueError, IndexError):
        return False
    return True
