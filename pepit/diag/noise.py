"""Mesure des entrées instables : compte les bascules brutes (sans anti-rebond)."""

import time

from ..hw import mastercard
from ..hw.hidraw import HidDevice


def measure(detected, seconds=10.0):
    """Écoute `seconds` secondes. Retourne (bascules par entrée, dernier état brut)."""
    flips = [0] * mastercard.INPUTS
    dec, prev = mastercard.Decoder(), None
    with HidDevice(detected.info.path) as dev:
        dev.write(mastercard.init_packet(1, detected.type.axes))
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            pkt = dev.read(timeout=0.2)
            if pkt and dec.feed(pkt).inputs_changed:
                cur = dec.inputs()
                if prev is not None:
                    for i in range(len(cur)):
                        flips[i] += prev[i] != cur[i]
                prev = cur
    return flips, prev


def report(flips, state, inputs=mastercard.INPUTS):
    """Grille texte : nombre de bascules par entrée ('.' = stable)."""
    lines = []
    for slot in range((inputs + 8) // 9):
        cells = []
        for b in range(9):
            i = 9 * slot + b
            if i < inputs:
                cells.append(f"{i:2d}:{'.' if not flips[i] else flips[i]:>4}")
        lines.append("  " + "  ".join(cells))
    if state is None:
        lines.append("Aucun état reçu : la carte n'a envoyé aucune entrée.")
    else:
        noisy = [i for i in range(inputs) if flips[i]]
        lines.append(f"Instables : {noisy if noisy else 'aucune'}")
    return "\n".join(lines)
