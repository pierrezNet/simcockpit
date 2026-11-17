"""Jauge du bus FDBUS (EFDE) pilotée par une valeur du simulateur.

La jauge est désignée par le nom qu'on lui a donné dans le banc de test (onglet FDBUS) :
ce nom renvoie, dans config/fdbus.yaml, à une sortie de module (adresse, sortie) et à
l'étalonnage de son cadran. Rien n'est figé ici : brancher une autre jauge sur une
sortie se règle dans le banc, puis dans le profil d'avion (nom de jauge → dataref).

Le bus est initialisé par la carte (hw/device.py) ; le moteur logique transmet la liste
des modules trouvés (`attach`). La jauge produit ensuite ses trames de position
(`take_frames`), que le moteur écrit sur la carte.

Sans valeur du simulateur (X-Plane absent ou perdu), l'aiguille revient sur la valeur
de repos du cadran (`rest`, 0 par défaut : 0 ft/min, volets rentrés).
"""

from ..hw import fdbus
from .controls import Control

REPORT_EVERY = 0.25      # s : l'état affiché suit la valeur sans inonder le panneau


class Gauge(Control):
    type = "gauge"
    quiet = True         # change en continu : pas de ligne de journal à chaque valeur

    def __init__(self, name, gauge, dataref=None, scale=1.0, rest=0.0, **kw):
        super().__init__(name, [], **kw)
        self.gauge = str(gauge)
        self.dataref = dataref
        self.scale = float(scale)
        self.rest = float(rest)
        self.address = self.channel = None
        self.calibration = None
        self.module = None
        self.problem = "bus FDBUS pas encore initialisé"
        self.sim_value = None     # valeur reçue (simulateur ou panneau), None = aucune
        self.position = None      # dernière position demandée au moteur
        self._outputs = fdbus.FdbusOutputs()
        self._queue = []
        self._changed = True
        self._reported = None
        self._connected = False

    # ------------------------------------------------------------ configuration
    def resolve(self, calibrations):
        """Trouve la sortie et l'étalonnage de la jauge dans config/fdbus.yaml."""
        wanted = self.gauge.strip().casefold()
        found = [(key, cal) for key, cal in calibrations.items()
                 if cal.name.strip().casefold() == wanted]
        names = sorted({cal.name for cal in calibrations.values() if cal.name})
        if not found:
            raise ValueError(f"jauge « {self.gauge} » inconnue dans config/fdbus.yaml"
                             f" (jauges nommées dans le banc : {', '.join(names) or 'aucune'})")
        if len(found) > 1:
            where = ", ".join(f"module {a} sortie {c}" for (a, c), _ in found)
            raise ValueError(f"jauge « {self.gauge} » : nom porté par plusieurs sorties ({where})")
        (self.address, self.channel), self.calibration = found[0]
        if len(self.calibration) < 2:
            raise ValueError(f"jauge « {self.gauge} » : il faut au moins deux repères"
                             " d'étalonnage (banc de test, onglet FDBUS)")

    @property
    def unit(self):
        return self.calibration.unit if self.calibration else ""

    # ------------------------------------------------------------ bus
    def attach(self, modules):
        """Fin d'initialisation du bus : modules trouvés (hw.fdbus.Module)."""
        self._outputs = fdbus.FdbusOutputs()     # la première position sera doublée
        self.module = None
        m = next((m for m in modules if m.address == self.address), None)
        if m is None:
            self.problem = f"module {self.address} absent du bus"
        elif self.calibration.module_type not in (None, m.type):
            self.problem = (f"module {self.address} de type {m.type}, étalonné pour le type"
                            f" {self.calibration.module_type} : autre module à cette adresse ?")
        else:
            self.module, self.problem = m, None
            self.position = None
            self._render()
        self._changed = True

    def restart(self, cold=False):
        """Carte (re)connectée : on attend la fin de l'initialisation du bus."""
        self.module, self.problem = None, "initialisation du bus…"
        self._queue = []
        self._changed = True

    def bus_failed(self, reason):
        self.module, self.problem = None, f"initialisation du bus : {reason}"
        self._changed = True

    # ------------------------------------------------------------ valeur
    def sim_datarefs(self):
        return [self.dataref] if self.dataref else []

    def on_sim(self, name, value, t):
        if name == self.dataref:
            self.set_value(value * self.scale)

    @property
    def sim_connected(self):
        return self._connected

    @sim_connected.setter
    def sim_connected(self, on):
        if self._connected and not on:
            self.set_value(None)              # X-Plane perdu : aiguille au repos
        self._connected = on

    def set_value(self, value):
        """Valeur à indiquer (unité du cadran) ; None = repos."""
        self.sim_value = None if value is None else float(value)
        self._render()

    @property
    def shown_value(self):
        """Valeur indiquée par l'aiguille : la demandée, bornée au cadran étalonné."""
        if self.position is None or self.calibration is None:
            return None
        return self.calibration.value(self.position)

    def _render(self):
        self._changed = True
        if self.module is None:
            return
        target = self.rest if self.sim_value is None else self.sim_value
        position = self.calibration.position(target)
        lo, hi = self.module.limits(self.channel)
        self.position = max(lo, min(hi, position))
        frames = self._outputs.position(self.module, self.position, self.channel)
        key = ("jauge", self.address, self.channel)
        for k, f in enumerate(frames):
            self._queue.append((key + (k,), f))   # 1re commande doublée : deux clés

    def take_frames(self):
        out, self._queue = self._queue, []
        return out

    # ------------------------------------------------------------ temps
    def poll(self, t):
        if not self._changed:
            return None
        if self._reported is not None and t - self._reported < REPORT_EVERY:
            return None
        self._changed, self._reported = False, t
        self.value = self.summary()
        return self.value

    def summary(self):
        if self.problem:
            return self.problem
        v = self.shown_value
        return f"{v:.0f} {self.unit}".strip() + f" (moteur {self.position})"

    def describe(self):
        where = (f"module {self.address} sortie {self.channel}" if self.address is not None
                 else "sortie à trouver")
        src = self.dataref or "aucun dataref"
        return f"jauge « {self.gauge} » ({where}) ← {src}" + (
            f" × {self.scale:g}" if self.scale != 1 else "")
