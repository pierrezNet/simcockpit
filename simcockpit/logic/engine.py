"""Moteur : relie les cartes physiques aux instruments décrits dans la configuration.

Le cœur (`feed`, `poll`, `outputs`) n'accède pas au matériel : on peut le nourrir avec
une capture. `connect` / `step` gèrent les vraies cartes.

Sorties : une commande liée à un afficheur (`display:`) ou à un voyant (`led:`) met à
jour l'état de sortie de sa carte ; les trames sont ensuite envoyées une à une, espacées
d'au moins WRITE_GAP (le MCP ignore les trames trop rapprochées). Une commande peut aussi
produire elle-même ses trames (`take_frames`, ex. l'indicateur DME).
"""

import queue
import time
from dataclasses import dataclass

from ..hw import manager, mcp, radio_airbus, usbfmc
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
        makers = {"mcp": mcp.McpOutputs, "radio_airbus": radio_airbus.RadioOutputs,
                  "usbfmc": usbfmc.FmcOutputs}
        self.outputs = {cid: makers[classify(spec.product).out_protocol]()
                        for cid, spec in cockpit.cards.items()
                        if classify(spec.product).out_protocol in makers}
        self._pending = {cid: {} for cid in cockpit.cards}  # clé de trame -> trame, dans l'ordre
        self._last_write = {}
        # simulateur : connecteur créé à la demande (connect_sim), abonnements par commande
        self.sim = None
        self.sim_connected = False
        self._sim_listeners = {}          # dataref -> [commandes]
        for inst in cockpit.instruments.values():
            for ctrl in inst.controls.values():
                for ref in ctrl.sim_datarefs():
                    self._sim_listeners.setdefault(ref, []).append(ctrl)

    # ------------------------------------------------------------ cœur, sans matériel
    def feed(self, card_id, raw_inputs, t, active_level):
        """Nouvel état brut des entrées d'une carte."""
        active = [int(v == active_level) for v in raw_inputs]
        for inst in self.cockpit.instruments.values():
            if inst.card == card_id:
                for ctrl in inst.controls.values():
                    ctrl.update(active, t)

    def key(self, card_id, code, t):
        """Touche reçue d'un clavier (testable sans matériel)."""
        for inst in self.cockpit.instruments.values():
            if inst.card == card_id:
                for ctrl in inst.controls.values():
                    if hasattr(ctrl, "on_key"):
                        ctrl.on_key(code, t)

    def poll(self, t):
        changes = []
        for inst in self.cockpit.instruments.values():
            for name, ctrl in inst.controls.items():
                v = ctrl.poll(t)
                if v is not None:
                    changes.append(Change(inst.id, name, v, t))
                    self._apply_output(inst.card, ctrl, v)
                take = getattr(ctrl, "take_frames", None)   # commandes qui produisent leurs trames (DME)
                if take is not None:
                    pending = self._pending[inst.card]
                    for key, frame in take():
                        pending.pop(key, None)              # une trame plus récente passe en dernier
                        pending[key] = frame
        return changes

    def _apply_output(self, card_id, ctrl, value):
        out = self.outputs.get(card_id)
        if isinstance(out, radio_airbus.RadioOutputs) and hasattr(ctrl, "radio_display"):
            texts, leds = ctrl.radio_display()
            for name, text in texts.items():
                out.set_display(name, text)
            for name in radio_airbus.LEDS:
                out.set_led(name, bool(leds.get(name)))
            self._pending[card_id].update({"display": out.display_frame(), "leds": out.led_frame()})
            return
        if out is not None and hasattr(ctrl, "led_states"):    # commande qui gère plusieurs voyants
            for name, on in ctrl.led_states().items():
                out.set_led(name, on)
            self._pending[card_id]["leds"] = out.led_frame()
            return
        if out is None or (ctrl.display is None and ctrl.led is None):
            return
        if ctrl.display is not None:
            shown, dot = ctrl.shown(value)
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
        self._pending[card_id].clear()                      # trames périmées
        for inst in self.cockpit.instruments.values():
            if inst.card == card_id:
                for ctrl in inst.controls.values():
                    if hasattr(ctrl, "restart"):
                        ctrl.restart(cold=True)             # le DME refait sa mise sous tension
        out = self.outputs.get(card_id)
        if isinstance(out, radio_airbus.RadioOutputs):
            self._pending[card_id].update({"display": out.display_frame(), "leds": out.led_frame()})
        elif isinstance(out, usbfmc.FmcOutputs):
            self._pending[card_id]["leds"] = out.led_frame()
        elif out is not None:
            p0, p1 = out.display_frames()
            self._pending[card_id].update({"page0": p0, "page1": p1, "leds": out.led_frame()})

    def _controls(self):
        for inst in self.cockpit.instruments.values():
            yield from inst.controls.values()

    def sim_step(self, changed, connected, now):
        """Cœur de la liaison simulateur (testable sans réseau) : nouvelles valeurs, état
        de la connexion. Retourne les actions à transmettre."""
        if connected != self.sim_connected:
            self.sim_connected = connected
            for ctrl in self._controls():
                ctrl.sim_connected = connected
                if ctrl.display is not None:
                    ctrl._changed = True          # réafficher (blank_unless dépend de la liaison)
            if connected:
                for ctrl in self._controls():
                    ctrl.sim_sync()               # pousse la position des interrupteurs
        for ref, value in changed.items():
            for ctrl in self._sim_listeners.get(ref, ()):
                ctrl.on_sim(ref, value, now)
        actions = []
        for ctrl in self._controls():
            actions += ctrl.take_sim_actions()
        return actions

    def connect_sim(self):
        """Ouvre la liaison X-Plane si la configuration en déclare une."""
        if self.cockpit.sim and self.sim is None:
            from ..sim.xplane import XPlane
            self.sim = XPlane(self.cockpit.sim["host"], self.cockpit.sim["port"])
            for ref in self._sim_listeners:
                self.sim.subscribe(ref)
            for i in range(8):                       # code OACI de l'avion chargé
                self.sim.subscribe(f"sim/aircraft/view/acf_ICAO[{i}]")

    @property
    def aircraft(self):
        """Code OACI de l'avion chargé dans X-Plane (« B738 »), ou chaîne vide."""
        if self.sim is None:
            return ""
        codes = [int(self.sim.values.get(f"sim/aircraft/view/acf_ICAO[{i}]", 0)) for i in range(8)]
        return "".join(chr(c) for c in codes if 32 < c < 127)

    # ------------------------------------------------------------ matériel
    def connect(self):
        """Ouvre les cartes déclarées (et la liaison X-Plane). Retourne {id: statut}."""
        self.connect_sim()
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
                if ev.kind == "key":                  # clavier (CDU) : une touche par événement
                    self.key(cid, ev.index, card.t0 + ev.t)
                elif ev.kind == "state":
                    # horloge absolue : plusieurs cartes, une seule base de temps
                    self.feed(cid, ev.value, card.t0 + ev.t, card.type.active_level)
                elif ev.kind == "error":
                    self.status[cid] = f"perdue : {ev.value}"
                    card.stop()
                    del self.cards[cid]
        now = time.monotonic()
        if self.sim is not None:
            for action in self.sim_step(self.sim.poll(), self.sim.connected, now):
                (self.sim.command if action[0] == "cmd" else self.sim.write)(*action[1:])
        changes = self.poll(now)
        if self.sim is not None:                  # actions nées du poll (interrupteurs…)
            for action in self.sim_step({}, self.sim.connected, now):
                (self.sim.command if action[0] == "cmd" else self.sim.write)(*action[1:])
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
        if self.sim is not None:
            self.sim.close()
            self.sim = None
