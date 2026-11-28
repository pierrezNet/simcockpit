"""Filtre anti-rebond : une valeur n'est retenue que si elle reste stable `delay` secondes."""


class Debouncer:
    def __init__(self, n, delay=0.05):
        self.delay = delay
        self.raw = [None] * n
        self.since = [0.0] * n
        self.stable = [None] * n

    def update(self, values, t):
        """Enregistre un nouvel état brut à l'instant t."""
        for i, v in enumerate(values):
            if v != self.raw[i]:
                self.raw[i], self.since[i] = v, t

    def poll(self, t):
        """Retourne [(index, ancienne, nouvelle)] des entrées devenues stables.

        « ancienne » vaut None à la première stabilisation d'une entrée.
        """
        changes = []
        for i, v in enumerate(self.raw):
            if v is not None and v != self.stable[i] and t - self.since[i] >= self.delay:
                changes.append((i, self.stable[i], v))
                self.stable[i] = v
        return changes

    def ready(self, upto=None):
        return None not in self.stable[:upto]


class GroupDebouncer:
    """Anti-rebond d'un GROUPE d'entrées lues ensemble (chiffre codé en binaire, sélecteur…).

    La valeur n'est retenue que lorsque tout le groupe est resté inchangé `delay` secondes :
    évite les valeurs intermédiaires fausses quand plusieurs bits basculent à quelques ms d'écart.
    """

    def __init__(self, indexes, delay=0.05):
        self.indexes = list(indexes)
        self.delay = delay
        self.raw = None
        self.since = 0.0
        self.stable = None

    def update(self, values, t):
        group = tuple(values[i] for i in self.indexes)
        if group != self.raw:
            self.raw, self.since = group, t

    def poll(self, t):
        """Retourne le nouveau tuple stable, ou None s'il n'a pas changé."""
        if self.raw is not None and self.raw != self.stable and t - self.since >= self.delay:
            self.stable = self.raw
            return self.stable
        return None
