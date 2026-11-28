"""Détection et classification des cartes branchées."""

from dataclasses import dataclass

from .cards import UNKNOWN, CardType, classify, maker
from .hidraw import HidInfo, enumerate_hid


@dataclass(frozen=True)
class Detected:
    info: HidInfo
    type: CardType

    @property
    def known(self):
        return self.type is not UNKNOWN

    @property
    def maker(self):
        return maker(self.info.manufacturer)

    @property
    def cockpit(self):
        """Carte de cockpit : modèle connu, ou fabricant de cockpit (modèle non pris en charge)."""
        return self.known or self.maker is not None

    @property
    def label(self):
        if self.known:
            return self.type.label
        if self.maker:
            return f"{self.maker} {self.info.product} (non prise en charge, écoute seule)"
        return f"{self.info.hid_name or self.info.product} (inconnu)"


def scan(include_unknown=False):
    """Cartes de cockpit présentes, y compris les modèles non pris en charge de fabricants
    de cockpit. `include_unknown` ajoute tous les autres périphériques HID (claviers…)."""
    found = [Detected(info, classify(info.product)) for info in enumerate_hid()]
    return [d for d in found if include_unknown or d.cockpit]


def find(port=None):
    """Première carte PRISE EN CHARGE, ou celle branchée sur le port USB donné (ex. « 1-14 »)."""
    for d in scan():
        if (port is None and d.known) or (port is not None and d.info.usb_port == port):
            return d
    return None
