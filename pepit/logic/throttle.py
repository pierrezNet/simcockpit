"""Manette des gaz : un axe d'une manette physique pilote la poussée de plusieurs moteurs.

Exemple : un TQ à deux manettes sur un quadriréacteur (BAe 146), la gauche pour les
moteurs 1 et 2, la droite pour les moteurs 3 et 4. La position de l'axe (0..1, fournie
par la carte) est ramenée à une poussée 0..1 entre deux repères réglés dans le profil :
`ralenti` (le cran : poussée 0) et `plein_gaz` (poussée 1). Tout ce qui est au-delà du
cran, côté reverse, reste au ralenti. Les repères peuvent être dans un sens ou dans
l'autre (sur le TCA Q-Eng, 0 = plein gaz).

Coupure carburant (BAe 146 : position OFF derrière le ralenti, pas d'inverseur) : avec
`coupure`, une position de l'axe encore plus loin que le cran, la manette écrit
`valeur_coupure` (−0,1 = OFF pour les manettes Thranda). On en ressort en revenant
d'HYSTERESIS vers le cran : une vibration près du seuil ne coupe pas le moteur.

Les axes de la manette doivent être désaffectés dans les réglages joystick d'X-Plane :
sinon X-Plane et Pepit écrivent tous deux la poussée.
"""

from .controls import Control

SEND_EVERY = 1 / 30      # s : au plus 30 écritures par seconde vers X-Plane
MIN_STEP = 0.002         # écart de poussée en dessous duquel on n'écrit pas
REPORT_EVERY = 0.25      # s : rafraîchissement de l'état affiché
HYSTERESIS = 0.03        # écart de position pour sortir de la coupure


class ThrottleAxis(Control):
    type = "throttle_axis"
    quiet = True         # change en continu : pas de ligne de journal à chaque valeur

    def __init__(self, name, axis, datarefs, ralenti, plein_gaz, coupure=None,
                 valeur_coupure=None, **kw):
        super().__init__(name, [], **kw)
        self.axis = int(axis)
        self.datarefs = [datarefs] if isinstance(datarefs, str) else list(datarefs)
        if not self.datarefs:
            raise ValueError(f"{name} : au moins un dataref de poussée (datarefs)")
        self.idle, self.full = float(ralenti), float(plein_gaz)
        if self.idle == self.full:
            raise ValueError(f"{name} : ralenti et plein_gaz doivent être différents")
        self.cut_at = None if coupure is None else float(coupure)
        if self.cut_at is not None:
            if valeur_coupure is None:
                raise ValueError(f"{name} : coupure demande valeur_coupure (valeur écrite pour OFF)")
            if not self._beyond_idle(self.cut_at):
                raise ValueError(f"{name} : coupure doit être derrière le ralenti")
        self.cut_value = None if valeur_coupure is None else float(valeur_coupure)
        self.cutoff = False         # carburant coupé (position OFF)
        self.position = None        # position de l'axe, 0..1
        self.ratio = None           # poussée demandée, 0..1
        self.output = None          # valeur écrite : la poussée, ou valeur_coupure
        self._sent = None
        self._last_send = -1e9
        self._reported = None
        self._changed = False

    def _beyond_idle(self, position):
        """Position plus loin que le ralenti, du côté opposé au plein gaz."""
        return (position - self.idle) * (self.full - self.idle) < 0

    def _cut(self, position):
        """Coupure avec hystérésis : on y entre au seuil, on en sort un peu avant."""
        if self.cut_at is None:
            return False
        if self.cutoff:
            back = self.cut_at + (HYSTERESIS if self.full > self.idle else -HYSTERESIS)
            return (position - back) * (self.full - self.idle) < 0
        return (position - self.cut_at) * (self.full - self.idle) <= 0

    def thrust(self, position):
        """Position de l'axe → poussée 0..1 (au-delà du cran : ralenti)."""
        r = (position - self.idle) / (self.full - self.idle)
        return min(1.0, max(0.0, r))

    def on_axis(self, axis, value, t):
        if axis != self.axis:
            return
        self.position = value
        self.ratio = self.thrust(value)
        self.cutoff = self._cut(value)
        self.output = self.cut_value if self.cutoff else self.ratio
        self._changed = True

    def update(self, active, t):
        pass

    def _send(self, t, force=False):
        """Écrit la poussée si elle a assez changé (ralenti et plein gaz toujours atteints
        exactement), au plus toutes les SEND_EVERY ; le poll suivant rattrape un envoi différé."""
        value = self.output
        if value is None or not self.sim_connected:
            return
        if not force:
            if self._sent is not None:
                exact = value in (0.0, 1.0, self.cut_value) and value != self._sent
                if abs(value - self._sent) < MIN_STEP and not exact:
                    return
            if t - self._last_send < SEND_EVERY:
                return
        self._sent, self._last_send = value, t
        for ref in self.datarefs:
            self._sim("dref", ref, round(value, 4))

    def sim_sync(self):
        self._send(0, force=True)        # X-Plane (re)connecté : pousser la position actuelle

    def poll(self, t):
        self._send(t)
        if not self._changed or (self._reported is not None and t - self._reported < REPORT_EVERY):
            return None
        self._changed, self._reported = False, t
        self.value = self.summary()
        return self.value

    def summary(self):
        if self.ratio is None:
            return "manette pas encore lue"
        if self.cutoff:
            return f"OFF, carburant coupé (position {self.position:.3f})"
        return f"poussée {self.ratio * 100:.0f} % (position {self.position:.3f})"

    def describe(self):
        cut = f", OFF au-delà de {self.cut_at:g}" if self.cut_at is not None else ""
        return (f"manette des gaz : axe {self.axis} → {len(self.datarefs)} moteur(s), "
                f"ralenti {self.idle:g}, plein gaz {self.full:g}{cut}")
