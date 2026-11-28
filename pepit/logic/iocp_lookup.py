"""Page d'un livret choisie selon une valeur du simulateur, envoyée à une carte IOCP.

Exemple : la carte des vitesses du BAe 146, un livret à une page par masse. La page est
celle de la masse immédiatement supérieure à la masse de l'avion (`choix: superieur`,
l'usage avec un livret : on ne prend jamais une page plus légère que l'avion), ou la
plus proche (`choix: proche`). Chaque case de la page part sur sa variable IOCP ; une
case absente de la page vaut 0 (l'écran affiche un tiret). La clé de page elle-même peut
être envoyée (`variables: {page: 210, …}`).

    source: masse.totale              # fonction ou dataref (kg)
    choix: superieur
    variables: {page: 210, vr_18: 211, …}
    pages:
      38000: {vr_18: 125, v2_18: 133, …}
"""

from .controls import Control

CHOICES = ("superieur", "proche")


class IocpLookup(Control):
    type = "iocp_lookup"
    quiet = True

    def __init__(self, name, source, variables, pages, choix="superieur", **kw):
        super().__init__(name, [], **kw)
        self.source = source
        if choix not in CHOICES:
            raise ValueError(f"{name} : choix {choix!r} ({' ou '.join(CHOICES)})")
        self.choice = choix
        self.columns = {str(col): int(var) for col, var in dict(variables).items()}
        self.variables = sorted(self.columns.values())
        self.pages = {float(key): {str(c): v for c, v in dict(page or {}).items()}
                      for key, page in dict(pages).items()}
        if not self.pages:
            raise ValueError(f"{name} : le livret n'a aucune page (pages)")
        for key, page in self.pages.items():
            unknown = set(page) - set(self.columns)
            if unknown:
                raise ValueError(f"{name} : page {key:g} : cases sans variable {sorted(unknown)}")
        self.reading = None          # valeur du simulateur (masse)
        self.page = None             # clé de la page choisie
        self.values = {}
        self._pending = {}
        self._changed = False

    def sim_datarefs(self):
        return [self.source]

    def update(self, active, t):
        pass

    def choose(self, reading):
        """Clé de page pour cette valeur."""
        keys = sorted(self.pages)
        if self.choice == "proche":
            return min(keys, key=lambda k: (abs(k - reading), k))
        above = [k for k in keys if k >= reading]
        return above[0] if above else keys[-1]       # au-delà du livret : sa dernière page

    def on_sim(self, name, value, t):
        if name != self.source:
            return
        self.reading = float(value)
        page = self.choose(self.reading)
        if page == self.page:
            return
        self.page = page
        content = self.pages[page]
        for col, var in self.columns.items():
            v = int(round(page)) if col == "page" else int(round(float(content.get(col, 0))))
            if self.values.get(var) != v:
                self.values[var] = v
                self._pending[var] = v
        self._changed = True

    def take_values(self):
        out, self._pending = self._pending, {}
        return out

    def poll(self, t):
        if not self._changed:
            return None
        self._changed = False
        self.value = self.summary()
        return self.value

    def summary(self):
        if self.page is None:
            return "en attente de la masse du simulateur"
        return f"page {self.page:g} (masse {self.reading:.0f})"

    def describe(self):
        return (f"livret de {len(self.pages)} page(s), choisie selon {self.source} ;"
                f" variables IOCP {self.variables[0]} à {self.variables[-1]}")
