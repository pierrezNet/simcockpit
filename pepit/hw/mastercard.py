"""Protocole « Master Card » OpenCockpits (aussi utilisé par l'EFDE IO32).

Rétro-ingénierie sur trames réelles (EFDE USB32I04AD, OpenCockpits IOCardUSB),
guidée par la lecture de xpiocards/libiocards.c. Format d'un rapport de 8 octets :

  octet 0 : bits 0-3 = Master Cards concernées, bits 4-6 = n° d'axe (0 = aucun),
            bit 7 = continuation de la transmission précédente
  [octet axe : valeur 0-255 si bits 4-6 != 0]
  octet masque : slots (0-7) dont l'état a CHANGÉ
  1 octet par slot du masque : 8 entrées, bit 0 = entrée 9*slot
  1 octet « 9e entrées » : bit i = 9e entrée (9*slot+8) du i-ème slot présent
  reste du rapport : résidus du rapport précédent, à ignorer

Limitation connue : une seule Master Card est décodée (carte 0).
"""

from dataclasses import dataclass, field

SLOTS = 8
INPUTS = 9 * SLOTS  # 72


FIRST_OUTPUT = 11      # numérotation SIOC des sorties : 11, 12, …
OUTPUTS_PER_SEGMENT = 8


def output_report(segment, bits, card=0) -> bytes:
    """Rapport pour 8 sorties : adresse = carte*64 + segment*8 + 11, puis l'octet des 8 sorties.

    D'après la lecture de libiocards.c (send_mastercard) ; bit à 1 = sortie à 1.
    La polarité physique (1 = allumée ?) n'est PAS vérifiée : c'est le rôle de output_check.
    """
    addr = card * 64 + segment * OUTPUTS_PER_SEGMENT + FIRST_OUTPUT
    return bytes([addr & 0xFF, bits & 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])


BLANK = 0x0A   # chiffre éteint
MINUS = 0xF8   # signe moins


def display_reports(digits: dict, card=0, ndisplays=64) -> list:
    """{position: valeur} → rapports de 8 octets, 4 paires [valeur, adresse] chacun.

    Adresse = carte*ndisplays + position. Valeur 0-9, BLANK ou MINUS. D'après
    xpcockpit (send_mastercard) ; vérifié sur l'OpenCockpits IOCard-MCP (positions 0-8).
    Les paires inutilisées sont remplies de 0xFF.
    """
    pairs = [(v & 0xFF, (card * ndisplays + p) & 0xFF) for p, v in sorted(digits.items())]
    reports = []
    for k in range(0, len(pairs), 4):
        chunk = [b for pair in pairs[k:k + 4] for b in pair]
        reports.append(bytes(chunk + [0xFF] * (8 - len(chunk))))
    return reports


def output_location(number):
    """Numéro SIOC de sortie (11, 12…) → (segment, bit)."""
    if number < FIRST_OUTPUT:
        raise ValueError(f"les sorties commencent à {FIRST_OUTPUT}")
    return divmod(number - FIRST_OUTPUT, OUTPUTS_PER_SEGMENT)


def init_packet(ncards=1, naxes=0) -> bytes:
    """Rapport d'initialisation ; sans lui la carte n'envoie que les axes."""
    return bytes([0x3D, 0x00, 0x3A, ncards & 0xFF, 0x39, naxes & 0xFF, 0xFF, 0xFF])


@dataclass
class Update:
    axis: tuple = None          # (n° d'axe 1-4, valeur) si le rapport en contient un
    inputs_changed: bool = False


@dataclass
class Decoder:
    slots: list = field(default_factory=lambda: [0] * SLOTS)
    ninth: int = 0
    seen: bool = False          # au moins un état d'entrées complet reçu
    _buf: list = field(default_factory=list)
    _need: int = 0

    def feed(self, pkt: bytes) -> Update:
        upd = Update()
        if not pkt:
            return upd
        b0 = pkt[0]
        if b0 & 0x80:                                   # continuation
            if not self._need:
                return upd
            self._buf += pkt[1:]
        else:
            axis = (b0 >> 4) & 7
            if axis:
                upd.axis = (axis, pkt[1])
            if not (b0 & 0x01):                         # rien pour la carte 0
                self._need = 0
                return upd
            self._buf = list(pkt[2 if axis else 1:])
            self._need = 1 + bin(self._buf[0]).count("1") + 1
        if len(self._buf) < self._need:
            return upd
        mask, data = self._buf[0], self._buf[1:self._need]
        ninth_byte = data[-1]
        i = 0
        for slot in range(SLOTS):
            if mask & (1 << slot):
                self.slots[slot] = data[i]
                if (ninth_byte >> i) & 1:
                    self.ninth |= 1 << slot
                else:
                    self.ninth &= ~(1 << slot)
                i += 1
        self._need = 0
        self.seen = True
        upd.inputs_changed = True
        return upd

    def inputs(self) -> list:
        """État brut des 72 entrées, index SIOC = 9*slot + bit."""
        out = []
        for slot in range(SLOTS):
            out += [(self.slots[slot] >> b) & 1 for b in range(8)]
            out.append((self.ninth >> slot) & 1)
        return out
