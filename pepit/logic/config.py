"""Chargement et validation de la configuration du cockpit.

Deux formes :
- un fichier unique (cartes + instruments + liaison simulateur) ;
- un dossier d'avion (ex. config/avions/b738-laminar/) : chaque fichier .yaml du dossier
  apporte des instruments (et éventuellement `sim:` ou `fonctions:`), et les cartes
  viennent du fichier `materiel.yaml` trouvé dans le dossier ou l'un de ses parents.
  Seules les cartes utilisées par les instruments sont ouvertes.

Les noms logiques de fonctions (« fonction: transpondeur.code ») sont résolus avec le
dictionnaire du simulateur (config/dictionnaire/xplane.yaml) complété par les sections
`fonctions:` du profil : voir logic/dictionary.py.
"""

import os
import re
from dataclasses import dataclass, field

import yaml

MATERIEL = "materiel.yaml"

from ..hw import fdbus, mcp, usbfmc
from ..hw.cards import KNOWN, classify
from . import controls
from .dictionary import Dictionary, DictionaryError, load_base


@dataclass
class CardSpec:
    id: str
    product: str
    usb_port: str = None
    tcp_port: int = None      # carte réseau IOCP : port d'écoute (8092 par défaut)


@dataclass
class Instrument:
    id: str
    label: str
    card: str
    controls: dict = field(default_factory=dict)   # nom -> Control


@dataclass
class Cockpit:
    cards: dict
    instruments: dict
    sim: dict = None          # ex. {"type": "xplane", "host": "127.0.0.1", "port": 49000}
    dictionary: Dictionary = None   # fonctions connues (base du simulateur + profil)


class ConfigError(ValueError):
    pass


def _read(path):
    with open(path) as f:
        text = f.read()
    for n, line in enumerate(text.splitlines(), 1):
        if line[:len(line) - len(line.lstrip())].count("\t"):
            raise ConfigError(f"{path}, ligne {n} : tabulation dans l'indentation ;"
                              " YAML n'accepte que des espaces")
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f", ligne {mark.line + 1}" if mark else ""
        raise ConfigError(f"{path}{where} : YAML invalide ({getattr(e, 'problem', e)})") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} : le fichier doit contenir des sections (cards, instruments…)")
    return data


def find_materiel(folder):
    """materiel.yaml du dossier ou du plus proche parent ; None s'il n'y en a pas."""
    folder = os.path.abspath(folder)
    while True:
        candidate = os.path.join(folder, MATERIEL)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(folder)
        if parent == folder:
            return None
        folder = parent


def load(path):
    if not os.path.isdir(path):
        return parse(_read(path))
    materiel = find_materiel(path)
    if materiel is None:
        raise ConfigError(f"{path} : aucun {MATERIEL} dans ce dossier ni au-dessus")
    data = {"cards": dict(_read(materiel).get("cards") or {}), "instruments": {}, "fonctions": {}}
    files = sorted(f for f in os.listdir(path) if f.endswith((".yaml", ".yml")) and f != MATERIEL)
    if not files:
        raise ConfigError(f"{path} : aucun fichier .yaml d'instruments")
    for name in files:
        part = _read(os.path.join(path, name))
        for key in part:
            if key not in ("cards", "instruments", "sim", "fonctions"):
                raise ConfigError(f"{name} : section inconnue « {key} »")
        for iid, spec in (part.get("instruments") or {}).items():
            if iid in data["instruments"]:
                raise ConfigError(f"{name} : instrument « {iid} » déjà défini dans un autre fichier")
            data["instruments"][iid] = spec
        data["cards"].update(part.get("cards") or {})      # carte propre à cet avion
        for fname, entry in (part.get("fonctions") or {}).items():
            if fname in data["fonctions"]:
                raise ConfigError(f"{name} : fonction « {fname} » déjà définie dans un autre fichier")
            data["fonctions"][fname] = entry
            data.setdefault("_fonctions_origine", {})[fname] = \
                f"{os.path.basename(os.path.abspath(path))}/{name}"
        if "sim" in part:
            if "sim" in data:
                raise ConfigError(f"{name} : section sim déjà définie dans un autre fichier")
            data["sim"] = part["sim"]
    used = {spec.get("card") for spec in data["instruments"].values()}
    data["cards"] = {cid: c for cid, c in data["cards"].items() if cid in used}
    return parse(data)


def parse(data, calibrations=None):
    """`calibrations` : jauges FDBUS {(adresse, sortie): Calibration} ; par défaut lues
    dans config/fdbus.yaml (réglées dans le banc de test), seulement si une jauge en a besoin."""
    products = {p for c in KNOWN for p in c.products}
    cards = {}
    for cid, spec in (data.get("cards") or {}).items():
        if spec.get("product") not in products:
            raise ConfigError(f"carte {cid} : produit {spec.get('product')!r} inconnu"
                              f" (connus : {sorted(products)})")
        cards[cid] = CardSpec(cid, spec["product"], spec.get("usb_port"),
                              int(spec["port"]) if spec.get("port") else None)
    dictionary = _dictionary(data)
    instruments = {}
    for iid, spec in (data.get("instruments") or {}).items():
        card = spec.get("card")
        if card not in cards:
            raise ConfigError(f"instrument {iid} : carte {card!r} non déclarée dans « cards »")
        ctrls = {}
        used = {}
        for name, cspec in (spec.get("controls") or {}).items():
            try:
                ctrl = controls.make(name, dictionary.resolve(cspec, f"{iid}.{name}"))
            except DictionaryError as e:
                raise ConfigError(str(e)) from None
            except (TypeError, ValueError) as e:
                raise ConfigError(f"{iid}.{name} : {e}") from None
            out = classify(cards[card].product).out_protocol
            if ctrl.display is not None and (out != "mcp" or ctrl.display not in mcp.DISPLAYS):
                raise ConfigError(f"{iid}.{name} : afficheur {ctrl.display!r} inconnu sur cette carte"
                                  + (f" (connus : {', '.join(mcp.DISPLAYS)})" if out == "mcp" else ""))
            if hasattr(ctrl, "radio_display") and out != "radio_airbus":
                raise ConfigError(f"{iid}.{name} : {ctrl.type} demande une radio OpenCockpits Airbus")
            if hasattr(ctrl, "led_states"):
                names = {"mcp": mcp.LEDS, "usbfmc": usbfmc.LEDS}.get(out)
                if names is None:
                    raise ConfigError(f"{iid}.{name} : {ctrl.type} demande une carte à voyants (MCP, CDU)")
                bad = sorted(set(ctrl.led_states()) - set(names))
                if bad:
                    raise ConfigError(f"{iid}.{name} : voyants inconnus {bad} (connus : {', '.join(names)})")
            if hasattr(ctrl, "resolve"):
                if out != "fdbus":
                    raise ConfigError(f"{iid}.{name} : une jauge demande la carte EFDE FDBUS")
                if calibrations is None:
                    calibrations = fdbus.load_calibrations()
                try:
                    ctrl.resolve(calibrations)
                except ValueError as e:
                    raise ConfigError(f"{iid}.{name} : {e}") from None
            if hasattr(ctrl, "on_key") and out != "usbfmc":
                raise ConfigError(f"{iid}.{name} : {ctrl.type} demande un clavier (CDU)")
            if ctrl.led is not None and (out != "mcp" or ctrl.led not in mcp.LEDS):
                raise ConfigError(f"{iid}.{name} : voyant {ctrl.led!r} inconnu sur cette carte"
                                  + (f" (connus : {', '.join(mcp.LEDS)})" if out == "mcp" else ""))
            for i in ctrl.indexes:
                if i in used:
                    raise ConfigError(f"{iid}.{name} : entrée {i} déjà utilisée par {used[i]}")
                used[i] = name
            ctrls[name] = ctrl
        for name, ctrl in ctrls.items():
            src = getattr(ctrl, "altitude_from", None)
            if src is not None:
                if src not in ctrls or not isinstance(ctrls[src], controls.Encoder):
                    raise ConfigError(f"{iid}.{name} : altitude_from {src!r} n'est pas un encodeur"
                                      " de cet instrument")
                ctrl.altitude_control = ctrls[src]
        instruments[iid] = Instrument(iid, spec.get("label", iid), card, ctrls)
    sim = data.get("sim")
    if sim is not None:
        sim = dict(sim)
        if not isinstance(sim, dict) or sim.get("type", "xplane") != "xplane":
            raise ConfigError("sim : seul « type: xplane » est pris en charge")
        sim = {"type": "xplane", "host": sim.get("host", "127.0.0.1"),
               "port": int(sim.get("port", 49000)),
               "web_port": int(sim.get("web_port", 8086)),     # API web (X-Plane 12.1.1+)
               "aircraft": aircraft_codes(sim.get("avion"))}   # profil choisi selon l'avion
    return Cockpit(cards, instruments, sim, dictionary)


def aircraft_codes(value):
    """`avion: B462` ou `avion: [B461, B462]` → ("B462",) : codes OACI de l'avion du profil."""
    if value is None:
        return ()
    codes = [value] if isinstance(value, str) else value
    if not isinstance(codes, (list, tuple)) or not all(
            isinstance(c, str) and re.fullmatch(r"[A-Za-z0-9]{2,4}", c) for c in codes):
        raise ConfigError(f"sim.avion : code(s) OACI attendu(s) (ex. B462), pas {value!r}")
    return tuple(c.upper() for c in codes)


def _dictionary(data):
    """Dictionnaire des fonctions : base du simulateur déclaré, puis sections `fonctions:`."""
    sim = data.get("sim")
    simulator = sim.get("type", "xplane") if isinstance(sim, dict) else None
    try:
        dictionary = Dictionary()
        if simulator:
            base = load_base(simulator)
            dictionary.extend(base, f"dictionnaire/{simulator}.yaml")
        origin = data.get("_fonctions_origine", {})
        for fname, entry in (data.get("fonctions") or {}).items():
            dictionary.extend({fname: entry}, origin.get(fname, "configuration"))
    except DictionaryError as e:
        raise ConfigError(str(e)) from None
    return dictionary
