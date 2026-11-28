"""Dictionnaire des fonctions : nom logique d'une fonction de l'avion → branchement simulateur.

Les profils d'avion désignent ce qu'ils pilotent par un nom logique (« transpondeur.code »,
« pa.mode.hdg », « volets.angle ») plutôt que par un dataref ou une commande. Le
dictionnaire dit comment chaque fonction s'obtient dans le simulateur :

- base : config/dictionnaire/<simulateur>.yaml (ex. xplane.yaml, datarefs et commandes
  standard d'X-Plane, valables pour tous les avions qui utilisent les systèmes standard) ;
- avion : section « fonctions: » d'un fichier du dossier de l'avion, qui ajoute ou
  remplace des fonctions (boutons propres à l'avion, ex. BAe 146 de Thranda).

Une entrée :

    transpondeur.mode:
      description: mode du transpondeur
      dataref: sim/cockpit2/radios/actuators/transponder_mode
      valeurs: {"OFF": 0, STBY: 1, "ON": 2, ALT: 3}
      verifie: 2026-11-14, Boeing 737-800 Laminar

Champs de branchement : dataref, valeurs, commande, commande_on, commande_off, bascule,
etat, etat_on, echelle. Champs de documentation (ignorés par le moteur) : description,
unite, verifie.

Deux usages dans un profil :
- « fonction: transpondeur.mode » sur une commande : les champs de branchement de l'entrée
  deviennent ses paramètres (dataref, dataref_values…), sauf ceux que la commande donne
  elle-même ;
- un nom logique à la place d'un dataref ou d'une commande (« dataref: volets.angle »,
  « 25: pa.mode.hdg » dans les poussoirs, « HDG SEL: pa.mode.hdg.voyant » dans les
  voyants). Un nom qui contient « / » est un vrai dataref ou une vraie commande : il est
  gardé tel quel.
"""

import difflib
import os
from pathlib import Path

import yaml

DICTIONARY_DIR = Path(__file__).resolve().parents[2] / "config" / "dictionnaire"

# champ du dictionnaire → paramètre de la commande, pour « fonction: »
FIELD_TO_PARAM = {
    "dataref": "dataref", "valeurs": "dataref_values", "commande_on": "command_on",
    "commande_off": "command_off", "bascule": "toggle_command", "etat": "state_dataref",
    "etat_on": "state_on", "echelle": "scale",
}
BINDING_FIELDS = set(FIELD_TO_PARAM) | {"commande"}
DOC_FIELDS = {"description", "unite", "verifie"}

# paramètres qui attendent un dataref ou une commande : un nom logique y est résolu
DATAREF_PARAMS = {"dataref", "state_dataref", "mach_dataref", "blank_unless", "source"}
DATAREF_LIST_PARAMS = {"datarefs"}          # liste de datarefs (manette des gaz → moteurs)
COMMAND_PARAMS = {"command_on", "command_off", "toggle_command"}
# commandes dont un paramètre est un tableau {nom: commande ou dataref}
TABLES = {"commands": ("inputs", "commande"), "keypad": ("keys", "commande"),
          "sim_leds": ("leds", "dataref"), "iocp_outputs": ("variables", "dataref")}


class DictionaryError(ValueError):
    pass


def is_logical(name):
    return isinstance(name, str) and "/" not in name


def load_base(simulator, folder=DICTIONARY_DIR):
    """Fonctions de base d'un simulateur ({} si son dictionnaire n'existe pas)."""
    path = Path(folder) / f"{simulator}.yaml"
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return check(data.get("fonctions") or {}, os.path.basename(path))


def check(functions, where):
    """Vérifie les entrées : {nom: {champ: valeur}} avec au moins un champ de branchement."""
    out = {}
    for name, entry in functions.items():
        if not isinstance(entry, dict):
            raise DictionaryError(f"{where} : fonction « {name} » : il faut des champs"
                                  " (dataref, commande…)")
        unknown = set(entry) - BINDING_FIELDS - DOC_FIELDS
        if unknown:
            raise DictionaryError(f"{where} : fonction « {name} » : champs inconnus"
                                  f" {sorted(unknown)} (connus : {sorted(BINDING_FIELDS | DOC_FIELDS)})")
        if not set(entry) & BINDING_FIELDS:
            raise DictionaryError(f"{where} : fonction « {name} » sans dataref ni commande")
        out[str(name)] = dict(entry)
    return out


class Dictionary:
    def __init__(self, functions=None, origin=None):
        self.functions = dict(functions or {})
        self.origin = dict(origin or {})       # nom → fichier d'où vient l'entrée

    def extend(self, functions, where):
        for name, entry in check(functions, where).items():
            self.functions[name] = entry
            self.origin[name] = where

    def entry(self, name, where):
        if name not in self.functions:
            close = difflib.get_close_matches(name, self.functions, n=3)
            hint = f" (vouliez-vous {', '.join(close)} ?)" if close else ""
            raise DictionaryError(f"{where} : fonction « {name} » absente du dictionnaire{hint}")
        return self.functions[name]

    def field(self, name, field, where):
        """Dataref ou commande d'une fonction, pour un paramètre qui n'attend que cela."""
        entry = self.entry(name, where)
        if field not in entry:
            kinds = ", ".join(sorted(set(entry) & BINDING_FIELDS))
            raise DictionaryError(f"{where} : fonction « {name} » : pas de {field} ici"
                                  f" (elle a : {kinds})")
        return entry[field]

    # ------------------------------------------------------------ résolution d'un contrôle
    def resolve(self, spec, where):
        """Paramètres d'une commande du profil → mêmes paramètres, noms logiques résolus."""
        spec = dict(spec)
        function = spec.pop("fonction", None)
        if function is not None:
            entry = self.entry(function, where)
            if "commande" in entry and not set(entry) & set(FIELD_TO_PARAM):
                raise DictionaryError(f"{where} : fonction « {function} » est une simple"
                                      " commande : la citer dans un poussoir ou command_on")
            for field, param in FIELD_TO_PARAM.items():
                if field in entry and param not in spec:
                    spec[param] = entry[field]
        for param in DATAREF_PARAMS:
            if is_logical(spec.get(param)):
                spec[param] = self.field(spec[param], "dataref", f"{where}.{param}")
        for param in DATAREF_LIST_PARAMS:
            if isinstance(spec.get(param), list):
                spec[param] = [self.field(v, "dataref", f"{where}.{param}") if is_logical(v) else v
                               for v in spec[param]]
        for param in COMMAND_PARAMS:
            if is_logical(spec.get(param)):
                spec[param] = self.field(spec[param], "commande", f"{where}.{param}")
        table = TABLES.get(spec.get("type"))
        if table is not None and isinstance(spec.get(table[0]), dict):
            key, field = table
            spec[key] = {k: (self.field(v, field, f"{where}.{key}.{k}") if is_logical(v) else v)
                         for k, v in spec[key].items()}
        return spec

    # ------------------------------------------------------------ consultation
    def describe(self, filter_text=""):
        """Lignes lisibles, une fonction par bloc, triées par nom ; `filter_text` restreint
        aux fonctions dont le nom ou la description le contient."""
        wanted = filter_text.casefold()
        lines = []
        for name in sorted(self.functions):
            entry = self.functions[name]
            if wanted and wanted not in name.casefold() \
                    and wanted not in str(entry.get("description", "")).casefold():
                continue
            head = name + (f"  ({entry['unite']})" if entry.get("unite") else "")
            lines.append(head)
            if entry.get("description"):
                lines.append(f"    {entry['description']}")
            for field in ("dataref", "valeurs", "commande", "commande_on", "commande_off",
                          "bascule", "etat", "etat_on", "echelle"):
                if field in entry:
                    lines.append(f"    {field:<12} {entry[field]}")
            origin = self.origin.get(name, "")
            lines.append(f"    source       {origin}"
                         + (f" ; vérifié {entry['verifie']}" if entry.get("verifie") else ""))
        return lines
