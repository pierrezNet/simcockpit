"""Noms donnés par l'utilisateur à ses périphériques (« Écran des vitesses (LilyGo) »).

Rangés dans ~/.config/pepit/noms.yaml, par clé de périphérique :
- USB : « VID:PID:numéro de série », ou « VID:PID@prise » sans numéro de série ;
- wifi : « wifi:adresse MAC ».
Un nom vide efface le nom choisi : le périphérique reprend le nom qu'il annonce.
"""

import os

import yaml


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "pepit")


class Names:
    def __init__(self, path=None):
        self.path = path or os.path.join(config_dir(), "noms.yaml")
        self.names = {}
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            data = {}
        self.names = {str(k): str(v) for k, v in data.items()
                      if isinstance(data, dict) and str(v).strip()}

    def get(self, key, default=""):
        return self.names.get(key, default)

    def set(self, key, name):
        name = " ".join((name or "").split())          # espaces et retours à la ligne réduits
        if name:
            self.names[key] = name
        else:
            self.names.pop(key, None)
        self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("# Pepit : noms donnés aux périphériques (page Périphériques, « Renommer »)\n")
            yaml.safe_dump(dict(sorted(self.names.items())), f, allow_unicode=True,
                           sort_keys=False)
        os.replace(tmp, self.path)
