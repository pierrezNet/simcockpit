"""Radio OpenCockpits de type Airbus (« IOCard-RadioAirb ») : afficheurs et voyants.

Vérifié à la webcam le 2026-11-12. La carte reste muette tant qu'on ne lui a pas envoyé
l'initialisation Master ; elle envoie ensuite l'état de ses 64 entrées (format du MCP).

Trame des AFFICHEURS (bit 7 de l'octet 6 à 0) :
  octets 0-5 : 12 demi-octets n0..n11 (octet k → n[2k] en bas, n[2k+1] en haut) ;
               ACTIVE = n5 n4 n3 n2 n1 n0, STANDBY = n11 .. n6 (de gauche à droite) ;
               codes des chiffres du MCP : 0-9, 0x0a = éteint, 0x0b = « - ».
  octet 6    : points décimaux (bits 0-5, voir DOTS).
Trame des VOYANTS (octet 6 = 0x80) :
  octet 0    : un bit par voyant (voir LEDS) ; la radio les garde jusqu'à la trame suivante.
"""

DIGIT_BLANK = 0x0A
DIGIT_MINUS = 0x0B
WIDTH = 6                       # chiffres par afficheur
LED_PAGE = 0x80

# afficheur → demi-octets, du chiffre de gauche au chiffre de droite
DISPLAYS = {"ACTIVE": [5, 4, 3, 2, 1, 0], "STANDBY": [11, 10, 9, 8, 7, 6]}

# (afficheur, nombre de chiffres avant le point) → bit de l'octet 6
DOTS = {("ACTIVE", 3): 0x02, ("ACTIVE", 4): 0x01, ("ACTIVE", 5): 0x10,
        ("STANDBY", 3): 0x08, ("STANDBY", 4): 0x04, ("STANDBY", 5): 0x20}

LEDS = {"VHF1": 0, "VHF2": 1, "SEL": 2, "VOR": 3, "ADF": 4, "BFO": 5, "NAV": 6, "ILS": 7}


def parse(text):
    """« 118.700 » → (codes des 6 chiffres de gauche à droite, chiffres avant le point ou None).

    Le texte est calé à droite ; espace = chiffre éteint, « - » = signe moins.
    """
    text = "" if text is None else str(text)
    if text.count(".") > 1:
        raise ValueError(f"« {text} » : un seul point décimal")
    digits = text.replace(".", "")
    if len(digits) > WIDTH:
        raise ValueError(f"« {text} » ne tient pas sur {WIDTH} chiffres")
    codes = []
    for ch in digits.rjust(WIDTH):
        if ch.isdigit():
            codes.append(int(ch))
        elif ch == " ":
            codes.append(DIGIT_BLANK)
        elif ch == "-":
            codes.append(DIGIT_MINUS)
        else:
            raise ValueError(f"caractère non affichable : {ch!r}")
    dot = None
    if "." in text:
        dot = WIDTH - len(digits) + text.index(".")
        if dot not in (3, 4, 5):
            raise ValueError(f"« {text} » : point possible seulement après le 3e, 4e ou 5e chiffre")
    return codes, dot


class RadioOutputs:
    """État des afficheurs et voyants de la radio ; produit les trames à envoyer."""

    def __init__(self):
        self.nibbles = [DIGIT_BLANK] * 12
        self.dots = 0
        self.leds = 0

    def set_display(self, name, text):
        codes, dot = parse(text)
        for nib, code in zip(DISPLAYS[name], codes):
            self.nibbles[nib] = code
        for (disp, _), bit in DOTS.items():
            if disp == name:
                self.dots &= ~bit
        if dot is not None:
            self.dots |= DOTS[(name, dot)]

    def set_led(self, name, on):
        bit = 1 << LEDS[name]
        self.leds = (self.leds | bit) if on else (self.leds & ~bit)

    def display_frame(self) -> bytes:
        n = self.nibbles
        data = bytes((n[2 * k] & 0x0F) | ((n[2 * k + 1] & 0x0F) << 4) for k in range(6))
        return data + bytes([self.dots & 0x3F, 0])

    def led_frame(self) -> bytes:
        return bytes([self.leds]) + bytes(5) + bytes([LED_PAGE, 0])

    def all_frames(self):
        return [self.display_frame(), self.led_frame()]
