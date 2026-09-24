"""Firefox with the about:config defaults of
data/firefox-privacy-config.toml as a distribution policy: every value a
new default, nothing locked."""

import json

from dotfiles import config
from dotfiles.config import ROOT
from dotfiles.engine import ensure_file
from dotfiles.feature import Feature


class Firefox(Feature):
    def apply(self, strategy):
        prefs = config.load(ROOT / "data/firefox-privacy-config.toml", ROOT)["firefox"]["prefs"]
        policy = {
            "policies": {
                "Preferences": {
                    name: {"Value": value, "Status": "default"}
                    for name, value in sorted(prefs.items())
                }
            }
        }
        text = json.dumps(policy, indent=2, ensure_ascii=False) + "\n"
        ensure_file(strategy.firefox_policies(), text, owner="root:root")

    class Arch:
        def packages(self):
            return ["firefox"]

        def firefox_policies(self):
            return "/usr/lib/firefox/distribution/policies.json"
