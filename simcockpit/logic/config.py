"""Chargement et validation de cockpit.yaml."""

from dataclasses import dataclass, field

import yaml

from ..hw import mcp
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


class ConfigError(ValueError):
    pass


def load(path):
    with open(path) as f:
        return parse(yaml.safe_load(f) or {})


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
            if hasattr(ctrl, "led_states") and out != "mcp":
                raise ConfigError(f"{iid}.{name} : {ctrl.type} demande une carte MCP")
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
    return Cockpit(cards, instruments)
