"""Chargement et validation de la configuration du cockpit.

Deux formes :
- un fichier unique (cartes + instruments + liaison simulateur) ;
- un dossier d'avion (ex. config/avions/b738-laminar/) : chaque fichier .yaml du dossier
  apporte des instruments (et éventuellement `sim:`), et les cartes viennent du fichier
  `materiel.yaml` trouvé dans le dossier ou l'un de ses parents. Seules les cartes
  utilisées par les instruments sont ouvertes.
"""

import os
from dataclasses import dataclass, field

import yaml

MATERIEL = "materiel.yaml"

from ..hw import mcp, usbfmc
from ..hw.cards import KNOWN, classify
from . import controls


@dataclass
class CardSpec:
    id: str
    product: str
    usb_port: str = None


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
    data = {"cards": dict(_read(materiel).get("cards") or {}), "instruments": {}}
    files = sorted(f for f in os.listdir(path) if f.endswith((".yaml", ".yml")) and f != MATERIEL)
    if not files:
        raise ConfigError(f"{path} : aucun fichier .yaml d'instruments")
    for name in files:
        part = _read(os.path.join(path, name))
        for key in part:
            if key not in ("cards", "instruments", "sim"):
                raise ConfigError(f"{name} : section inconnue « {key} »")
        for iid, spec in (part.get("instruments") or {}).items():
            if iid in data["instruments"]:
                raise ConfigError(f"{name} : instrument « {iid} » déjà défini dans un autre fichier")
            data["instruments"][iid] = spec
        data["cards"].update(part.get("cards") or {})      # carte propre à cet avion
        if "sim" in part:
            if "sim" in data:
                raise ConfigError(f"{name} : section sim déjà définie dans un autre fichier")
            data["sim"] = part["sim"]
    used = {spec.get("card") for spec in data["instruments"].values()}
    data["cards"] = {cid: c for cid, c in data["cards"].items() if cid in used}
    return parse(data)


def parse(data):
    products = {p for c in KNOWN for p in c.products}
    cards = {}
    for cid, spec in (data.get("cards") or {}).items():
        if spec.get("product") not in products:
            raise ConfigError(f"carte {cid} : produit {spec.get('product')!r} inconnu"
                              f" (connus : {sorted(products)})")
        cards[cid] = CardSpec(cid, spec["product"], spec.get("usb_port"))
    instruments = {}
    for iid, spec in (data.get("instruments") or {}).items():
        card = spec.get("card")
        if card not in cards:
            raise ConfigError(f"instrument {iid} : carte {card!r} non déclarée dans « cards »")
        ctrls = {}
        used = {}
        for name, cspec in (spec.get("controls") or {}).items():
            try:
                ctrl = controls.make(name, cspec)
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
        if not isinstance(sim, dict) or sim.get("type", "xplane") != "xplane":
            raise ConfigError("sim : seul « type: xplane » est pris en charge")
        sim = {"type": "xplane", "host": sim.get("host", "127.0.0.1"),
               "port": int(sim.get("port", 49000))}
    return Cockpit(cards, instruments, sim)
