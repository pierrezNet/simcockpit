"""Protocole « bitmap » : chaque rapport est l'état COMPLET de 64 entrées (8 octets × 8 bits).

Observé sur l'OpenCockpits IOCard-MCP le 2026-11-08 : après l'init Master
(3d 00 3a 01 39 00 ff ff), la carte envoie un rapport toutes les ~40 ms, qu'il y ait
un changement ou non. Index d'entrée = 8 × octet + bit. Les encodeurs rotatifs
apparaissent comme des paires de bits en code Gray (00 → 01 → 11 → 10).
"""

from .mastercard import INPUTS, Update

BITS = 64


class BitmapDecoder:
    def __init__(self):
        self.state = None

    def feed(self, pkt: bytes) -> Update:
        upd = Update()
        if not pkt or len(pkt) < 8:
            return upd
        new = bytes(pkt[:8])
        if new != self.state:
            self.state = new
            upd.inputs_changed = True
        return upd

    @property
    def seen(self):
        return self.state is not None

    def inputs(self) -> list:
        """64 entrées (index 8*octet+bit), complétées à 72 pour partager les outils Master."""
        if self.state is None:
            return [0] * INPUTS
        bits = [(self.state[i // 8] >> (i % 8)) & 1 for i in range(BITS)]
        return bits + [0] * (INPUTS - BITS)
