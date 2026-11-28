"""Écran du CDU lu dans X-Plane (FMS standard), pour l'afficher dans le panneau virtuel.

X-Plane publie 16 lignes de 24 caractères (developer.x-plane.com, « Datarefs for the CDU
screen ») ; vérifié le 2026-11-14 avec le 737 de Laminar (ligne 0 « INDEX 1/1 », style 0x81) :
- fms_cdu{1|2}_text_lineN : la ligne en UTF-8 (un symbole spécial occupe plusieurs octets) ;
- fms_cdu{1|2}_style_lineN : un octet par caractère : bit 7 gros caractère, bit 6 vidéo
  inverse, bit 5 clignotant, bit 4 souligné, bits 0-3 couleur (0 noir, 1 cyan, 2 rouge,
  3 jaune, 4 vert, 5 magenta, 6 ambre, 7 blanc).
Les tableaux sont lus élément par élément (abonnements RREF « …lineN[i] »).
"""

from .controls import Control

LINES, COLUMNS = 16, 24
MAX_BYTES = 72          # octets lus par ligne : 24 caractères de 3 octets au plus (☐, flèches…)
BASE = "sim/cockpit2/radios/indicators/fms_cdu{side}_{kind}_line{line}[{i}]"


class CduScreen(Control):
    type = "cdu_screen"

    def __init__(self, name, side=1, **kw):
        super().__init__(name, [], **kw)
        if side not in (1, 2):
            raise ValueError(f"{name} : side 1 (commandant) ou 2 (copilote)")
        self.side = side
        self.text = [bytearray(MAX_BYTES) for _ in range(LINES)]
        self.style = [bytearray(COLUMNS) for _ in range(LINES)]
        self._refs = {}
        for line in range(LINES):
            for i in range(MAX_BYTES):
                self._refs[BASE.format(side=side, kind="text", line=line, i=i)] = (self.text, line, i)
            for i in range(COLUMNS):
                self._refs[BASE.format(side=side, kind="style", line=line, i=i)] = (self.style, line, i)
        self._changed = False

    def update(self, active, t):
        pass

    def sim_datarefs(self):
        return list(self._refs)

    def on_sim(self, name, value, t):
        target = self._refs.get(name)
        if target is None:
            return
        table, line, i = target
        b = int(value) & 0xFF
        if table[line][i] != b:
            table[line][i] = b
            self._changed = True

    def lines(self):
        """[(texte de 24 caractères, [style par caractère])] pour les 16 lignes."""
        out = []
        for line in range(LINES):
            raw = bytes(self.text[line]).split(b"\x00")[0]
            text = raw.decode("utf-8", "replace")[:COLUMNS].ljust(COLUMNS)
            out.append((text, list(self.style[line])))
        return out

    def poll(self, t):
        if not self._changed:
            return None
        self._changed = False
        title = self.lines()[0][0].strip()
        return title or "(écran vide)"

    def describe(self):
        return f"écran du CDU {'commandant' if self.side == 1 else 'copilote'} lu dans X-Plane"
