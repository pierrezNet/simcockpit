"""DME EFDE (réplique du Collins IND-42) : écran, voyants et bouton SEL.

Protocole fourni par EFDE (Fab) et vérifié à la webcam le 2026-11-10. Une trame de
8 octets ; l'octet 0 désigne la fonction (dans la doc EFDE, les octets sont numérotés
à partir de 1 : leur « octet 2 » est notre octet 1).

  01  distance à gauche : octets 1-2 = dixièmes de NM, gros-boutiste.
      Le DME affiche le dixième sous 200 NM, puis un entier tronqué (399,9 → « 399 »).
  02  texte à droite : octets 1-4 = 4 caractères ASCII (identifiant de balise, « LIL »)
  03  voyant 1, 2 ou 3 en bas à gauche : octet 7 (0 = éteint)
  04  WPT ou NM sous la distance : octet 5 (1 = WPT, 2 = NM, 0 = éteint)
  05  HLD, KT, MIN ou ID : octet 6 (1 = HLD, 2 = KT, 3 = MIN, 4 = ID, 0 = éteint)
  06  texte libre : octet 1 = colonne de départ (1 à 9), octets 2-5 = 4 caractères
  07  efface tout l'écran
  08  rétroéclairage : octet 1 = 0 pour la cellule photo du DME, 1-255 pour une valeur fixe
      (cellule vérifiée : couverte, le rétroéclairage s'éteint ; plus de lumière, plus fort)
  09  éteint le DME
  0a  allume le DME (avec un test de tous les segments)

Un octet 00 dans un texte allume des segments parasites : les textes sont complétés
avec des espaces. Les trames peuvent être espacées de 60 ms.

En lecture, le DME émet sans initialisation, toutes les 3 ms environ, même éteint.
L'octet 0 vaut 0x0a au repos, 0x01 tant que SEL est enfoncé et 0x02 tant que PWR l'est
(impulsions de 57 ms environ). PWR éteint et rallume l'écran de lui-même, sans programme.
L'octet 2 a valu 0x9b puis 0xbb d'une séance à l'autre : rôle inconnu.
"""

CLEAR, BACKLIGHT, OFF, ON = 0x07, 0x08, 0x09, 0x0A
DISTANCE, RIGHT_TEXT, TEXT = 0x01, 0x02, 0x06
# Les dixièmes ne sont plus affichés à partir de cette distance (vérifié).
TENTHS_BELOW_NM = 200

# Groupes de voyants : nom → (fonction, octet, {libellé: valeur}). Un seul voyant
# allumé à la fois par groupe.
ANNUNCIATORS = {
    "canal": (0x03, 7, {"1": 1, "2": 2, "3": 3}),
    "unite_gauche": (0x04, 5, {"WPT": 1, "NM": 2}),
    "unite_droite": (0x05, 6, {"HLD": 1, "KT": 2, "MIN": 3, "ID": 4}),
}

# Boutons : octet 0 reçu tant que le bouton est enfoncé → numéro d'entrée simcockpit.
BUTTONS = {0x01: 0, 0x02: 1}     # SEL = entrée 0, PWR = entrée 1
BUTTON_NAMES = {0: "SEL", 1: "PWR"}


def _ascii(text, width):
    text = str(text).upper()
    if len(text) > width:
        raise ValueError(f"« {text} » dépasse {width} caractères")
    if not text.isascii() or not text.isprintable():
        raise ValueError(f"« {text} » : caractères ASCII imprimables uniquement")
    return text.ljust(width).encode("ascii")


def distance(nm) -> bytes:
    """Distance en NM (nombre décimal) → trame. Arrondie au dixième."""
    tenths = round(float(nm) * 10)
    if not 0 <= tenths <= 0xFFFF:
        raise ValueError(f"distance hors limites : {nm}")
    return bytes([DISTANCE, tenths >> 8, tenths & 0xFF]) + bytes(5)


def right_text(text, align_right=False) -> bytes:
    """4 caractères à droite (identifiant de balise à gauche, vitesse ou temps calés à droite)."""
    text = str(text).upper()
    if len(text) > 4:
        raise ValueError(f"« {text} » dépasse 4 caractères")
    return bytes([RIGHT_TEXT]) + _ascii(text.rjust(4) if align_right else text, 4) + bytes(3)


def no_distance() -> bytes:
    """Tirets à la place de la distance (pas de signal) ; la colonne 1 est effacée (vérifié)."""
    return text(1, " ---")


def text(column, chars) -> bytes:
    """4 caractères à partir de la colonne 1 à 9."""
    if not 1 <= column <= 9:
        raise ValueError(f"colonne {column} : 1 à 9")
    return bytes([TEXT, column]) + _ascii(chars, 4) + bytes(2)


def annunciator(group, label=None) -> bytes:
    """Allume le voyant `label` du groupe (None = tout le groupe éteint)."""
    function, pos, values = ANNUNCIATORS[group]
    data = bytearray(8)
    data[0] = function
    data[pos] = 0 if label is None else values[label]
    return bytes(data)


def backlight(level=None) -> bytes:
    """Rétroéclairage : None = réglé par la cellule photo du DME, sinon 1 à 255."""
    if level is not None and not 1 <= level <= 255:
        raise ValueError("rétroéclairage : 1 à 255, ou None pour la cellule photo")
    return bytes([BACKLIGHT, level or 0]) + bytes(6)


def command(function) -> bytes:
    """Trame sans paramètre : CLEAR, OFF ou ON."""
    return bytes([function]) + bytes(7)


def buttons(packet: bytes):
    """Trame reçue → état des entrées [SEL, PWR] (1 = enfoncé)."""
    state = [0] * len(BUTTON_NAMES)
    if packet and packet[0] in BUTTONS:
        state[BUTTONS[packet[0]]] = 1
    return state


class DmeOutputs:
    """État affiché ; `frames()` rend toutes les trames pour tout réafficher."""

    def __init__(self):
        self.distance = None
        self.right = ""
        self.lit = {group: None for group in ANNUNCIATORS}
        self.backlight = None

    def frames(self):
        out = [command(CLEAR), backlight(self.backlight)]
        if self.distance is not None:
            out.append(distance(self.distance))
        if self.right:
            out.append(right_text(self.right))
        out += [annunciator(g, label) for g, label in self.lit.items() if label]
        return out
