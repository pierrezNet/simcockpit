"""Variables IOCP alimentées par le simulateur, pour une carte réseau écrite pour SIOC
(ex. afficheur carburant ESP8266 : variables 201, 202, 203).

    variables:
      201: carburant.aile_gauche     # nom logique (dictionnaire) ou dataref
      202: carburant.aile_droite
    echelle: 1                       # valeur envoyée = valeur du simulateur × echelle

Les valeurs sont arrondies à l'entier (IOCP ne transporte que des entiers) ; le serveur
(hw/iocp.py) ne les renvoie à une carte que si elles changent.
"""

from .controls import Control

REPORT_EVERY = 1.0       # s : rafraîchissement de l'état affiché


class IocpOutputs(Control):
    type = "iocp_outputs"
    quiet = True

    def __init__(self, name, variables, echelle=1.0, **kw):
        super().__init__(name, [], **kw)
        self.variables = {int(var): ref for var, ref in dict(variables).items()}
        if not self.variables:
            raise ValueError(f"{name} : au moins une variable IOCP")
        self.scale = float(echelle)
        self.values = {}             # variable → valeur entière à envoyer
        self._pending = {}
        self._changed = False
        self._reported = None

    def update(self, active, t):
        pass

    def sim_datarefs(self):
        return list(dict.fromkeys(self.variables.values()))

    def on_sim(self, name, value, t):
        for var, ref in self.variables.items():
            if ref == name:
                v = int(round(float(value) * self.scale))
                if self.values.get(var) != v:
                    self.values[var] = v
                    self._pending[var] = v
                    self._changed = True

    def take_values(self):
        """Variables changées depuis l'appel précédent : {variable: entier}."""
        out, self._pending = self._pending, {}
        return out

    def poll(self, t):
        if not self._changed or (self._reported is not None and t - self._reported < REPORT_EVERY):
            return None
        self._changed, self._reported = False, t
        self.value = self.summary()
        return self.value

    def summary(self):
        if not self.values:
            return "en attente des valeurs du simulateur"
        return "  ".join(f"{var} = {v}" for var, v in sorted(self.values.items()))

    def describe(self):
        return f"variables IOCP {', '.join(map(str, sorted(self.variables)))}"
