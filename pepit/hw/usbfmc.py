"""CDU OpenCockpits (737) : clavier et voyants de la carte « USBFMC V1.0 ».

Vérifié le 2026-11-10 (captures, webcam) et cohérent avec xpcockpit (carte
« IOCardS-Keys », touches 1 à 88) et avec l'ancien script SIOC de l'utilisateur :

- la carte reste muette tant qu'on ne lui a rien écrit ;
- ensuite, UNE trame par appui : octet 0 = numéro de la touche (1 à 88), le reste à 0 ;
  rien au relâchement, pas de répétition si la touche reste enfoncée ;
- en écriture, l'octet 0 est un masque des 5 voyants (bits 5 à 7 sans effet).

Les noms viennent des légendes du CDU 737 ; les numéros de l'ancien script SIOC
(archives/SIOCV5/FMC.txt). Vérifiés sur la carte : 1, 2, 3, A, B, EXEC, CLR.
"""

LEDS = {"OFST": 0, "MSG": 1, "EXEC": 2, "DSPY": 3, "FAIL": 4}   # bit du masque

KEYS = {
    # touches de sélection de ligne, de haut en bas
    56: "LSK1L", 64: "LSK2L", 72: "LSK3L", 80: "LSK4L", 88: "LSK5L", 87: "LSK6L",
    86: "LSK1R", 85: "LSK2R", 84: "LSK3R", 83: "LSK4R", 82: "LSK5R", 74: "LSK6R",
    # pages et fonctions
    79: "INIT REF", 78: "RTE", 77: "CLB", 76: "CRZ", 75: "DES",
    71: "MENU", 70: "LEGS", 69: "DEP ARR", 68: "HOLD", 67: "PROG", 66: "EXEC",
    63: "N1 LIMIT", 62: "FIX", 55: "PREV PAGE", 54: "NEXT PAGE",
    # chiffres
    32: "1", 31: "2", 30: "3", 24: "4", 23: "5", 22: "6", 16: "7", 15: "8", 14: "9",
    8: ".", 7: "0", 6: "+/-",
    # lettres et édition (rangée Z SP DEL / CLR : 5 4 3 2 1)
    61: "A", 60: "B", 59: "C", 58: "D", 57: "E",
    53: "F", 52: "G", 51: "H", 50: "I", 49: "J",
    29: "K", 28: "L", 27: "M", 26: "N", 25: "O",
    21: "P", 20: "Q", 19: "R", 18: "S", 17: "T",
    13: "U", 12: "V", 11: "W", 10: "X", 9: "Y",
    5: "Z", 4: "SP", 3: "DEL", 2: "/", 1: "CLR",
}
MAX_KEY = 88

# Disposition pour l'affichage : groupes de touches dans l'ordre du CDU.
LAYOUT = {
    "Lignes gauche": ["LSK1L", "LSK2L", "LSK3L", "LSK4L", "LSK5L", "LSK6L"],
    "Lignes droite": ["LSK1R", "LSK2R", "LSK3R", "LSK4R", "LSK5R", "LSK6R"],
    "Pages": ["INIT REF", "RTE", "CLB", "CRZ", "DES", "MENU", "LEGS", "DEP ARR", "HOLD",
              "PROG", "EXEC", "N1 LIMIT", "FIX", "PREV PAGE", "NEXT PAGE"],
    "Lettres": [chr(c) for c in range(ord("A"), ord("Z") + 1)] + ["SP", "DEL", "/", "CLR"],
    "Chiffres": ["1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0", "+/-"],
}


def keys_pressed(packet: bytes):
    """Trame reçue → numéros des touches appuyées (en principe une seule)."""
    return [b for b in packet if 1 <= b <= MAX_KEY]


def key_name(code):
    return KEYS.get(code, f"touche {code} (inconnue)")


def led_frame(lit=()) -> bytes:
    """Voyants à allumer (noms de LEDS) → trame ; une trame vide les éteint tous."""
    mask = 0
    for name in lit:
        mask |= 1 << LEDS[name]
    return bytes([mask]) + bytes(7)


class FmcOutputs:
    """État des 5 voyants du CDU ; même interface que les sorties du MCP pour le moteur."""

    def __init__(self):
        self.lit = set()

    def set_led(self, name, on):
        if name not in LEDS:
            raise KeyError(name)
        (self.lit.add if on else self.lit.discard)(name)

    def led_frame(self) -> bytes:
        return led_frame(self.lit)
