#!/usr/bin/env python3
"""Test minimal : lire les interrupteurs d'une OpenCockpits USB Expansion + 1 Master Card.

Protocole déduit de xpiocards (libiocards.c) et validé sur des trames réelles :
  octet 0 : bits 0-3 = cartes concernées, bits 4-6 = n° d'axe A/D, bit 7 = continuation
  [octet axe si bits 4-6 != 0]
  1 octet masque = slots (0-7) qui ont CHANGÉ
  1 octet par slot changé (8 entrées, bit 0 = 1re)
  1 octet « 9e entrées » : bit i = i-ème slot présent dans la trame
  le reste du paquet = résidus du paquet précédent, à ignorer.
  Si ça ne tient pas dans 8 octets, la suite arrive dans un paquet commençant par 0x80.
Ctrl+C pour quitter.
"""
import glob
import os
import select
import sys
import time

NCARDS = 1


CARDS = ("IOCardUSB", "USB32I04AD")  # OpenCockpits USB Expansion, EFDE IO32
# Valeur rapportée quand le contact est actionné (EFDE : 0 au repos, observé le 08/11)
ACTIVE_LEVEL = {"IOCardUSB": 0, "USB32I04AD": 1}
ACTIVE = 0


def find_hidraw(names=CARDS):
    for d in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        with open(os.path.join(d, "device/uevent")) as f:
            uevent = f.read()
        for name in names:
            if name in uevent:
                print(f"Carte trouvée : {name}")
                global ACTIVE
                ACTIVE = ACTIVE_LEVEL[name]
                return "/dev/" + os.path.basename(d)
    sys.exit(f"Aucune carte trouvée parmi {names}")


def listen(path, seconds=10.0):
    """Écoute passive : n'envoie RIEN à la carte, affiche les rapports bruts."""
    fd = os.open(path, os.O_RDONLY)
    t0, n = time.monotonic(), 0
    try:
        while (t := time.monotonic() - t0) < seconds:
            if select.select([fd], [], [], 0.2)[0]:
                print(f"{t:8.3f}  RX {os.read(fd, 64).hex(' ')}")
                n += 1
    except KeyboardInterrupt:
        pass
    finally:
        os.close(fd)
    print(f"{n} rapport(s) reçu(s) en écoute passive")


class Decoder:
    def __init__(self):
        self.slots = [0] * 8   # octet courant de chaque slot
        self.ninth = 0         # 9e entrées
        self.buf = []          # octets utiles accumulés
        self.need = 0          # octets utiles attendus

    def feed(self, pkt):
        """Retourne True quand une transmission complète a été appliquée."""
        b0 = pkt[0]
        if b0 & 0x80:                       # continuation
            if not self.need:
                return False
            self.buf += pkt[1:]
        else:                               # nouvelle transmission
            if not (b0 & 0x0F) & 1:         # ne concerne pas la carte 0
                self.need = 0
                return False
            pos = 2 if (b0 >> 4) & 7 else 1
            self.buf = list(pkt[pos:])
            self.need = 1 + bin(self.buf[0]).count("1") + 1  # masque + données + 9e
        if len(self.buf) < self.need:
            return False
        mask, data = self.buf[0], self.buf[1:self.need]
        ninth_byte = data[-1]
        i = 0
        for slot in range(8):
            if mask & (1 << slot):
                self.slots[slot] = data[i]
                # 9e entrées : bit i = i-ème slot PRÉSENT dans la trame (vérifié sur EFDE)
                if (ninth_byte >> i) & 1:
                    self.ninth |= 1 << slot
                else:
                    self.ninth &= ~(1 << slot)
                i += 1
        self.need = 0
        return True

    def inputs(self):
        out = []
        for slot in range(8):
            out += [(self.slots[slot] >> b) & 1 for b in range(8)]
            out.append((self.ninth >> slot) & 1)
        return out  # index = 9*slot + bit, 72 entrées


def main():
    path = find_hidraw()
    # --listen [s] : écoute sans envoyer d'init (sûr pour une carte inconnue)
    if len(sys.argv) > 1 and sys.argv[1] == "--listen":
        return listen(path, float(sys.argv[2]) if len(sys.argv) > 2 else 10.0)
    fd = os.open(path, os.O_RDWR)
    init = bytes([0x3D, 0x00, 0x3A, NCARDS, 0x39, 0x00, 0xFF, 0xFF])
    try:
        os.write(fd, b"\x00" + init)
    except OSError as e:
        os.close(fd)
        sys.exit(f"Échec de l'init ({e}). La carte ne répond pas : vérifie "
                 "`journalctl -k | tail` (déconnexion ?), débranche/rebranche l'USB, "
                 "et contrôle qu'aucun fil ne court-circuite le 5 V de la Master Card.")
    print(f"{path} ouvert, init envoyé : {init.hex(' ')}")

    # --diag N : ne rien toucher pendant N secondes, puis bilan des entrées instables
    diag = float(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--diag" else None
    flips = [0] * 72

    # --watch [ms] : n'affiche que les entrées restées stables au moins `ms` (défaut 200)
    # --xpdr : comme --watch 50, et affiche le code transpondeur (3 entrées binaires par chiffre)
    watch = None
    xpdr = len(sys.argv) > 1 and sys.argv[1] == "--xpdr"
    if xpdr:
        watch = 0.05
    elif len(sys.argv) > 1 and sys.argv[1] == "--watch":
        watch = (float(sys.argv[2]) if len(sys.argv) > 2 else 200.0) / 1000
    raw = [None] * 72          # dernière valeur brute
    since = [0.0] * 72         # instant du dernier changement brut
    stable = [None] * 72       # dernière valeur stable annoncée

    dec, prev, t0 = Decoder(), None, time.monotonic()
    try:
        while True:
            t = time.monotonic() - t0
            if diag and t > diag:
                break
            ready = select.select([fd], [], [], 0.02 if watch else 1.0)[0]
            if watch:
                if ready and dec.feed(os.read(fd, 8)):
                    for i, v in enumerate(dec.inputs()):
                        if v != raw[i]:
                            raw[i], since[i] = v, t
                t = time.monotonic() - t0
                first = []
                for i in range(72):
                    if raw[i] is not None and raw[i] != stable[i] and t - since[i] >= watch:
                        if stable[i] is None:
                            first.append(i)
                        else:
                            etat = (f"ACTIVÉE ({raw[i]})" if raw[i] == ACTIVE
                                    else f"repos ({raw[i]})")
                            print(f"{t:8.3f}  entrée {i:2d} -> {etat}")
                        stable[i] = raw[i]
                if first:
                    print(f"{t:8.3f}  stables : à 0 {[i for i in first if not raw[i]]}"
                          f" / à 1 {[i for i in first if raw[i]]}")
                if xpdr and None not in stable[:14]:
                    act = [int(v == ACTIVE) for v in stable[:14]]
                    code = "".join(str(act[b] | act[b + 1] << 1 | act[b + 2] << 2)
                                   for b in (0, 3, 6, 9))
                    etat = (code, act[12], act[13])
                    if etat != getattr(main, "last_xpdr", None):
                        main.last_xpdr = etat
                        # entrée 12 = ON, entrée 13 = STBY ; en ON, le contact STBY reste fermé
                        mode = "ON" if act[12] else "STBY" if act[13] else "OFF"
                        print(f"{t:8.3f}  TRANSPONDEUR {code}  {mode}")
                continue
            if not ready:
                continue
            pkt = os.read(fd, 8)
            if diag:
                if dec.feed(pkt):
                    cur = dec.inputs()
                    if prev:
                        for i in range(72):
                            flips[i] += prev[i] != cur[i]
                    prev = cur
                continue
            print(f"{t:8.3f}  RX {pkt.hex(' ')}")
            if not dec.feed(pkt):
                continue
            cur = dec.inputs()
            if prev is not None:
                ch = [f"{i}->{v}" for i, (p, v) in enumerate(zip(prev, cur)) if p != v]
                if ch:
                    print("          ", " ".join(ch))
            else:
                print("           état initial, actives :", [i for i, v in enumerate(cur) if v])
            prev = cur
    except KeyboardInterrupt:
        pass
    finally:
        os.close(fd)
    if diag and prev:
        print(f"Bilan sur {diag:.0f} s (bascules par entrée, '.' = stable) :")
        for slot in range(8):
            cells = []
            for b in range(9):
                i = 9 * slot + b
                cells.append(f"{i:2d}:{'.' if not flips[i] else flips[i]:>4}")
            print("  " + "  ".join(cells))
        print("Stables à 1 :", [i for i in range(72) if not flips[i] and prev[i]])


if __name__ == "__main__":
    main()
