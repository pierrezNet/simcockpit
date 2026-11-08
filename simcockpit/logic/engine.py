"""Moteur : relie les cartes physiques aux instruments décrits dans cockpit.yaml.

Le cœur (`feed`, `poll`, `outputs`) n'accède pas au matériel : on peut le nourrir avec
une capture. `connect` / `step` gèrent les vraies cartes.

Sorties : une commande liée à un afficheur (`display:`) ou à un voyant (`led:`) met à
jour l'état de sortie de sa carte ; les trames sont ensuite envoyées une à une, espacées
d'au moins WRITE_GAP (le MCP ignore les trames trop rapprochées).
"""

import queue
import time
from dataclasses import dataclass

from ..hw import manager, mcp
from ..hw.cards import classify
from ..hw.device import Card

WRITE_GAP = 0.06


@dataclass
class Change:
    instrument: str
    control: str
    value: object
    t: float


class Engine:
    def __init__(self, cockpit):
        self.cockpit = cockpit
        self.cards = {}            # id -> Card (connectées)
        self.status = {cid: "non trouvée" for cid in cockpit.cards}
        # état des sorties par carte (seul le protocole MCP est géré pour l'instant)
        self.outputs = {cid: mcp.McpOutputs() for cid, spec in cockpit.cards.items()
                        if classify(spec.product).out_protocol == "mcp"}
        self._pending = {cid: {} for cid in self.outputs}   # clé de trame -> trame
        self._last_write = {}

    # ------------------------------------------------------------ cœur, sans matériel
    def feed(self, card_id, raw_inputs, t, active_level):
        """Nouvel état brut des entrées d'une carte."""
        active = [int(v == active_level) for v in raw_inputs]
        for inst in self.cockpit.instruments.values():
            if inst.card == card_id:
                for ctrl in inst.controls.values():
                    ctrl.update(active, t)

    def poll(self, t):
        changes = []
        for inst in self.cockpit.instruments.values():
            for name, ctrl in inst.controls.items():
                v = ctrl.poll(t)
                if v is not None:
                    changes.append(Change(inst.id, name, v, t))
                    self._apply_output(inst.card, ctrl, v)
        return changes

    def _apply_output(self, card_id, ctrl, value):
        out = self.outputs.get(card_id)
        if out is None or (ctrl.display is None and ctrl.led is None):
            return
        if ctrl.display is not None:
            shown, dot = ctrl.display_value(value)
            out.set_display(ctrl.display, shown, blank_leading=not ctrl.leading_zeros)
            if ctrl.display in mcp.DOTS:
                out.set_dot(ctrl.display, dot)
            p0, p1 = out.display_frames()
            self._pending[card_id].update({"page0": p0, "page1": p1})
        if ctrl.led is not None:
            out.set_led(ctrl.led, bool(value))
            self._pending[card_id]["leds"] = out.led_frame()

    def take_frame(self, card_id, now):
        """Prochaine trame à écrire sur la carte, ou None (rien à faire / trop tôt)."""
        pending = self._pending.get(card_id)
        if not pending or now - self._last_write.get(card_id, -1e9) < WRITE_GAP:
            return None
        key = next(iter(pending))
        self._last_write[card_id] = now
        return pending.pop(key)

    def resend_all(self, card_id):
        """Remet toutes les sorties d'une carte en file (ex. après (re)connexion)."""
        out = self.outputs.get(card_id)
        if out is not None:
            p0, p1 = out.display_frames()
            self._pending[card_id].update({"page0": p0, "page1": p1, "leds": out.led_frame()})

    # ------------------------------------------------------------ matériel
    def connect(self):
        """Ouvre les cartes déclarées. Retourne {id: statut}."""
        present = manager.scan()
        taken = set()
        for cid, spec in self.cockpit.cards.items():
            if cid in self.cards:
                continue
            match = next((d for d in present
                          if d.info.product == spec.product
                          and (spec.usb_port is None or d.info.usb_port == spec.usb_port)
                          and d.info.path not in taken), None)
            if match is None:
                self.status[cid] = "non trouvée"
                continue
            taken.add(match.info.path)
            card = Card(match.info, classify(match.info.product), state_events=True)
            try:
                card.start()
            except OSError as e:
                self.status[cid] = f"erreur : {e}"
                continue
            self.cards[cid] = card
            self.resend_all(cid)
            self.status[cid] = f"connectée ({match.info.path}, port {match.info.usb_port})"
        return dict(self.status)

    def step(self):
        """À appeler régulièrement : consomme les événements, écrit les sorties, retourne les changements."""
        for cid, card in list(self.cards.items()):
            while True:
                try:
                    ev = card.events.get_nowait()
                except queue.Empty:
                    break
                if ev.kind == "state":
                    # horloge absolue : plusieurs cartes, une seule base de temps
                    self.feed(cid, ev.value, card.t0 + ev.t, card.type.active_level)
                elif ev.kind == "error":
                    self.status[cid] = f"perdue : {ev.value}"
                    card.stop()
                    del self.cards[cid]
        now = time.monotonic()
        changes = self.poll(now)
        for cid, card in self.cards.items():
            frame = self.take_frame(cid, now)
            if frame is not None:
                try:
                    card.write(frame)
                except OSError as e:
                    self.status[cid] = f"erreur d'écriture : {e}"
        return changes

    def close(self):
        for card in self.cards.values():
            card.stop()
        self.cards.clear()
