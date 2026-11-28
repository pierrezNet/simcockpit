"""Assistant de vérification des entrées : « actionne la borne N » → numéro SIOC détecté.

Le cœur (`TerminalProbe`, `summarize`) est sans entrée/sortie, donc testable et réutilisable
par l'interface graphique. `run_wizard` est la version terminal.
"""

import json
import os
import queue
import select
import sys
import time
from dataclasses import asdict, dataclass, field

HOLD = 1.0  # s sans nouvel événement : un interrupteur basculé (non relâché) est accepté


@dataclass
class TerminalResult:
    terminal: int
    status: str                 # ok | pontée | muette | passée
    indexes: list = field(default_factory=list)   # numéros SIOC qui ont réagi
    released: bool = True       # revenu à l'état de repos (poussoir) ou maintenu (interrupteur)


class TerminalProbe:
    """Observe les événements pendant qu'on actionne UNE borne."""

    def __init__(self, terminal, baseline, ignore=()):
        self.terminal = terminal
        self.baseline = list(baseline)
        self.ignore = set(ignore)
        self.changed = []           # ordre d'apparition
        self.current = list(baseline)
        self.last_t = None

    def feed(self, index, value, t):
        if index in self.ignore:
            return
        self.current[index] = value
        if value != self.baseline[index] and index not in self.changed:
            self.changed.append(index)
        self.last_t = t

    def released(self):
        return all(self.current[i] == self.baseline[i] for i in self.changed)

    def done(self, t):
        if not self.changed:
            return False
        return self.released() or (t - self.last_t >= HOLD)

    def result(self):
        if not self.changed:
            return TerminalResult(self.terminal, "muette")
        status = "ok" if len(self.changed) == 1 else "pontée"
        return TerminalResult(self.terminal, status, list(self.changed), self.released())


def summarize(results, noisy=(), inputs=32):
    """Synthèse : anomalies et correspondance borne → SIOC."""
    owners = {}
    for r in results:
        for i in r.indexes:
            owners.setdefault(i, []).append(r.terminal)
    return {
        "mapping": {r.terminal: r.indexes[0] for r in results if r.status == "ok"},
        "muettes": [r.terminal for r in results if r.status == "muette"],
        "pontées": {r.terminal: r.indexes for r in results if r.status == "pontée"},
        "passées": [r.terminal for r in results if r.status == "passée"],
        "doublons": {i: t for i, t in owners.items() if len(t) > 1},
        "instables": sorted(noisy),
    }


# ---------------------------------------------------------------- version terminal

def _stdin_line():
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.readline().strip().lower()
    return None


def _drain(card, probe=None, counter=None, until=None):
    """Consomme les événements d'entrée jusqu'à `until` (monotonic) ou file vide."""
    while True:
        timeout = 0.05 if until is None else max(0.0, until - time.monotonic())
        try:
            ev = card.events.get(timeout=timeout)
        except queue.Empty:
            if until is None or time.monotonic() >= until:
                return
            continue
        if ev.kind == "error":
            raise OSError(ev.value)
        if ev.kind != "input":
            continue
        if counter is not None:
            counter[ev.index] = counter.get(ev.index, 0) + 1
        if probe is not None:
            probe.feed(ev.index, ev.value, ev.t)


def run_wizard(card, first=1, last=32, timeout=20.0, noise_s=3.0, report_dir="reports"):
    # 1. état initial
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            ev = card.events.get(timeout=0.2)
        except queue.Empty:
            continue
        if ev.kind == "ready":
            break
        if ev.kind == "error":
            raise OSError(ev.value)
    else:
        print("La carte n'a pas envoyé d'état initial (init refusée ?).")
        return None

    # 2. bruit
    print(f"\n1/2  Mesure du bruit : ne touchez à RIEN pendant {noise_s:.0f} s…")
    counts = {}
    _drain(card, counter=counts, until=time.monotonic() + noise_s)
    noisy = sorted(counts)
    if noisy:
        print(f"     Entrées instables, ignorées pendant le test : {noisy}")
    else:
        print("     Aucune entrée instable.")
    at_rest = [i for i, v in enumerate(card.debouncer.stable) if card.is_active(v)]
    if at_rest:
        print(f"     Entrées déjà actionnées au repos : {at_rest}")

    # 3. bornes une à une
    print(f"\n2/2  Bornes {first} à {last}. Pour chacune : actionnez-la (poussoir : appuyez puis relâchez ;"
          f"\n     interrupteur ou molette : basculez). [Entrée] = passer, q = arrêter.\n")
    results = []
    for n in range(first, last + 1):
        _drain(card)  # vide les restes
        probe = TerminalProbe(n, card.debouncer.stable, ignore=noisy)
        print(f"  Borne {n:2d} … ", end="", flush=True)
        end = time.monotonic() + timeout
        res = None
        while res is None:
            line = _stdin_line()
            if line == "q":
                print("arrêt")
                return _finish(card, results, noisy, report_dir)
            if line is not None:
                res = TerminalResult(n, "passée")
                break
            _drain(card, probe, until=time.monotonic() + 0.05)
            now = time.monotonic() - card.t0
            if probe.done(now):
                time.sleep(0.2)            # laisse arriver un éventuel pontage tardif
                _drain(card, probe)
                res = probe.result()
            elif time.monotonic() > end:
                res = probe.result()       # muette
        results.append(res)
        detail = {"ok": f"→ entrée SIOC {res.indexes[0]}",
                  "pontée": f"→ PONTÉE avec {res.indexes}",
                  "muette": "→ aucune réaction",
                  "passée": "(passée)"}[res.status]
        if res.status in ("ok", "pontée") and not res.released:
            detail += " (maintenue)"
        print(detail)
        if res.indexes and not res.released:
            time.sleep(0.3)  # l'état de repos de la borne suivante inclut ce basculement
    return _finish(card, results, noisy, report_dir)


def _finish(card, results, noisy, report_dir):
    s = summarize(results, noisy, card.type.inputs)
    print("\nBilan")
    print(f"  Correspondance borne → SIOC : {s['mapping']}")
    for key in ("muettes", "pontées", "doublons", "instables", "passées"):
        if s[key]:
            print(f"  {key.capitalize():12}: {s[key]}")
    tested = [r for r in results if r.status != "passée"]
    if not tested:
        print("  Aucune borne testée.")
    elif not any(s[k] for k in ("muettes", "pontées", "doublons", "instables")):
        print(f"  Aucune anomalie sur {len(tested)} borne(s) testée(s).")
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, time.strftime(
        f"inputs_{card.info.product}_{card.info.usb_port}_%Y%m%d-%H%M%S.json"))
    with open(path, "w") as f:
        json.dump({"card": card.info.product, "usb_port": card.info.usb_port,
                   "results": [asdict(r) for r in results], "summary": s},
                  f, indent=2, ensure_ascii=False, default=str)
    print(f"  Rapport : {path}")
    return s
