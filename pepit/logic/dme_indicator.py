"""Logique d'un indicateur DME Collins IND-42C (réf. 622-7318-001) sur le DME EFDE.

Fonctionnement reproduit (guide Pro Line ; à confirmer sur la documentation Collins) :
- à la mise sous tension : test de tous les segments, puis distance en NM à gauche et
  identifiant de la station à droite ;
- appui sur SEL : la partie droite passe à KT (vitesse sol), puis MIN (temps
  jusqu'à la station), puis revient à ID ;
- HLD (appui long sur SEL dans l'avion) n'est pas repris : le bouton du DME EFDE
  n'envoie qu'une impulsion, quelle que soit la durée d'appui ;
- PWR : marche / arrêt ;
- pas de signal : tirets ;
- IND-42C : pas de sélecteur de canal, le canal est fixé par câblage (`channel`).

Les données (distance, vitesse sol, identifiant) viennent du simulateur : pour l'instant
du panneau virtuel, plus tard de X-Plane.
"""

from ..hw import dme
from .controls import Control

MODES = ("ID", "KT", "MIN")
MIN_GS_FOR_TIME = 30      # en dessous (nœuds), le temps jusqu'à la station n'a pas de sens


class DmeIndicator(Control):
    type = "dme_indicator"

    def __init__(self, name, sel=dme.BUTTONS[0x01], pwr=dme.BUTTONS[0x02], channel=1,
                 self_test=2.0, backlight=None, **kw):
        super().__init__(name, [sel, pwr], **kw)
        self.sel_input, self.pwr_input = sel, pwr
        self.channel = str(channel) if channel else None
        if self.channel is not None and self.channel not in dme.ANNUNCIATORS["canal"][2]:
            raise ValueError(f"{name} : canal {channel} (1, 2 ou 3)")
        self.self_test = self_test
        self.backlight = backlight
        # état de l'instrument
        self.powered = True
        self.testing = False
        self.mode = "ID"
        # données du simulateur
        self.distance = None       # NM ; None = pas de signal
        self.groundspeed = None    # nœuds
        self.ident = ""
        # boutons
        self._down = {sel: False, pwr: False}
        # sorties
        self._queue = []           # [(clé, trame)] à envoyer
        self._sent = {}            # clé -> dernière trame envoyée (évite les répétitions)
        self._boot_at = None       # mise sous tension demandée ; l'instant est pris au poll
        self._test_end = None
        self._changed = True
        self.value = self.summary()

    # ------------------------------------------------------------ entrées
    def update(self, active, t):
        """Fronts des boutons, sans anti-rebond : le DME envoie des impulsions propres
        (~57 ms), qu'un filtre de 50 ms risquerait de perdre."""
        for index in (self.sel_input, self.pwr_input):
            down = bool(active[index])
            if down == self._down[index]:
                continue
            self._down[index] = down
            if down and index == self.pwr_input:
                self.toggle_power()
            elif down and index == self.sel_input:
                self.press_sel()

    def press_sel(self):
        if self.powered and not self.testing:
            self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
            self._render()

    def toggle_power(self):
        self.powered = not self.powered
        if self.powered:
            self.restart()
        else:
            self.testing, self._boot_at = False, None
            self._send("power", dme.command(dme.OFF))
            self._sent = {"power": self._sent["power"]}
            self._changed = True

    def set_sim(self, distance=..., groundspeed=..., ident=...):
        """Nouvelles données du simulateur (un argument omis reste inchangé)."""
        if distance is not ...:
            self.distance = None if distance is None else max(0.0, float(distance))
        if groundspeed is not ...:
            self.groundspeed = None if groundspeed is None else max(0.0, float(groundspeed))
        if ident is not ...:
            self.ident = (ident or "").strip().upper()[:4]
        self._render()

    # ------------------------------------------------------------ sorties
    def restart(self, cold=False):
        """Mise sous tension : test des segments puis affichage.

        `cold` (connexion de la carte) : le DME est peut-être déjà allumé, et la commande
        d'allumage seule ne relance alors pas son test (vérifié) : on l'éteint d'abord.
        """
        self.powered, self.testing = True, True
        self.mode = "ID"
        self._sent, self._queue = {}, []       # ce qui était en attente est périmé
        self._boot_at = True
        if cold:
            self._send("power_off", dme.command(dme.OFF))
        self._send("power", dme.command(dme.ON))
        self._changed = True

    def _send(self, key, frame):
        if self._sent.get(key) != frame:
            self._sent[key] = frame
            self._queue.append((key, frame))

    def fields(self):
        """Ce que l'écran doit montrer : (gauche, droite, {groupe: voyant})."""
        left = None if self.distance is None else round(self.distance, 1)
        if self.mode == "ID":
            right = self.ident if self.distance is not None else None
        elif self.mode == "KT":
            right = None if self.groundspeed is None else str(min(round(self.groundspeed), 9999))
        else:
            gs = self.groundspeed or 0
            right = (None if self.distance is None or gs < MIN_GS_FOR_TIME
                     else str(min(round(self.distance / gs * 60), 999)))
        lit = {"canal": self.channel, "unite_gauche": "NM", "unite_droite": self.mode}
        return left, right, lit

    def _render(self):
        self._changed = True
        if not self.powered or self.testing:
            return
        left, right, lit = self.fields()
        self._send("left", dme.no_distance() if left is None else dme.distance(left))
        if right is None:
            self._send("right", dme.right_text("---", align_right=True))
        else:
            self._send("right", dme.right_text(right, align_right=self.mode != "ID"))
        for group, label in lit.items():
            self._send(group, dme.annunciator(group, label))

    def take_frames(self):
        """Trames à écrire, dans l'ordre (le moteur les espace de WRITE_GAP)."""
        out, self._queue = self._queue, []
        return out

    # ------------------------------------------------------------ temps
    def poll(self, t):
        if self._boot_at is True:                    # instant réel de la mise sous tension
            self._boot_at, self._test_end = t, t + self.self_test
        if self.testing and self._test_end is not None and t >= self._test_end:
            self.testing, self._test_end = False, None
            self._send("clear", dme.command(dme.CLEAR))
            self._send("backlight", dme.backlight(self.backlight))
            self._render()
        if self._changed:
            self._changed = False
            self.value = self.summary()
            return self.value
        return None

    def summary(self):
        if not self.powered:
            return "éteint"
        if self.testing:
            return "test des segments"
        left, right, lit = self.fields()
        dist = "---" if left is None else f"{left:.1f}" if left < dme.TENTHS_BELOW_NM else str(int(left))
        return f"{dist} NM · {right if right is not None else '---'} {lit['unite_droite']}"

    def describe(self):
        return (f"DME IND-42C : SEL entrée {self.sel_input} (ID → KT → MIN),"
                f" PWR entrée {self.pwr_input}, canal {self.channel or '-'}")
