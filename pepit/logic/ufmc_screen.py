"""Écran de l'UFMC (FJCC), le FMC du BAe 146 de Just Flight, lu dans X-Plane.

L'UFMC ne passe pas par l'écran du FMS standard d'X-Plane : il publie ses 14 lignes dans
FJCC/UFMC/LINE_1 à LINE_14 (texte, type « data »), lisibles seulement par l'API web
d'X-Plane (sim/xplane_web.py). C'est l'écran du CDU droit (FO) : constaté le 2026-11-17,
les touches du commandant ne le faisaient pas changer. Relevé sur la page PERF INIT :

   1 |       PERF INIT       |          titre
   2 | GW/CRZ CG  trip/Crz Alt |        libellés (petits caractères)
   3 |<83.3/16.7%   FL287/FL100|        données
   …
   7 |[][][][]          -35=;2c|        [] = case de saisie, = = degré, ;2 = code ?
  14 ||                                 bloc-notes

Codage, établi en comparant ces lignes à une capture de l'écran de l'avion (2026-11-17) :
- 25 colonnes ; lignes paires (libellés) en petits caractères, affichés en majuscules ;
- « ;n » (n un chiffre) : petits caractères jusqu'à l'espace suivante (« 10.1;2CALC »,
  « -35=;2c » → « -35°c », le C en petit) ; le code lui-même n'est pas affiché ;
- « [] » : une case de saisie □ sur une seule colonne ; « = » : symbole degré ;
- une ligne plus courte que 25 colonnes une fois les codes retirés est étirée au niveau
  de son plus grand blanc intérieur, pour que sa partie droite reste calée à droite
  (« 100 » sous « FL100 »).
"""

from .controls import Control

ROWS, COLUMNS = 14, 25
GREEN, LARGE = 4, 0x80          # style d'un caractère : couleur (bits 0-3), gros (bit 7)
PREFIX = "FJCC/UFMC/LINE_"


def _justify(chars, styles):
    """Étire le plus grand blanc intérieur (le dernier en cas d'égalité) jusqu'à COLUMNS."""
    missing = COLUMNS - len(chars)
    text = "".join(chars)
    inner = text.strip(" ")
    if missing <= 0 or not inner:
        return chars, styles
    first = text.index(inner[0])
    last = first + len(inner)
    best = None                                     # (longueur, début) du plus grand blanc
    i = first
    while i < last:
        if text[i] == " ":
            j = i
            while j < last and text[j] == " ":
                j += 1
            if j - i >= 2 and (best is None or j - i >= best[0]):
                best = (j - i, i)
            i = j
        else:
            i += 1
    if best is None:
        return chars, styles
    at = best[1]
    return chars[:at] + [" "] * missing + chars[at:], styles[:at] + [GREEN] * missing + styles[at:]


def decode_line(raw: bytes, row: int):
    """Ligne brute de l'UFMC → (texte de COLUMNS caractères, [style par caractère])."""
    text = raw.split(b"\0")[0].decode("latin-1")
    label = row % 2 == 1 and row < ROWS - 1        # lignes 2, 4 … 12 : libellés
    chars, styles = [], []
    small_run = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == ";" and i + 1 < len(text) and text[i + 1].isdigit():
            small_run = True                        # petits caractères jusqu'à l'espace
            i += 2
            continue
        if text.startswith("[]", i):
            ch, i = "□", i + 2
        else:
            i += 1
            if ch == "=":
                ch = "°"
        if ch == " ":
            small_run = False
        small = label or small_run
        chars.append(ch.upper())
        styles.append(GREEN | (0 if small else LARGE))
    chars, styles = _justify(chars, styles)
    chars, styles = chars[:COLUMNS], styles[:COLUMNS]
    pad = COLUMNS - len(chars)
    return "".join(chars) + " " * pad, styles + [GREEN] * pad


class UfmcScreen(Control):
    type = "ufmc_screen"
    rows, columns = ROWS, COLUMNS

    def __init__(self, name, side=1, **kw):
        super().__init__(name, [], **kw)
        if side != 1:
            raise ValueError(f"{name} : l'UFMC ne publie qu'un écran, celui du FO (sans « side »)")
        self.side = side
        self.raw = [b""] * ROWS
        self._changed = False

    def update(self, active, t):
        pass

    def web_datarefs(self):
        return [f"{PREFIX}{n}" for n in range(1, ROWS + 1)]

    def on_sim(self, name, value, t):
        if not name.startswith(PREFIX) or not isinstance(value, (bytes, bytearray)):
            return
        row = int(name[len(PREFIX):]) - 1
        if 0 <= row < ROWS and self.raw[row] != value:
            self.raw[row] = bytes(value)
            self._changed = True

    def lines(self):
        return [decode_line(raw, row) for row, raw in enumerate(self.raw)]

    def poll(self, t):
        if not self._changed:
            return None
        self._changed = False
        return self.lines()[0][0].strip() or "(écran vide)"

    def describe(self):
        return "écran de l'UFMC (FJCC), CDU du FO, lu par l'API web d'X-Plane"
