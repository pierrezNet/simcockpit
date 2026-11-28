"""Le concentrateur : une seule ouverture par carte, partagée par le cockpit et le banc.

Deux pages qui ouvriraient chacune la même carte se gêneraient (initialisation du bus
FDBUS relancée, afficheurs du MCP réécrits). Le concentrateur ouvre la carte une fois,
la garde ouverte tant qu'elle est branchée, et chacun s'y abonne (`Card.listen`).

Il retient aussi qui pilote la carte (« cockpit ») pour que le banc puisse l'indiquer.
Utilisé depuis le fil de l'interface seulement : pas de verrou.
"""

from . import manager
from .device import Card

DEBOUNCE = 0.03     # anti-rebond commun (le cockpit lit l'état brut, le banc les entrées)


def _identity(detected):
    return (detected.info.product, detected.info.usb_port)


class DeviceHub:
    def __init__(self, scan=manager.scan, make_card=None):
        self._scan = scan
        self._make = make_card or (lambda d: Card(d.info, d.type, debounce=DEBOUNCE,
                                                  raw_events=not d.known, state_events=True,
                                                  shared=True))
        self.present = []          # dernières cartes détectées (manager.Detected)
        self.cards = {}            # chemin hidraw -> Card ouverte
        self._ident = {}           # chemin -> (produit, port) au moment de l'ouverture
        self._drivers = {}         # chemin -> {« cockpit », …}

    def refresh(self):
        """Relit les cartes branchées ; referme celles qui sont parties ou perdues."""
        self.present = self._scan()
        here = {d.info.path: _identity(d) for d in self.present}
        for path, card in list(self.cards.items()):
            if here.get(path) != self._ident[path] or not card.alive:
                self._close(path)
        return self.present

    def open(self, detected):
        """La carte ouverte pour `detected` (ouverte maintenant si besoin).
        Lève PermissionError ou OSError si elle ne peut pas être ouverte."""
        path = detected.info.path
        card = self.cards.get(path)
        if card is not None and (self._ident[path] != _identity(detected) or not card.alive):
            self._close(path)
            card = None
        if card is None:
            card = self._make(detected)
            card.start()                       # lève en cas d'échec : rien n'est retenu
            self.cards[path], self._ident[path] = card, _identity(detected)
        return card

    # ------------------------------------------------------------ qui pilote
    def claim(self, card, who):
        self._drivers.setdefault(card.info.path, set()).add(who)

    def release(self, card, who):
        self._drivers.get(card.info.path, set()).discard(who)

    def drivers(self, card):
        return frozenset(self._drivers.get(card.info.path, ()))

    # ------------------------------------------------------------ fin
    def _close(self, path):
        card = self.cards.pop(path)
        self._ident.pop(path, None)
        self._drivers.pop(path, None)
        card.stop()

    def close(self):
        for path in list(self.cards):
            self._close(path)
