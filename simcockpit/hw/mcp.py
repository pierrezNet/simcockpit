"""Sorties de l'OpenCockpits IOCard-MCP : afficheurs 7 segments et LED.

Rétro-ingénierie du 2026-11-08 (webcam + trames d'essai). Ce n'est PAS le format
Master Card. Une trame de 8 octets = 16 demi-octets n0..n15 (octet k → n[2k] dans
sa moitié basse, n[2k+1] dans sa moitié haute) :

  n0..n10 : données (chiffres en pages 0 et 1, bits de LED en page 2)
  n12     : page (0, 1 = afficheurs ; 2 = LED)
  octet 7 : luminosité, inversée (0 = maximum, 0x0f = faible)

Les afficheurs ne restent allumés que tant qu'un programme LIT la carte
(le MCP garde ses valeurs en mémoire et les réaffiche dès qu'on la relit).
"""

DIGIT_BLANK = 0x0A
DIGIT_MINUS = 0x0B

# Afficheur → emplacements (page, demi-octet), du chiffre de gauche au chiffre de droite.
DISPLAYS = {
    "CRS1": [(0, 2), (0, 1), (0, 0)],
    "IAS": [(0, 5), (0, 4), (0, 3)],
    "HDG": [(0, 8), (0, 7), (0, 6)],
    "ALT": [(0, 10), (0, 9), (1, 2), (1, 1), (1, 0)],
    "VS": [(1, 10), (1, 9), (1, 8), (1, 7), (1, 6)],
    "CRS2": [(1, 5), (1, 4), (1, 3)],
}

# Points décimaux : afficheur → (page, demi-octet, masque). Point allumé à droite du
# chiffre de gauche (vérifié à la webcam : IAS « 2.50 » ; « .78 » avec ce chiffre éteint).
# Les autres bits du demi-octet 11 n'allument aucun point visible.
DOTS = {"IAS": (0, 11, 0x8)}

# LED → bit des 16 bits de données de la page 2 (bit 8 inutilisé).
LEDS = {
    "APP": 0, "ALT HLD": 1, "V/S": 2, "CMD A": 3, "CWS A": 4, "CMD B": 5, "CWS B": 6,
    "A/T ARM": 7, "N1": 9, "SPEED": 10, "VNAV": 11, "LVL CHG": 12, "HDG SEL": 13,
    "LNAV": 14, "VOR LOC": 15,
}


def frame(nibbles11, page, brightness=0) -> bytes:
    """Demi-octets de données (n0..n10, et n11 = points décimaux) + n° de page → 8 octets."""
    n = list(nibbles11) + [0] * (16 - len(nibbles11))
    n[12] = page & 0x0F
    data = bytes((n[2 * k] & 0x0F) | ((n[2 * k + 1] & 0x0F) << 4) for k in range(7))
    return data + bytes([brightness & 0xFF])


def format_value(value, width, blank_leading=True):
    """Nombre (ou texte) → codes chiffres de gauche à droite, calés à droite.

    Les zéros de tête sont éteints (sauf le dernier chiffre) ; « - » donne le signe moins ;
    un espace ou None éteint un chiffre. Lève ValueError si la valeur ne tient pas.
    """
    if value is None:
        return [DIGIT_BLANK] * width
    if isinstance(value, int) and not blank_leading:
        text = f"{value:0{width}d}" if value >= 0 else "-" + f"{-value:0{width - 1}d}"
    else:
        text = str(value)
    if len(text) > width:
        raise ValueError(f"« {text} » ne tient pas sur {width} chiffres")
    codes = []
    for ch in text.rjust(width):
        if ch.isdigit():
            codes.append(int(ch))
        elif ch == "-":
            codes.append(DIGIT_MINUS)
        elif ch == " ":
            codes.append(DIGIT_BLANK)
        else:
            raise ValueError(f"caractère non affichable : {ch!r}")
    return codes


class McpOutputs:
    """État des sorties du MCP ; produit les trames à envoyer."""

    def __init__(self, brightness=0):
        self.brightness = brightness
        self.pages = {0: [DIGIT_BLANK] * 11 + [0], 1: [DIGIT_BLANK] * 11 + [0]}  # n0..n11
        self.leds = 0

    def set_display(self, name, value, blank_leading=True):
        slots = DISPLAYS[name]
        for (page, nib), code in zip(slots, format_value(value, len(slots), blank_leading)):
            self.pages[page][nib] = code

    def set_dot(self, name, on):
        page, nib, mask = DOTS[name]
        cur = self.pages[page][nib]
        self.pages[page][nib] = (cur | mask) if on else (cur & ~mask)

    def set_led(self, name, on):
        bit = 1 << LEDS[name]
        self.leds = (self.leds | bit) if on else (self.leds & ~bit)

    def display_frames(self):
        return [frame(self.pages[p], p, self.brightness) for p in (0, 1)]

    def led_frame(self):
        lo, hi = self.leds & 0x0F, (self.leds >> 4) & 0x0F
        nib = [lo, hi, (self.leds >> 8) & 0x0F, (self.leds >> 12) & 0x0F] + [0] * 7
        return frame(nib, 2, self.brightness)

    def all_frames(self):
        return self.display_frames() + [self.led_frame()]
